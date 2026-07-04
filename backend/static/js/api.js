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
    const dados = await resposta.json();
    if (!resposta.ok) {
        throw new Error(dados.detail || dados.erro || 'Não foi possível concluir a operação.');
    }
    return dados;
}
