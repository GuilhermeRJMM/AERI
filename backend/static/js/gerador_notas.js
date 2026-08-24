let acessoPermitido = false;


function frame() {
    return document.getElementById('gerador-notas-frame');
}


function carregarSeNecessario() {
    const elemento = frame();
    const paginaAtiva = document.querySelector('.nav-item.active')?.dataset.page === 'geradornotas';
    if (!acessoPermitido || !paginaAtiva || !elemento?.dataset.src) return;
    if (elemento.getAttribute('src') !== elemento.dataset.src) {
        elemento.setAttribute('src', elemento.dataset.src);
    }
}


export function configurarAcessoGeradorNotas(permitido) {
    acessoPermitido = Boolean(permitido);
    const elemento = frame();
    if (!acessoPermitido && elemento?.hasAttribute('src')) {
        elemento.removeAttribute('src');
    }
    carregarSeNecessario();
}


export function iniciarGeradorNotas() {
    window.addEventListener('aeri:pagina-alterada', carregarSeNecessario);
}
