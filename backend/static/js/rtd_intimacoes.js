import {escaparHtml} from './util.js';

const CAMPOS = [
    ['Situacao', 'Situação'],
    ['SituacaoId', 'Código do andamento RTD'],
    ['DataSituacao', 'Data da situação'],
    ['ValorOrcamento', 'Orçamento'],
    ['DataDiligencia', 'Data da diligência'],
    ['DiligenciaPositiva', 'Resultado da diligência'],
    ['QtdExigencia', 'Quantidade de exigências'],
    ['NumeroRegistro', 'Número do registro'],
    ['DataExcluido', 'Data de exclusão'],
    ['MotivoCancelamento', 'Motivo do cancelamento'],
    ['TemArquivoEnviado', 'Documento enviado'],
    ['TemArquivoRegistrado', 'Documento registrado'],
    ['TemCertidao', 'Certidão disponível'],
];

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

function formatarData(valor) {
    if (!valor) return '—';
    const texto = String(valor);
    const data = /^\d{4}-\d{2}-\d{2}$/.test(texto)
        ? new Date(`${texto}T12:00:00`)
        : new Date(texto);
    if (Number.isNaN(data.getTime())) return texto;
    return new Intl.DateTimeFormat('pt-BR', {
        dateStyle: 'short',
        ...(texto.includes('T') || texto.includes(':') ? {timeStyle: 'short'} : {}),
    }).format(data);
}

function exibirValor(campo, valor) {
    if (valor == null || valor === '') return '—';
    if (campo === 'ValorOrcamento') {
        const numero = Number(valor);
        return Number.isFinite(numero)
            ? new Intl.NumberFormat('pt-BR', {style: 'currency', currency: 'BRL'}).format(numero)
            : String(valor);
    }
    if (campo.startsWith('Data')) return formatarData(valor);
    if (campo === 'DiligenciaPositiva') return valor === true ? 'Positiva' : valor === false ? 'Negativa' : 'Não informado';
    if (['TemArquivoEnviado', 'TemArquivoRegistrado', 'TemCertidao'].includes(campo)) return valor ? 'Sim' : 'Não';
    return String(valor);
}

function diferencas(evento) {
    const anterior = evento?.anterior || {};
    const atual = evento?.atual || {};
    return CAMPOS.flatMap(([campo, rotulo]) => {
        if (JSON.stringify(anterior[campo] ?? null) === JSON.stringify(atual[campo] ?? null)) return [];
        return [{
            rotulo,
            anterior: exibirValor(campo, anterior[campo]),
            atual: exibirValor(campo, atual[campo]),
        }];
    });
}

function listaDiferencas(evento, compacta = false) {
    const alteracoes = diferencas(evento);
    if (!alteracoes.length) {
        return '<p class="rtd-sem-diferenca">A consulta foi atualizada, mas não houve mudança nos dados do pedido exibidos aqui. Pode ter sido uma atualização de vínculo ou documento.</p>';
    }
    const itens = alteracoes.map(item => `<li><strong>${item.rotulo}:</strong> ${escaparHtml(item.anterior)} <span aria-hidden="true">→</span> <strong>${escaparHtml(item.atual)}</strong></li>`).join('');
    return `<ul class="rtd-diferencas${compacta ? ' compacta' : ''}">${itens}</ul>`;
}

function dataCurta(valor) {
    return escaparHtml(formatarData(valor));
}

export function resumoRtd(item) {
    if (!(item.rtd || []).length) return '<span class="rtd-sem-vinculo">Sem protocolo RTD vinculado</span>';
    return item.rtd.map(p => {
        const atualizacao = p.eventos?.[0];
        const mudanca = atualizacao ? diferencas(atualizacao)[0] : null;
        const textoMudanca = mudanca ? `${mudanca.rotulo}: ${mudanca.anterior} → ${mudanca.atual}` : '';
        return `<div class="rtd-resumo-pedido ${p.novo ? 'rtd-novo' : ''}">
            <span class="rtd-resumo-cabecalho"><strong>RTD ${escaparHtml(p.protocolo)}</strong>${p.novo ? '<em>Atualização para conferir</em>' : ''}</span>
            <span>${escaparHtml(p.situacao || 'Aguardando consulta')}</span>
            ${textoMudanca ? `<small>${escaparHtml(textoMudanca)}</small>` : ''}
            <small>${p.erro ? 'Falha na atualização' : `Consultado: ${dataCurta(p.consultadoEm)}`}</small>
        </div>`;
    }).join('');
}

export function detalhesRtd(item) {
    if (!(item.rtd || []).length) return '';
    return `<section class="rtd-detalhes" aria-label="Acompanhamento externo da Central RTD">
        <div class="rtd-detalhes-cabecalho"><div><span class="rtd-origem">CENTRAL RTD · DADO EXTERNO</span><h3>Acompanhamento RTD</h3></div><p>Este andamento vem da Central RTD e não altera a fase nem as conferências internas do AERI.</p></div>
        ${item.rtd.map(p => {
            const dados = p.dados || {};
            const dataUltimaMudanca = p.eventos?.[0]?.criado_em || p.alteradoEm;
            return `<article class="rtd-pedido ${p.novo ? 'rtd-novo' : ''}">
                <div class="rtd-pedido-titulo"><strong>Protocolo RTD ${escaparHtml(p.protocolo)}</strong><span class="rtd-situacao-atual">${escaparHtml(p.situacao || 'Aguardando consulta')}</span></div>
                <div class="rtd-metadados"><span>Última consulta: <strong>${dataCurta(p.consultadoEm)}</strong></span><span>Dados alterados: <strong>${dataCurta(dataUltimaMudanca)}</strong></span></div>
                ${p.novo ? '<p class="rtd-aviso-novo">Há uma atualização que ainda não foi marcada como vista por você.</p>' : '<p class="rtd-aviso-visto">Atualização vista por você.</p>'}
                ${p.eventos?.length ? `<div class="rtd-o-que-mudou"><h4>O que mudou na última atualização</h4>${listaDiferencas(p.eventos[0])}</div>` : '<p>Aguardando a primeira atualização da Central.</p>'}
                ${dados.ValorOrcamento != null ? `<p><strong>Orçamento atual:</strong> ${escaparHtml(exibirValor('ValorOrcamento', dados.ValorOrcamento))}</p>` : ''}
                ${dados.DataDiligencia ? `<p><strong>Diligência:</strong> ${dataCurta(dados.DataDiligencia)} · ${escaparHtml(exibirValor('DiligenciaPositiva', dados.DiligenciaPositiva))}</p>` : ''}
                ${p.erro ? `<p class="rtd-alerta" role="alert">${escaparHtml(p.erro)}</p>` : ''}
                ${['CONFLITO', 'IN_AMBIGUO'].includes(p.vinculo) ? '<p class="rtd-alerta" role="alert">O protocolo ou documento precisa de revisão. O vínculo anterior foi preservado.</p>' : ''}
                ${p.novo ? `<button type="button" data-acao="rtd-lido" data-rtd="${escaparHtml(p.protocolo)}" data-versao="${p.versao}">Marcar atualização como conferida</button>` : ''}
                <details><summary>Ver histórico de atualizações</summary><ol class="rtd-historico">${(p.eventos || []).map(evento => `<li><time>${dataCurta(evento.criado_em)}</time>${listaDiferencas(evento, true)}</li>`).join('') || '<li>Não há atualizações anteriores registradas.</li>'}</ol></details>
            </article>`;
        }).join('')}
    </section>`;
}
