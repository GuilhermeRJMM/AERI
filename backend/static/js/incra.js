import {baixarArquivo, escaparHtml} from './util.js';
import {requisicaoAeri} from './api.js';

let arquivoIncra = null;
let resultadoIncra = null;

function selecionarPdfIncra(evento) {
    const arquivo = evento.target.files?.[0];
    if (!arquivo) return;
    arquivoIncra = arquivo;
    document.getElementById('incra-file-name').textContent = arquivo.name;
    document.getElementById('btn-incra').disabled = false;
    document.getElementById('incra-dropzone').classList.add('com-arquivo');
}

async function analisarIncra() {
    if (!arquivoIncra) return;
    const botao = document.getElementById('btn-incra');
    const resultado = document.getElementById('incra-resultado');
    botao.disabled = true;
    botao.textContent = 'Lendo relatório...';
    resultado.innerHTML = '<div class="incra-loading">Extraindo e classificando os protocolos...</div>';
    try {
        resultadoIncra = await requisicaoAeri('/analisar-incra', {
            method: 'POST',
            headers: {'Content-Type': 'application/pdf'},
            body: arquivoIncra,
        });
        if (resultadoIncra.erro) throw new Error(resultadoIncra.erro);
        renderizarIncra('COMUNICAR');
    } catch (erro) {
        resultado.innerHTML = `<div class="incra-erro">${escaparHtml(erro.message || 'Não foi possível processar o PDF.')}</div>`;
    } finally {
        botao.disabled = false;
        botao.textContent = 'Gerar lista de protocolos';
    }
}

function itensIncra(filtro) {
    return (resultadoIncra?.itens || []).filter(item => item.status === filtro);
}

function renderizarIncra(filtro) {
    if (!resultadoIncra) return;
    const rotulos = {
        COMUNICAR: 'Comunicar',
        REVISAR: 'Revisar',
        FORA_DAS_HIPOTESES: 'Fora das hipóteses',
    };
    const linhas = itensIncra(filtro).map(item => `
        <tr>
            <td><strong>${escaparHtml(item.protocolo)}</strong></td>
            <td>${escaparHtml(item.ato)}</td>
            <td>${escaparHtml(item.motivo)}</td>
            <td class="incra-ocorrencias">${item.ocorrencias}</td>
        </tr>`).join('');

    document.getElementById('incra-resultado').innerHTML = `
        <div class="incra-resumo">
            <div><strong>${resultadoIncra.protocolos_unicos}</strong><span>Protocolos únicos</span></div>
            <div><strong>${resultadoIncra.lancamentos}</strong><span>Lançamentos lidos</span></div>
            <div><strong>${resultadoIncra.paginas}</strong><span>Páginas</span></div>
        </div>
        <div class="incra-toolbar">
            <div class="incra-filtros">
                ${Object.keys(rotulos).map(status => `<button class="incra-filtro ${status === filtro ? 'active' : ''}" data-filtro="${status}">${rotulos[status]} <b>${resultadoIncra.contagens[status]}</b></button>`).join('')}
            </div>
            <div class="incra-acoes">
                <button data-acao="copiar" data-filtro="${filtro}">Copiar lista</button>
                <button data-acao="csv" data-filtro="${filtro}">Baixar CSV</button>
            </div>
        </div>
        <div class="incra-table-wrap">
            <table class="incra-table">
                <thead><tr><th>Protocolo</th><th>Tipo do ato</th><th>Enquadramento</th><th>Ocorrências</th></tr></thead>
                <tbody>${linhas || '<tr><td colspan="4" class="incra-vazio">Nenhum protocolo nesta categoria.</td></tr>'}</tbody>
            </table>
        </div>`;
}

function copiarListaIncra(filtro) {
    const texto = itensIncra(filtro).map(item => `${item.protocolo} - ${item.ato}`).join('\n');
    navigator.clipboard.writeText(texto);
}

function baixarCsvIncra(filtro) {
    const cabecalho = 'Protocolo;Tipo do ato;Enquadramento;Ocorrências';
    const linhas = itensIncra(filtro).map(item => [item.protocolo, item.ato, item.motivo, item.ocorrencias]
        .map(valor => `"${String(valor).replace(/"/g, '""')}"`).join(';'));
    baixarArquivo(
        '\uFEFF' + [cabecalho, ...linhas].join('\n'),
        'text/csv;charset=utf-8',
        `protocolos-incra-${filtro.toLowerCase()}.csv`,
    );
}

function tratarAcaoResultado(evento) {
    const botao = evento.target.closest('button');
    if (!botao) return;
    if (botao.classList.contains('incra-filtro')) return renderizarIncra(botao.dataset.filtro);
    if (botao.dataset.acao === 'copiar') return copiarListaIncra(botao.dataset.filtro);
    if (botao.dataset.acao === 'csv') baixarCsvIncra(botao.dataset.filtro);
}

export function iniciarIncra() {
    document.getElementById('incra-pdf').addEventListener('change', selecionarPdfIncra);
    document.getElementById('btn-incra').addEventListener('click', analisarIncra);
    document.getElementById('incra-resultado').addEventListener('click', tratarAcaoResultado);
}
