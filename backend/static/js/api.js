let csrfToken = '';

export function definirCsrfToken(token) {
    csrfToken = token || '';
}

export async function requisicaoAeri(url, opcoes = {}) {
    const metodo = String(opcoes.method || 'GET').toUpperCase();
    const headers = new Headers(opcoes.headers || {});
    if (!['GET', 'HEAD', 'OPTIONS'].includes(metodo)) headers.set('X-CSRF-Token', csrfToken);
    opcoes = {...opcoes, headers};
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
        if (resposta.ok && texto) dados = {resultado: texto};
    }
    if (!resposta.ok) {
        const erro = new Error(dados.detail || dados.erro || 'O servidor não conseguiu concluir a operação. Tente novamente mais tarde.');
        erro.status = resposta.status;
        throw erro;
    }
    return dados.resultado ?? dados;
}
