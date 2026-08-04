import {requisicaoAeri} from './api.js';
import {escaparHtml} from './util.js';

function numero(valor) { return new Intl.NumberFormat('pt-BR').format(Number(valor || 0)); }
function data(valor) { return valor ? new Intl.DateTimeFormat('pt-BR').format(new Date(`${valor}T12:00:00`)) : '—'; }

function renderizar(dados) {
    const resumo = dados.resumo || {};
    document.getElementById('painel-resumo').innerHTML = [
        ['Intimações ativas', resumo.total, 'verde'],
        ['Conferências pendentes', resumo.conferencias_pendentes, 'amarelo'],
        ['Certificações vencidas', resumo.certificacoes_vencidas, 'vermelho'],
        ['Divergências para revisar', resumo.divergencias_pendentes, 'cinza'],
    ].map(([rotulo, valor, classe]) => `<div class="rotina-resumo-card ${classe}"><span>${rotulo}</span><strong>${numero(valor)}</strong></div>`).join('');
    document.getElementById('painel-fases').innerHTML = `
        <span>Inicial <strong>${numero(resumo.intimacao)}</strong></span>
        <span>Edital <strong>${numero(resumo.edital)}</strong></span>
        <span>Consolidação <strong>${numero(resumo.consolidacao)}</strong></span>`;
    document.getElementById('painel-pendencias').innerHTML = (dados.pendencias || []).map(item => `<tr>
        <td><strong>${escaparHtml(item.protocolo)}</strong></td>
        <td>${escaparHtml(item.fase)}</td>
        <td>${escaparHtml(item.nome_andamento || '—')}</td>
        <td>${data(item.ultima_conferencia)}</td>
        <td>${data(item.data_certificacao)}</td>
    </tr>`).join('') || '<tr><td colspan="5" class="rotina-vazio">Nenhuma pendência operacional.</td></tr>';
}

export async function carregarPainel() {
    const alvo = document.getElementById('painel-pendencias');
    if (!alvo) return;
    try { renderizar(await requisicaoAeri('/api/painel')); }
    catch (erro) { alvo.innerHTML = `<tr><td colspan="5" class="rotina-vazio">${escaparHtml(erro.message)}</td></tr>`; }
}

export function iniciarPainel() {
    document.getElementById('btn-atualizar-painel')?.addEventListener('click', carregarPainel);
}
