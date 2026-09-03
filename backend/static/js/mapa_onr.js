import {requisicaoAeri} from './api.js?v=20260902-arquivo-v1';


function elementos() {
    return {
        formulario: document.getElementById('form-mapa-onr'),
        entrada: document.getElementById('mapa-onr-matricula'),
        botao: document.getElementById('btn-mapa-onr-consultar'),
        status: document.getElementById('mapa-onr-status'),
        conversor: document.getElementById('mapa-onr-nativo'),
    };
}


function atualizarStatus(texto, tipo = '') {
    const status = elementos().status;
    if (!status) return;
    status.textContent = texto;
    status.dataset.tipo = tipo;
}


function motor() {
    if (!window.AERI_MAPA_ONR) throw new Error('O conversor MAPA-ONR não foi carregado. Atualize a página.');
    return window.AERI_MAPA_ONR;
}


function notificarAnaliseHibrida(carga) {
    // O adaptador de confrontantes continua desacoplado do conversor. O evento
    // local é síncrono para que o contexto esteja pronto antes da extração.
    window.dispatchEvent(new MessageEvent('message', {data: carga, source: window}));
}


async function consultar(evento) {
    evento.preventDefault();
    const {entrada, botao} = elementos();
    const numero = entrada.value.trim();
    botao.disabled = true;
    atualizarStatus(`Consultando a matrícula ${numero} na Tri7…`, 'carregando');
    try {
        const resultado = await requisicaoAeri('/api/mapa-onr/matricula', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({numero_matricula: numero}),
        });
        const carga = {
            tipo: 'AERI_MAPA_ONR_MATRICULA',
            numeroMatricula: resultado.numero_matricula,
            tipoImovel: resultado.tipo_imovel,
            texto: resultado.texto,
            contextoAeri: resultado.contexto_aeri,
        };
        notificarAnaliseHibrida(carga);
        const processado = motor().carregarMatricula(carga);
        atualizarStatus(
            `Matrícula ${processado.numeroMatricula} carregada: ${processado.totalAtos} ato(s) reconhecido(s).`,
            'sucesso',
        );
    } catch (erro) {
        atualizarStatus(erro.message, 'erro');
    } finally {
        botao.disabled = false;
    }
}


export function limparMapaOnr() {
    const entrada = elementos().entrada;
    if (entrada) entrada.value = '';
    atualizarStatus('Informe a matrícula para iniciar.');
    notificarAnaliseHibrida({tipo: 'AERI_MAPA_ONR_LIMPAR'});
    window.AERI_MAPA_ONR?.limpar();
}


export function configurarAcessoMapaOnr(permitido) {
    const conversor = elementos().conversor;
    if (!conversor) return;
    conversor.hidden = !permitido;
    conversor.dataset.autorizado = String(Boolean(permitido));
}


export function iniciarMapaOnr() {
    const {formulario, conversor} = elementos();
    if (!formulario || !conversor) return;
    formulario.addEventListener('submit', consultar);
}
