let csrfToken = '';

export function definirCsrfToken(token) {
    csrfToken = token || '';
}

export async function requisicaoAeri(url, opcoes = {}) {
    const metodo = String(opcoes.method || 'GET').toUpperCase();
    const headers = new Headers(opcoes.headers || {});
    if (!['GET', 'HEAD', 'OPTIONS'].includes(metodo)) headers.set('X-CSRF-Token', csrfToken);
    if (opcoes.background) headers.set('X-AERI-Background', '1');
    const {background: _background, ...opcoesFetch} = opcoes;
    opcoes = {...opcoesFetch, headers};
    const resposta = await fetch(url, opcoes);
    if (resposta.status === 401) {
        window.dispatchEvent(new CustomEvent('aeri:sessao-expirada'));
        throw new Error('Sua sessão expirou. Entre novamente.');
    }
    if (resposta.status === 204) return null;
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
