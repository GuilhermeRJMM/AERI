import {requisicaoAeri} from './api.js';

const ROTULOS = {
    OPERATIONAL: 'Operacional',
    UNDERMAINTENANCE: 'Em manutenção',
    DEGRADEDPERFORMANCE: 'Desempenho degradado',
    PARTIALOUTAGE: 'Interrupção parcial',
    MAJOROUTAGE: 'Indisponível',
    UNKNOWN: 'Status desconhecido',
};

let temporizador = null;
let iniciado = false;

function classeStatus(status) {
    if (status === 'OPERATIONAL') return 'operacional';
    if (['UNDERMAINTENANCE', 'DEGRADEDPERFORMANCE'].includes(status)) return 'atencao';
    if (['PARTIALOUTAGE', 'MAJOROUTAGE'].includes(status)) return 'indisponivel';
    return 'desconhecido';
}

function formatarData(valor) {
    if (!valor) return 'Aguardando primeira atualização';
    return new Intl.DateTimeFormat('pt-BR', {dateStyle:'short', timeStyle:'short'}).format(new Date(valor));
}

function renderizarComponentes(componentes) {
    const lista = document.getElementById('status-onr-componentes');
    lista.replaceChildren();
    if (!componentes.length) {
        const item = document.createElement('li');
        item.textContent = 'Nenhum evento recebido do ONR.';
        lista.appendChild(item);
        return;
    }
    componentes.slice(0, 4).forEach(componente => {
        const item = document.createElement('li');
        const nome = document.createElement('span');
        const status = document.createElement('strong');
        nome.textContent = componente.nome;
        status.textContent = ROTULOS[componente.status] || componente.status;
        status.className = `status-onr-${classeStatus(componente.status)}`;
        item.append(nome, status);
        lista.appendChild(item);
    });
}

function renderizarStatus(dados) {
    const status = dados.status || 'UNKNOWN';
    const classe = classeStatus(status);
    const botao = document.getElementById('status-onr');
    botao.className = `status-onr status-onr-${classe}`;
    botao.title = `Ofício Eletrônico: ${ROTULOS[status] || status}`;
    document.getElementById('status-onr-rotulo').textContent = ROTULOS[status] || status;
    document.getElementById('status-onr-atualizado').textContent = `Atualizado em ${formatarData(dados.atualizadoEm)}`;
    document.getElementById('status-onr-configuracao').hidden = dados.configurado !== false;
    renderizarComponentes(dados.componentes || []);
    const evento = document.getElementById('status-onr-evento');
    evento.textContent = dados.eventos?.[0]?.resumo || '';
    evento.hidden = !evento.textContent;

    const alerta = document.getElementById('aviso-status-onr');
    const exibirAlerta = ['UNDERMAINTENANCE', 'DEGRADEDPERFORMANCE', 'PARTIALOUTAGE', 'MAJOROUTAGE'].includes(status);
    alerta.hidden = !exibirAlerta;
    alerta.className = `aviso-status-onr aviso-status-onr-${classe}`;
    document.getElementById('aviso-status-onr-texto').textContent =
        `Ofício Eletrônico: ${ROTULOS[status] || status}. Consulte o status oficial antes de prosseguir.`;
}

async function carregarStatus() {
    try {
        renderizarStatus(await requisicaoAeri('/api/status/onr'));
    } catch {
        renderizarStatus({status:'UNKNOWN', componentes:[], configurado:true});
    }
}

function alternarDetalhes(evento) {
    evento.stopPropagation();
    const painel = document.getElementById('status-onr-painel');
    const abrir = painel.hidden;
    painel.hidden = !abrir;
    document.getElementById('status-onr').setAttribute('aria-expanded', String(abrir));
}

function fecharDetalhes() {
    document.getElementById('status-onr-painel').hidden = true;
    document.getElementById('status-onr').setAttribute('aria-expanded', 'false');
}

export function iniciarStatusOnr() {
    if (iniciado) return;
    iniciado = true;
    document.getElementById('status-onr').addEventListener('click', alternarDetalhes);
    document.addEventListener('click', evento => {
        if (!evento.target.closest('.status-onr-container')) fecharDetalhes();
    });
    document.addEventListener('keydown', evento => {
        if (evento.key === 'Escape') fecharDetalhes();
    });
}

export function ativarStatusOnr() {
    carregarStatus();
    window.clearInterval(temporizador);
    temporizador = window.setInterval(carregarStatus, 60_000);
}

export function pararStatusOnr() {
    window.clearInterval(temporizador);
    temporizador = null;
    fecharDetalhes();
}
