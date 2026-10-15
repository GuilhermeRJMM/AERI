const {issueSignedToken, presignUrl} = require('@vercel/blob');

const LIMITE_UPLOAD = 25 * 1024 * 1024;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

function responder(res, status, corpo) {
  res.status(status).setHeader('Cache-Control', 'no-store');
  res.setHeader('Content-Type', 'application/json; charset=utf-8');
  res.end(JSON.stringify(corpo));
}

function corpoJson(req) {
  if (req.body && typeof req.body === 'object' && !Buffer.isBuffer(req.body)) return req.body;
  const bruto = Buffer.isBuffer(req.body) ? req.body.toString('utf8') : String(req.body || '');
  try { return JSON.parse(bruto); } catch { return null; }
}

function origemDaRequisicao(req) {
  const origem = String(req.headers.origin || '');
  const host = String(req.headers.host || '').toLowerCase();
  let parsed;
  try { parsed = new URL(origem); } catch { return null; }
  if (!['https:', 'http:'].includes(parsed.protocol) || parsed.host.toLowerCase() !== host
      || parsed.username || parsed.password || parsed.pathname !== '/' || parsed.search || parsed.hash) return null;
  return parsed.origin;
}

async function autorizarNoAeri(req, origem, uploadId, operacao) {
  const cabecalhos = {
    'content-type': 'application/json',
    'origin': origem,
    'x-csrf-token': String(req.headers['x-csrf-token'] || ''),
  };
  if (req.headers.cookie) cabecalhos.cookie = String(req.headers.cookie);
  const resposta = await fetch(`${origem}/api/rtd-intimacoes/uploads/${uploadId}/autorizar`, {
    method: 'POST', headers: cabecalhos, body: JSON.stringify({operacao}),
    signal: AbortSignal.timeout(10000),
  });
  const dados = await resposta.json().catch(() => ({}));
  if (!resposta.ok) return {erro: dados.detail || 'Não foi possível autorizar o arquivo.', status: resposta.status};
  return {dados};
}

module.exports = async function rtdUploadUrl(req, res) {
  if (req.method !== 'POST') return responder(res, 405, {detail: 'Método não permitido.'});
  const origem = origemDaRequisicao(req);
  const corpo = corpoJson(req);
  const uploadId = String(corpo?.upload_id || '');
  const operacao = String(corpo?.operacao || '').toLowerCase();
  if (!origem || !UUID.test(uploadId) || !['put', 'get', 'delete'].includes(operacao)) {
    return responder(res, 400, {detail: 'Solicitação de arquivo inválida.'});
  }
  if (!process.env.BLOB_STORE_ID) {
    return responder(res, 503, {detail: 'O armazenamento privado de documentos não está disponível.'});
  }

  try {
    const autorizacao = await autorizarNoAeri(req, origem, uploadId, operacao);
    if (autorizacao.erro) return responder(res, autorizacao.status, {detail: autorizacao.erro});
    const {pathname} = autorizacao.dados;
    if (typeof pathname !== 'string' || pathname !== `rtd-intimacoes/temporarios/${uploadId}.pdf`) {
      return responder(res, 403, {detail: 'O caminho do arquivo não foi autorizado.'});
    }

    const validade = Date.now() + 5 * 60 * 1000;
    const formato = {pathname, operations: [operacao], validUntil: validade,
      storeId: process.env.BLOB_STORE_ID};
    if (process.env.VERCEL_OIDC_TOKEN) formato.oidcToken = process.env.VERCEL_OIDC_TOKEN;
    if (operacao === 'put') {
      formato.allowedContentTypes = ['application/pdf'];
      formato.maximumSizeInBytes = LIMITE_UPLOAD;
    }
    const delegacao = await issueSignedToken(formato);
    const opcoes = {operation: operacao, pathname, access: 'private', validUntil: validade};
    if (operacao === 'put') Object.assign(opcoes, {
      allowedContentTypes: ['application/pdf'], maximumSizeInBytes: LIMITE_UPLOAD,
      addRandomSuffix: false, allowOverwrite: false,
    });
    if (operacao === 'get') opcoes.useCache = false;
    const {presignedUrl} = await presignUrl(delegacao, opcoes);

    if (operacao === 'delete') {
      const removido = await fetch(presignedUrl, {method: 'DELETE', signal: AbortSignal.timeout(15000)});
      if (!removido.ok && removido.status !== 404) {
        return responder(res, 502, {detail: 'O temporário não foi removido; tente novamente ao fechar a janela.'});
      }
      const cabecalhos = {
        'content-type': 'application/json', 'origin': origem,
        'x-csrf-token': String(req.headers['x-csrf-token'] || ''),
      };
      if (req.headers.cookie) cabecalhos.cookie = String(req.headers.cookie);
      const confirmado = await fetch(`${origem}/api/rtd-intimacoes/uploads/${uploadId}/remocao-confirmada`, {
        method: 'POST', headers: cabecalhos, body: '{}', signal: AbortSignal.timeout(10000),
      });
      if (!confirmado.ok) return responder(res, 502, {detail: 'O arquivo foi removido, mas a confirmação interna falhou.'});
      return responder(res, 200, {ok: true});
    }
    return responder(res, 200, {url: presignedUrl, expiraEm: validade});
  } catch (_erro) {
    return responder(res, 502, {detail: 'Não foi possível preparar o envio privado. Tente novamente.'});
  }
};
