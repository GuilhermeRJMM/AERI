import {baixarArquivo, escaparHtml} from './util.js';
import {requisicaoAeri} from './api.js?v=20260824-csrf-v1';

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
    botao.textContent = 'Consultando relatório e Tri7...';
    resultado.innerHTML = '<div class="incra-loading">Extraindo os protocolos e consultando situação, matrículas e atos na Tri7...</div>';
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
        botao.textContent = 'Gerar lista e consultar Tri7';
    }
}

function itensIncra(filtro) {
    return (resultadoIncra?.itens || []).filter(item => item.status === filtro);
}

function textoMatriculasAtos(item) {
    return (item.matriculas || []).map(matricula => (
        `Matrícula ${matricula.numeroFormatado}: ${(matricula.atos || []).join(', ') || 'sem ato'}`
    )).join(' | ');
}

function htmlMatriculasAtos(item) {
    if (!item.matriculas?.length) return '<span class="incra-sem-ato">—</span>';
    return item.matriculas.map(matricula => `
        <div class="incra-matricula-atos">
            <strong>Matrícula ${escaparHtml(matricula.numeroFormatado)}</strong>
            <span>${escaparHtml((matricula.atos || []).join(', ') || 'Sem ato')}</span>
        </div>`).join('');
}

function htmlSituacaoTri7(item) {
    const situacao = item.situacaoTri7 || 'CONSULTA_INDISPONIVEL';
    const detalhes = item.erroTri7 || item.alertaTri7 || item.ultimoAndamento?.tipo || '';
    return `
        <span class="incra-status-tri7 incra-status-${escaparHtml(situacao.toLowerCase())}">
            ${escaparHtml(item.situacaoTri7Rotulo || 'Consulta indisponível')}
        </span>
        ${detalhes ? `<small class="incra-status-detalhe">${escaparHtml(detalhes)}</small>` : ''}`;
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
            <td>${htmlSituacaoTri7(item)}</td>
            <td>${htmlMatriculasAtos(item)}</td>
            <td class="incra-ocorrencias">${item.ocorrencias}</td>
        </tr>`).join('');

    document.getElementById('incra-resultado').innerHTML = `
        <div class="incra-resumo incra-resumo-tri7">
            <div><strong>${resultadoIncra.protocolos_unicos}</strong><span>Protocolos únicos</span></div>
            <div><strong>${resultadoIncra.lancamentos}</strong><span>Lançamentos lidos</span></div>
            <div><strong>${resultadoIncra.paginas}</strong><span>Páginas</span></div>
            <div><strong>${resultadoIncra.contagens_tri7?.CANCELADO_DECURSO_PRAZO || 0}</strong><span>Cancelados por decurso</span></div>
        </div>
        <div class="incra-toolbar">
            <div class="incra-filtros">
                ${Object.keys(rotulos).map(status => `<button class="incra-filtro ${status === filtro ? 'active' : ''}" data-filtro="${status}">${rotulos[status]} <b>${resultadoIncra.contagens[status]}</b></button>`).join('')}
            </div>
            <div class="incra-acoes">
                <button data-acao="reconsultar">Reconsultar Tri7</button>
                <button data-acao="copiar" data-filtro="${filtro}">Copiar lista</button>
                <button data-acao="csv" data-filtro="${filtro}">Baixar CSV</button>
            </div>
        </div>
        <div class="incra-table-wrap">
            <table class="incra-table incra-table-enriquecida">
                <thead><tr><th>Protocolo</th><th>Tipo do ato</th><th>Enquadramento</th><th>Situação Tri7</th><th>Matrículas e atos</th><th>Ocorrências</th></tr></thead>
                <tbody>${linhas || '<tr><td colspan="6" class="incra-vazio">Nenhum protocolo nesta categoria.</td></tr>'}</tbody>
            </table>
        </div>`;
}

async function reconsultarTri7(botao) {
    botao.disabled = true;
    const rotulo = botao.textContent;
    botao.textContent = 'Reconsultando…';
    try {
        resultadoIncra = await requisicaoAeri('/api/incra/reconsultar', {
            method:'POST', headers:{'Content-Type':'application/json'},
            body:JSON.stringify({
                paginas: resultadoIncra.paginas,
                itens: resultadoIncra.itens,
            }),
        });
        renderizarIncra(document.querySelector('.incra-filtro.active')?.dataset.filtro || 'COMUNICAR');
    } catch (erro) {
        alert(erro.message);
        botao.disabled = false;
        botao.textContent = rotulo;
    }
}

function copiarListaIncra(filtro) {
    const texto = itensIncra(filtro).map(item => [
        item.protocolo,
        item.ato,
        item.situacaoTri7Rotulo || 'Consulta indisponível',
        textoMatriculasAtos(item) || 'Sem matrícula/ato identificado',
    ].join(' - ')).join('\n');
    navigator.clipboard.writeText(texto);
}

function baixarCsvIncra(filtro) {
    const cabecalho = 'Protocolo;Tipo do ato;Enquadramento;Situação Tri7;Cancelado;Matrículas e atos;Último andamento;Ocorrências;Alerta Tri7';
    const linhas = itensIncra(filtro).map(item => [
        item.protocolo, item.ato, item.motivo,
        item.situacaoTri7Rotulo || 'Consulta indisponível',
        item.cancelado ? 'SIM' : 'NÃO',
        textoMatriculasAtos(item), item.ultimoAndamento?.tipo || '',
        item.ocorrencias, item.erroTri7 || item.alertaTri7 || '',
    ]
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
    if (botao.dataset.acao === 'reconsultar') return reconsultarTri7(botao);
    if (botao.dataset.acao === 'copiar') return copiarListaIncra(botao.dataset.filtro);
    if (botao.dataset.acao === 'csv') baixarCsvIncra(botao.dataset.filtro);
}

export function iniciarIncra() {
    document.getElementById('incra-pdf').addEventListener('change', selecionarPdfIncra);
    document.getElementById('btn-incra').addEventListener('click', analisarIncra);
    document.getElementById('incra-resultado').addEventListener('click', tratarAcaoResultado);
}
