import {escaparHtml} from './util.js';
import {requisicaoAeri} from './api.js';

let arquivoLivroProto = null;
let resultadoLivroProto = null;

const ROTULOS_STATUS = {
    PRENOTADO: 'Prenotado',
    REGISTRADO: 'Registrado',
    SEM_EFEITO: 'Sem efeito',
    INDEFINIDO: 'Indefinido',
};

function selecionarPdfLivroProto(evento) {
    const arquivo = evento.target.files?.[0];
    if (!arquivo) return;
    arquivoLivroProto = arquivo;
    document.getElementById('livroproto-file-name').textContent = arquivo.name;
    document.getElementById('btn-livroproto').disabled = false;
    document.getElementById('livroproto-dropzone').classList.add('com-arquivo');
}

async function analisarLivroProtocolos() {
    if (!arquivoLivroProto) return;
    const botao = document.getElementById('btn-livroproto');
    const resultado = document.getElementById('livroproto-resultado');
    botao.disabled = true;
    botao.textContent = 'Conferindo na Tri7...';
    resultado.innerHTML = '<div class="incra-loading">Lendo o Livro de Protocolos e conferindo os registrados na Tri7…</div>';
    try {
        resultadoLivroProto = await requisicaoAeri('/api/livro-protocolos/analisar', {
            method: 'POST',
            headers: {'Content-Type': 'application/pdf'},
            body: arquivoLivroProto,
        });
        renderizarLivroProtocolos('TODOS');
    } catch (erro) {
        resultado.innerHTML = `<div class="incra-erro">${escaparHtml(erro.message || 'Não foi possível processar o PDF.')}</div>`;
    } finally {
        botao.disabled = false;
        botao.textContent = 'Conferir protocolos';
    }
}

function itensLivroProto(filtro) {
    const protocolos = resultadoLivroProto?.protocolos || [];
    if (filtro === 'TODOS') return protocolos;
    if (filtro === 'OCORRENCIAS') return protocolos.filter(item => item.ocorrencias.length > 0);
    if (filtro === 'FALHAS') return protocolos.filter(item => item.erro);
    return protocolos.filter(item => item.status === filtro);
}

function renderizarOcorrencias(item) {
    if (item.erro) return `<span class="livroproto-erro-item">${escaparHtml(item.erro)}</span>`;
    if (!item.conferido) return '<span class="livroproto-nao-conferido">—</span>';
    if (!item.ocorrencias.length) return '<span class="livroproto-ok">Sem ocorrências</span>';
    return `<ul class="livroproto-ocorrencias">${item.ocorrencias.map(ocorrencia => `
        <li class="livroproto-gravidade-${ocorrencia.gravidade.toLowerCase()}">${escaparHtml(ocorrencia.descricao)}</li>
    `).join('')}</ul>`;
}

function renderizarLivroProtocolos(filtro) {
    if (!resultadoLivroProto) return;
    const resumo = resultadoLivroProto.resumo;
    const linhas = itensLivroProto(filtro).map(item => `
        <tr>
            <td><strong>${escaparHtml(item.numeroFormatado)}</strong><small>${escaparHtml(item.data ? new Intl.DateTimeFormat('pt-BR').format(new Date(item.data)) : '—')}</small></td>
            <td>${escaparHtml(item.nomeApresentante)}</td>
            <td><span class="livroproto-status livroproto-status-${item.status.toLowerCase()}">${escaparHtml(ROTULOS_STATUS[item.status] || item.status)}</span></td>
            <td>${renderizarOcorrencias(item)}</td>
        </tr>`).join('');

    const filtros = [
        ['TODOS', 'Todos', resumo.total],
        ['REGISTRADO', 'Registrados', resumo.registrados],
        ['PRENOTADO', 'Prenotados', resumo.prenotados],
        ['SEM_EFEITO', 'Sem efeito', resumo.semEfeito],
        ['INDEFINIDO', 'Indefinidos', resumo.indefinidos],
        ['OCORRENCIAS', 'Com ocorrências', resumo.comOcorrencias],
        ['FALHAS', 'Falha na consulta', resumo.falhasConsulta],
    ];

    document.getElementById('livroproto-resultado').innerHTML = `
        <div class="incra-resumo">
            <div><strong>${resumo.total}</strong><span>Protocolos na folha</span></div>
            <div><strong>${resumo.conferidos}</strong><span>Conferidos na Tri7</span></div>
            <div><strong>${resumo.totalOcorrencias}</strong><span>Ocorrências encontradas</span></div>
            <div><strong>${new Intl.DateTimeFormat('pt-BR').format(new Date(resultadoLivroProto.dataEsperada))}</strong><span>Data esperada dos registros</span></div>
        </div>
        <div class="incra-toolbar">
            <div class="incra-filtros">
                ${filtros.map(([chave, rotulo, total]) => `<button class="incra-filtro ${chave === filtro ? 'active' : ''}" data-filtro="${chave}">${rotulo} <b>${total}</b></button>`).join('')}
            </div>
        </div>
        <div class="incra-table-wrap">
            <table class="incra-table">
                <thead><tr><th>Protocolo</th><th>Apresentante</th><th>Situação</th><th>Ocorrências</th></tr></thead>
                <tbody>${linhas || '<tr><td colspan="4" class="incra-vazio">Nenhum protocolo nesta categoria.</td></tr>'}</tbody>
            </table>
        </div>`;
}

function tratarAcaoResultado(evento) {
    const botao = evento.target.closest('.incra-filtro');
    if (botao) renderizarLivroProtocolos(botao.dataset.filtro);
}

export function iniciarLivroProtocolos() {
    document.getElementById('livroproto-pdf').addEventListener('change', selecionarPdfLivroProto);
    document.getElementById('btn-livroproto').addEventListener('click', analisarLivroProtocolos);
    document.getElementById('livroproto-resultado').addEventListener('click', tratarAcaoResultado);
}
