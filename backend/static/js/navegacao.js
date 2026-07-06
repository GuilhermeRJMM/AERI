export function mostrarPagina(pageId) {
    const itemAlvo = document.querySelector(`.nav-item[data-page="${pageId}"]`);
    if (!itemAlvo || itemAlvo.hidden) return;
    document.querySelectorAll('.nav-item').forEach(item => item.classList.remove('active'));
    itemAlvo.classList.add('active');
    document.querySelectorAll('.page').forEach(page => page.classList.remove('active'));
    document.getElementById(`page-${pageId}`)?.classList.add('active');
}

const limiteMobile = window.matchMedia('(max-width: 720px)');

function atualizarControleSidebar() {
    const mobile = limiteMobile.matches;
    const aberta = mobile
        ? document.body.classList.contains('sidebar-aberta-mobile')
        : !document.body.classList.contains('sidebar-recolhida');
    const botao = document.getElementById('btn-sidebar');
    botao.setAttribute('aria-expanded', String(aberta));
    botao.setAttribute('aria-label', aberta ? 'Recolher menu' : 'Expandir menu');
    botao.title = aberta ? 'Recolher menu' : 'Expandir menu';
}

function fecharSidebarMobile() {
    document.body.classList.remove('sidebar-aberta-mobile');
    atualizarControleSidebar();
}

function alternarSidebar() {
    if (limiteMobile.matches) {
        document.body.classList.toggle('sidebar-aberta-mobile');
    } else {
        document.body.classList.toggle('sidebar-recolhida');
    }
    atualizarControleSidebar();
}

export function iniciarNavegacao() {
    document.querySelector('.sidebar-nav').addEventListener('click', evento => {
        const item = evento.target.closest('[data-page]');
        if (item && !item.hidden) {
            mostrarPagina(item.dataset.page);
            if (limiteMobile.matches) fecharSidebarMobile();
        }
    });
    document.getElementById('btn-sidebar').addEventListener('click', alternarSidebar);
    document.getElementById('sidebar-backdrop').addEventListener('click', fecharSidebarMobile);
    document.addEventListener('keydown', evento => {
        if (evento.key === 'Escape' && limiteMobile.matches) fecharSidebarMobile();
    });
    limiteMobile.addEventListener('change', () => {
        document.body.classList.remove('sidebar-aberta-mobile');
        atualizarControleSidebar();
    });
    atualizarControleSidebar();
}
