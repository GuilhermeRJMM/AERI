const {list, del} = require('@vercel/blob');

function responder(res, status, corpo) {
  res.status(status).setHeader('Cache-Control', 'no-store');
  res.setHeader('Content-Type', 'application/json; charset=utf-8');
  res.end(JSON.stringify(corpo));
}

module.exports = async function limparUploadsRtd(req, res) {
  if (req.method !== 'POST') return responder(res, 405, {detail: 'Método não permitido.'});
  const segredo = process.env.CRON_SECRET || '';
  const recebido = String(req.headers.authorization || '').replace(/^Bearer\s+/i, '').trim();
  const recebidoBytes = Buffer.from(recebido);
  const segredoBytes = Buffer.from(segredo);
  if (!segredo || !recebido || recebidoBytes.length !== segredoBytes.length
      || !require('crypto').timingSafeEqual(recebidoBytes, segredoBytes)) {
    return responder(res, 401, {detail: 'Não autorizado.'});
  }
  if (!process.env.BLOB_STORE_ID) {
    return responder(res, 503, {detail: 'O armazenamento privado não está disponível.'});
  }
  try {
    const oidcToken = process.env.VERCEL_OIDC_TOKEN;
    const storeId = process.env.BLOB_STORE_ID;
    const limiteIdade = Date.now() - 24 * 60 * 60 * 1000;
    let cursor;
    let paginas = 0;
    let removidos = 0;
    do {
      const pagina = await list({prefix: 'rtd-intimacoes/temporarios/', limit: 1000, cursor,
        oidcToken, storeId});
      const expirados = pagina.blobs.filter(blob => Date.parse(blob.uploadedAt) < limiteIdade);
      for (let i = 0; i < expirados.length; i += 100) {
        await del(expirados.slice(i, i + 100).map(blob => blob.url), {oidcToken, storeId});
        removidos += Math.min(100, expirados.length - i);
      }
      cursor = pagina.cursor;
      paginas += 1;
    } while (cursor && paginas < 50);
    return responder(res, 200, {ok: true, removidos});
  } catch (_erro) {
    return responder(res, 500, {detail: 'A limpeza de temporários não foi concluída.'});
  }
};
