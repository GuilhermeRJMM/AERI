export function mostrarPagina(pageId) {
    const itemAlvo = document.querySelector(`.nav-item[data-page="${pageId}"]`);
    if (!itemAlvo || itemAlvo.hidden) return;
    document.querySelectorAll('.nav-item').forEach(item => item.classList.remove('active'));
    itemAlvo.classList.add('active');
    document.querySelectorAll('.page').forEach(page => page.classList.remove('active'));
    document.getElementById(`page-${pageId}`)?.classList.add('active');
}

export function iniciarNavegacao() {
    document.querySelector('.sidebar-nav').addEventListener('click', evento => {
        const item = evento.target.closest('[data-page]');
        if (item && !item.hidden) mostrarPagina(item.dataset.page);
    });
}
