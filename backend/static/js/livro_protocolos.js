import {escaparHtml} from './util.js';
import {requisicaoAeri} from './api.js?v=20260824-csrf-v1';

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
    document.getElementById('btn-livroproto-pdf').disabled = false;
    document.getElementById('livroproto-dropzone').classList.add('com-arquivo');
}

function formatarDataIso(valor) {
    const data = String(valor || '').slice(0, 10);
    const partes = data.split('-');
    return partes.length === 3 ? `${partes[2]}/${partes[1]}/${partes[0]}` : '—';
}

function dataLocalIso(data) {
    const ano = data.getFullYear();
    const mes = String(data.getMonth() + 1).padStart(2, '0');
    const dia = String(data.getDate()).padStart(2, '0');
    return `${ano}-${mes}-${dia}`;
}

async function analisarLivroProtocolosPdf() {
    if (!arquivoLivroProto) return;
    const botao = document.getElementById('btn-livroproto-pdf');
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
        botao.textContent = 'Conferir pelo PDF';
    }
}

async function analisarLivroProtocolosPorData() {
    const campo = document.getElementById('livroproto-data');
    const botao = document.getElementById('btn-livroproto-data');
    const resultado = document.getElementById('livroproto-resultado');
    if (!campo.value) return;
    botao.disabled = true;
    botao.textContent = 'Consultando três períodos...';
    resultado.innerHTML = `<div class="incra-loading">Localizando os protocolos apresentados e registrados em ${formatarDataIso(campo.value)} e conferindo os atos na Tri7…</div>`;
    try {
        resultadoLivroProto = await requisicaoAeri('/api/livro-protocolos/analisar-data', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({data: campo.value}),
        });
        renderizarLivroProtocolos('TODOS');
    } catch (erro) {
        resultado.innerHTML = `<div class="incra-erro">${escaparHtml(erro.message || 'Não foi possível consultar o Livro pela data.')}</div>`;
    } finally {
        botao.disabled = false;
        botao.textContent = 'Analisar o dia';
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
    return `<ul class="livroproto-ocorrencias">${item.ocorrencias.map(ocorrencia => {
        const perfil = document.body.dataset.perfil;
        const podeConfirmar = ['ADMIN', 'SUBSTITUTO'].includes(perfil)
            && ocorrencia.regra === 'NATUREZA_TITULO'
            && ocorrencia.permiteExcecao === true
            && ocorrencia.tituloOriginal
            && ocorrencia.naturezaOriginal;
        const botao = podeConfirmar ? `
            <button type="button" class="livroproto-confirmar-excecao" data-numero="${escaparHtml(item.numero)}"
                data-titulo="${escaparHtml(ocorrencia.tituloOriginal)}" data-natureza="${escaparHtml(ocorrencia.naturezaOriginal)}">
                Cadastrar equivalência exata
            </button>` : '';
        return `<li class="livroproto-gravidade-${ocorrencia.gravidade.toLowerCase()}">${escaparHtml(ocorrencia.descricao)}${botao}</li>`;
    }).join('')}</ul>`;
}

async function confirmarExcecaoNatureza(botao) {
    const numero = botao.dataset.numero;
    const tituloOriginal = botao.dataset.titulo;
    const naturezaOriginal = botao.dataset.natureza;
    const confirmado = window.confirm(
        `Esta equivalência valerá somente quando os dois textos abaixo aparecerem juntos em outro protocolo:\n\n`
        + `Título: ${tituloOriginal}\nNatureza: ${naturezaOriginal}\n\nConfirmar essa equivalência exata?`,
    );
    if (!confirmado) return;
    botao.disabled = true;
    botao.textContent = 'Confirmando...';
    try {
        await requisicaoAeri('/api/livro-protocolos/excecoes', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({tituloOriginal, naturezaOriginal}),
        });
        // Remove só da linha clicada (o item já visível na tela); pares
        // iguais em outras linhas desta mesma análise só somem na próxima
        // vez que o Livro de Protocolos for conferido.
        const protocolo = resultadoLivroProto?.protocolos.find(item => item.numero === numero);
        if (protocolo) {
            protocolo.ocorrencias = protocolo.ocorrencias.filter(ocorrencia => !(
                ocorrencia.regra === 'NATUREZA_TITULO'
                && ocorrencia.tituloOriginal === tituloOriginal
                && ocorrencia.naturezaOriginal === naturezaOriginal
            ));
        }
        const filtroAtivo = document.querySelector('.incra-filtro.active')?.dataset.filtro || 'TODOS';
        renderizarLivroProtocolos(filtroAtivo);
    } catch (erro) {
        alert(erro.message);
        botao.disabled = false;
        botao.textContent = 'Cadastrar equivalência exata';
    }
}

