export async function requisicaoAeri(url, opcoes = {}) {
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
