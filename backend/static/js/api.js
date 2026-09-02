let csrfToken = '';
const METODOS_SEGUROS = ['GET', 'HEAD', 'OPTIONS'];

export function definirCsrfToken(token) {
    csrfToken = token || '';
}

function informarSessaoExpirada() {
    window.dispatchEvent(new CustomEvent('aeri:sessao-expirada'));
}

async function atualizarCsrfDaSessao() {
    const resposta = await fetch('/api/sessao', {
        credentials: 'same-origin',
        cache: 'no-store',
    });
    if (resposta.status === 401) {
        informarSessaoExpirada();
        throw new Error('Sua sessão expirou. Entre novamente.');
    }
    if (!resposta.ok) return '';
    const dados = await resposta.json().catch(() => ({}));
    definirCsrfToken(dados.csrfToken);
    return csrfToken;
}

export async function requisicaoAeri(url, opcoes = {}) {
    const metodo = String(opcoes.method || 'GET').toUpperCase();
    const headers = new Headers(opcoes.headers || {});
    const exigeCsrf = !METODOS_SEGUROS.includes(metodo);
    if (exigeCsrf && !csrfToken) await atualizarCsrfDaSessao();
    if (exigeCsrf) headers.set('X-CSRF-Token', csrfToken);
    if (opcoes.background) headers.set('X-AERI-Background', '1');
    const {background: _background, resposta: formatoResposta, ...opcoesFetch} = opcoes;
    opcoes = {...opcoesFetch, headers};
    let resposta = await fetch(url, opcoes);
    if (resposta.status === 403 && exigeCsrf) {
        const tokenAnterior = csrfToken;
        const tokenAtual = await atualizarCsrfDaSessao();
        if (tokenAtual && tokenAtual !== tokenAnterior) {
            headers.set('X-CSRF-Token', tokenAtual);
            resposta = await fetch(url, opcoes);
        }
    }
    if (resposta.status === 401) {
        informarSessaoExpirada();
        throw new Error('Sua sessão expirou. Entre novamente.');
    }
    if (resposta.status === 204) return null;
    if (resposta.ok && formatoResposta === 'blob') return resposta.blob();
    const tipoConteudo = resposta.headers.get('content-type') || '';
    let dados = {};
    if (tipoConteudo.includes('application/json')) {
        try {
            dados = await resposta.json();
        } catch (_erro) {
            dados = {};
        }
    } else {
        const texto = (await resposta.text()).trim();
        dados = texto;
    }
    if (!resposta.ok) {
        const detalhe = dados && typeof dados === 'object'
            ? dados.detail || dados.erro
            : '';
        const erro = new Error(detalhe || 'O servidor não conseguiu concluir a operação. Tente novamente mais tarde.');
        erro.status = resposta.status;
        erro.identificador = resposta.headers.get('X-Request-ID') || '';
        throw erro;
    }
    return dados;
}