// A conferência do dia também atualiza no índice de buscas o que foi
// registrado, para não ser preciso descobrir à mão o que mudou e revisar
// matrícula por matrícula.
function avisoAtualizacao(atualizacao) {
    if (!atualizacao) return '';
    const partes = [];
    if (atualizacao.matriculas) {
        partes.push(`${atualizacao.matriculas} matrícula(s)`
            + (atualizacao.matriculasAlteradas ? ` — ${atualizacao.matriculasAlteradas} com alteração` : ''));
    }
    if (atualizacao.registrosAuxiliares) {
        partes.push(`${atualizacao.registrosAuxiliares} registro(s) auxiliar(es)`);
    }
    if (!partes.length && !atualizacao.falhas) {
        return '<p class="livroproto-atualizacao">Nenhum registro novo para atualizar no índice de buscas.</p>';
    }
    const falhas = atualizacao.falhas
        ? ` <b>${atualizacao.falhas} não atualizou</b> (${escaparHtml((atualizacao.numerosComFalha || []).join(', '))})`
        : '';
    return `<p class="livroproto-atualizacao">Índice de buscas atualizado: ${partes.join(' e ')}.${falhas}</p>`;
}

function renderizarLivroProtocolos(filtro) {
    if (!resultadoLivroProto) return;
    const resumo = resultadoLivroProto.resumo;
    const linhas = itensLivroProto(filtro).map(item => `
        <tr>
            <td><strong>${escaparHtml(item.numeroFormatado)}</strong><small>${escaparHtml(formatarDataIso(item.data))}</small></td>
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
        <div class="incra-resumo livroproto-resumo">
            <div><strong>${resumo.total}</strong><span>${resultadoLivroProto.fonte === 'PDF' ? 'Protocolos na folha' : 'Protocolos do dia'}</span></div>
            <div><strong>${resumo.conferidos}</strong><span>Conferidos na Tri7</span></div>
            <div><strong>${resumo.totalOcorrencias}</strong><span>Ocorrências encontradas</span></div>
            <div><strong>${formatarDataIso(resultadoLivroProto.dataEsperada)}</strong><span>Data analisada</span></div>
        </div>
        ${avisoAtualizacao(resultadoLivroProto.atualizacao)}
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
    const botaoFiltro = evento.target.closest('.incra-filtro');
    if (botaoFiltro) return renderizarLivroProtocolos(botaoFiltro.dataset.filtro);
    const botaoConfirmar = evento.target.closest('.livroproto-confirmar-excecao');
    if (botaoConfirmar) confirmarExcecaoNatureza(botaoConfirmar);
}

export function iniciarLivroProtocolos() {
    const campoData = document.getElementById('livroproto-data');
    const hoje = new Date();
    const ontem = new Date(hoje);
    ontem.setDate(ontem.getDate() - 1);
    campoData.max = dataLocalIso(hoje);
    campoData.value = dataLocalIso(ontem);
    document.getElementById('livroproto-pdf').addEventListener('change', selecionarPdfLivroProto);
    document.getElementById('btn-livroproto-data').addEventListener('click', analisarLivroProtocolosPorData);
    document.getElementById('btn-livroproto-pdf').addEventListener('click', analisarLivroProtocolosPdf);
    document.getElementById('livroproto-resultado').addEventListener('click', tratarAcaoResultado);
}
