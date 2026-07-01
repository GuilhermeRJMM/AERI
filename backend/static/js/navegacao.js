export function mostrarPagina(pageId) {
    document.querySelectorAll('.nav-item').forEach(item => item.classList.remove('active'));
    document.querySelector(`[data-page="${pageId}"]`)?.classList.add('active');
    document.querySelectorAll('.page').forEach(page => page.classList.remove('active'));
    document.getElementById(`page-${pageId}`)?.classList.add('active');
}

export function iniciarNavegacao() {
    document.querySelector('.sidebar-nav').addEventListener('click', evento => {
        const item = evento.target.closest('[data-page]');
        if (item) mostrarPagina(item.dataset.page);
    });
}
