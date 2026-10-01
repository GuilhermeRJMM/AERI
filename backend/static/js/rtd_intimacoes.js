import {escaparHtml} from './util.js';

export function temNovidadeRtd(item) {
    return (item.rtd || []).some(p => p.novo);
}

export function ordenarNovidadesRtd(a, b) {
    const prioridade = Number(temNovidadeRtd(b)) - Number(temNovidadeRtd(a));
    if (prioridade) return prioridade;
    if (!temNovidadeRtd(a)) return 0;
    const data = item => Math.max(0, ...(item.rtd || []).filter(p => p.novo).map(p => Date.parse(p.alteradoEm) || 0));
    return data(b) - data(a);
}

export function resumoRtd(item) {
    return (item.rtd || []).map(p => `<small class="rtd-resumo ${p.novo ? 'rtd-novo' : ''}">${p.novo ? '● Novo no RTD: ' : 'RTD: '}${escaparHtml(p.situacao)}${p.erro ? ' · Falha na atualização' : ''}</small>`).join('');
}

export function detalhesRtd(item) {
    if (!(item.rtd || []).length) return '';
    return `<section class="rtd-detalhes"><h3>Diligências RTD</h3><p>Acompanhamento da central, separado do andamento interno.</p>${item.rtd.map(p => {
        const dados = p.dados || {};
        const data = valor => valor ? escaparHtml(String(valor).replace('T', ' ').slice(0, 19)) : '—';
        return `<article class="rtd-pedido ${p.novo ? 'rtd-novo' : ''}">
            <strong>RTD ${escaparHtml(p.protocolo)} · ${escaparHtml(p.situacao)}</strong>
            <p>Situação na central: ${data(dados.DataSituacao)}${dados.ValorOrcamento != null ? ` · Orçamento: ${new Intl.NumberFormat('pt-BR', {style:'currency', currency:'BRL'}).format(dados.ValorOrcamento)}` : ''}</p>
            ${dados.DataDiligencia ? `<p>Diligência: ${data(dados.DataDiligencia)} · ${dados.DiligenciaPositiva === true ? 'Positiva' : dados.DiligenciaPositiva === false ? 'Negativa' : 'Resultado não informado'}</p>` : ''}
            ${p.erro ? `<p role="alert">${escaparHtml(p.erro)}</p>` : ''}
            ${['CONFLITO','IN_AMBIGUO'].includes(p.vinculo) ? '<p role="alert">Referências do documento precisam de revisão. Vínculo anterior preservado.</p>' : ''}
            ${p.novo ? `<button type="button" data-acao="rtd-lido" data-rtd="${escaparHtml(p.protocolo)}" data-versao="${p.versao}">Marcar atualização como vista</button>` : '<small>Atualização vista por você</small>'}
            <details><summary>Histórico do RTD</summary><ul>${(p.eventos || []).map(e => `<li>${data(e.criado_em)}: ${e.anterior?.Situacao === e.atual?.Situacao ? `Dados/documentação atualizados · ${escaparHtml(e.atual?.Situacao)}` : `${escaparHtml(e.anterior?.Situacao || 'Primeira consulta')} → ${escaparHtml(e.atual?.Situacao || 'Atualizado')}`}</li>`).join('')}</ul></details>
        </article>`;
    }).join('')}</section>`;
}
