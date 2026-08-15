import {requisicaoAeri} from './api.js';


let framePronto = false;
let cargaPendente = null;


function elementos() {
    return {
        formulario: document.getElementById('form-mapa-onr'),
        entrada: document.getElementById('mapa-onr-matricula'),
        botao: document.getElementById('btn-mapa-onr-consultar'),
        status: document.getElementById('mapa-onr-status'),
        frame: document.getElementById('mapa-onr-frame'),
    };
}


function atualizarStatus(texto, tipo = '') {
    const status = elementos().status;
    if (!status) return;
    status.textContent = texto;
    status.dataset.tipo = tipo;
}


function enviarAoConversor(carga) {
    const frame = elementos().frame;
    if (!frame?.contentWindow || !framePronto) {
        cargaPendente = carga;
        return;
    }
    frame.contentWindow.postMessage(carga, '*');
    cargaPendente = null;
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
        enviarAoConversor({
            tipo: 'AERI_MAPA_ONR_MATRICULA',
            numeroMatricula: resultado.numero_matricula,
            tipoImovel: resultado.tipo_imovel,
            texto: resultado.texto,
            contextoAeri: resultado.contexto_aeri,
        });
        atualizarStatus('Matrícula recebida. O MAPA-ONR está reconhecendo os atos…', 'carregando');
    } catch (erro) {
        atualizarStatus(erro.message, 'erro');
    } finally {
        botao.disabled = false;
    }
}


function receberMensagem(evento) {
    const frame = elementos().frame;
    if (!frame || evento.source !== frame.contentWindow || !evento.data) return;
    if (evento.data.tipo === 'AERI_MAPA_ONR_CARREGADO') {
        framePronto = true;
        if (cargaPendente) enviarAoConversor(cargaPendente);
        return;
    }
    if (evento.data.tipo === 'AERI_MAPA_ONR_ALTURA') {
        const altura = Number(evento.data.altura);
        if (Number.isFinite(altura)) {
            frame.style.height = `${Math.max(720, Math.min(15000, altura + 12))}px`;
        }
        return;
    }
    if (evento.data.tipo === 'AERI_MAPA_ONR_ERRO') {
        atualizarStatus(evento.data.mensagem || 'Não foi possível converter a matrícula.', 'erro');
        return;
    }
    if (evento.data.tipo === 'AERI_MAPA_ONR_PROCESSADO') {
        const quantidade = Number(evento.data.totalAtos || 0);
        atualizarStatus(
            `Matrícula ${evento.data.numeroMatricula} carregada: ${quantidade} ato(s) reconhecido(s).`,
            'sucesso',
        );
    }
}


export function limparMapaOnr() {
    cargaPendente = null;
    const entrada = elementos().entrada;
    if (entrada) entrada.value = '';
    atualizarStatus('Informe a matrícula para iniciar.');
    enviarAoConversor({tipo: 'AERI_MAPA_ONR_LIMPAR'});
}


export function configurarAcessoMapaOnr(permitido) {
    const frame = elementos().frame;
    if (!frame) return;
    const origem = frame.dataset.src;
    if (permitido && origem && frame.getAttribute('src') !== origem) {
        frame.setAttribute('src', origem);
        return;
    }
    if (!permitido && frame.hasAttribute('src')) {
        framePronto = false;
        cargaPendente = null;
        frame.removeAttribute('src');
    }
}


export function iniciarMapaOnr() {
    const {formulario, frame} = elementos();
    if (!formulario || !frame) return;
    formulario.addEventListener('submit', consultar);
    window.addEventListener('message', receberMensagem);
    frame.addEventListener('load', () => {
        framePronto = false;
        frame.contentWindow?.postMessage({tipo: 'AERI_MAPA_ONR_PING'}, '*');
    });
}
