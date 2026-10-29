import {requisicaoAeri} from './api.js?v=20260902-arquivo-v1';
import {baixarArquivo, escaparHtml, hojeLocal} from './util.js';
import {temNovidadeRtd, ordenarNovidadesRtd, resumoRtd, detalhesRtd, carregarDocumentosRtd} from './rtd_intimacoes.js?v=20261019-protocolo-rtd-visivel-v1';
import {abrirDocumentosIntimacao, iniciarDocumentosIntimacao} from './intimacao_documentos.js?v=20261009-v1';

let intimacoes = [];
const intimacoesPendentes = new Set();
const detalhesAbertos = new Set();
const historicosOperacionais = new Map();
let intimacaoCheckId = null;
let faseAtiva = 'TODAS';
const FASES_INTIMACAO = ['INTIMACAO', 'EDITAL', 'CONSOLIDACAO'];
let filtroSituacao = 'TODAS';
let exibindoLixeira = false;
let filtroFila = 'TODAS';
let intimacaoSelecionadaId = null;
let mostrandoFormularioAndamentoId = null;
const rascunhosConferencia = new Map();
let filaConferenciaAtual = [];
let avisoMesa = '';
let deslocamentoSemanaAgenda = 0;
const enviosRtdPorIntimacao = new Map();
const enviosRtdCarregando = new Set();
let envioRtdEmCurso = false;
let extracaoRtdEmCurso = false;
let versaoExtracaoRtd = 0;
let filaRtdSeparada = null;
let filaRtdDosOriginais = false;
let indiceFilaRtdSeparada = 0;
let filaRtdFinalizada = false;
let intimacaoEnvioRtdId = null;
let envioRtdConcluido = false;
let uploadRtdAtual = null;
let uploadRtdController = null;
let arquivoRtdPendente = null;
let exclusaoRtdIntimacaoId = null;
let exclusaoRtdEmCurso = false;
const LIMITE_PDF_RTD = 25 * 1024 * 1024;

function opcoesJsonRtd(dados, signal) {
    return {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(dados), signal};
}

async function urlTemporariaRtd(uploadId, operacao, signal) {
    return requisicaoAeri('/api/rtd-intimacoes/uploads/signed-url',
        opcoesJsonRtd({upload_id:uploadId, operacao}, signal));
}

async function removerUploadRtd(upload = uploadRtdAtual) {
    if (!upload?.id) return;
    if (uploadRtdAtual?.id === upload.id) uploadRtdAtual = null;
    try {
        await urlTemporariaRtd(upload.id, 'delete');
    } catch (_erro) {
        // O varredor diário elimina uploads abandonados se a janela fechar sem rede.
    }
}

function novaChaveOperacaoRtd() {
    return globalThis.crypto?.randomUUID?.()
        || 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, letra => {
            const numero = Math.random() * 16 | 0;
            return (letra === 'x' ? numero : (numero & 0x3 | 0x8)).toString(16);
        });
}

function pode(permissao) {
    return ['ADMIN', 'SUBSTITUTO'].includes(document.body.dataset.perfil) || Boolean(window.aeriPermissoes?.[permissao]);
}

function cargoAdministrativo() {
    return ['ADMIN', 'SUBSTITUTO'].includes(document.body.dataset.perfil);
}

function somenteAdm() {
    return document.body.dataset.perfil === 'ADMIN';
}

function diasDesde(data) {
    if (!data) return null;
    const hoje = new Date(`${hojeLocal()}T00:00:00`);
    const referencia = new Date(`${data}T00:00:00`);
    return Math.max(0, Math.floor((hoje - referencia) / 86400000));
}

function situacaoIntimacao(item) {
    return item.situacaoConferencia || {classe:'cinza', rotulo:'Aguardando', detalhe:'Atualize a lista para conferir', ordem:2};
}

function fasePorAndamento(nomeAndamento, faseAtual = 'INTIMACAO') {
    const texto = String(nomeAndamento || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
    if (texto.includes('consolida') || texto.includes('intimacao positiva')) return 'CONSOLIDACAO';
    if (texto.includes('edital') && faseAtual !== 'CONSOLIDACAO') return 'EDITAL';
    return FASES_INTIMACAO.includes(faseAtual) ? faseAtual : 'INTIMACAO';
}

function formatarDataRotina(data) {
    if (!data) return '—';
    return new Intl.DateTimeFormat('pt-BR').format(new Date(`${data}T12:00:00`));
}

function normalizarBuscaIntimacao(valor) {
    return String(valor || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().trim().replace(/\s+/g, ' ');
}

function dataIsoLocal(data) {
    return `${data.getFullYear()}-${String(data.getMonth() + 1).padStart(2, '0')}-${String(data.getDate()).padStart(2, '0')}`;
}

function inicioSemanaAgenda() {
    const hoje = new Date(`${hojeLocal()}T12:00:00`);
    hoje.setDate(hoje.getDate() - ((hoje.getDay() + 6) % 7) + deslocamentoSemanaAgenda * 7);
    return hoje;
}

function renderizarAgendaIntimacoes() {
    const periodo = document.getElementById('rotina-agenda-periodo');
    const metricas = document.getElementById('rotina-agenda-metricas');
    const dias = document.getElementById('rotina-agenda-dias');
    if (!periodo || !metricas || !dias) return;
    if (exibindoLixeira) {
        periodo.textContent = 'Intimações ativas';
        metricas.innerHTML = '<span class="rotina-agenda-metrica">A agenda não inclui itens enviados à lixeira.</span>';
        dias.innerHTML = '<p class="rotina-agenda-vazia">Volte às intimações ativas para consultar os prazos.</p>';
        return;
    }

    const hoje = hojeLocal();
    const comPrazo = intimacoes.filter(item => /^\d{4}-\d{2}-\d{2}$/.test(item.dataCertificacao || ''));
    const inicio = inicioSemanaAgenda();
    const fim = new Date(inicio);
    fim.setDate(fim.getDate() + 6);
    periodo.textContent = `${formatarDataRotina(dataIsoLocal(inicio))} – ${formatarDataRotina(dataIsoLocal(fim))}`;
    const semana = comPrazo.filter(item => item.dataCertificacao >= dataIsoLocal(inicio) && item.dataCertificacao <= dataIsoLocal(fim));
    const atrasados = comPrazo.filter(item => item.dataCertificacao < hoje).length;
    const semPrazo = intimacoes.length - comPrazo.length;
    metricas.innerHTML = [
        `<span class="rotina-agenda-metrica"><strong>${intimacoes.length}</strong> INs ativos na conferência diária</span>`,
        `<span class="rotina-agenda-metrica"><strong>${semana.length}</strong> prazos nesta semana</span>`,
        `<span class="rotina-agenda-metrica alerta"><strong>${atrasados}</strong> com data anterior a hoje</span>`,
        `<span class="rotina-agenda-metrica"><strong>${semPrazo}</strong> sem prazo calculado</span>`,
    ].join('');

    const nomesDias = ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom'];
    dias.innerHTML = nomesDias.map((nome, indice) => {
        const data = new Date(inicio);
        data.setDate(data.getDate() + indice);
        const iso = dataIsoLocal(data);
        const compromissos = comPrazo.filter(item => item.dataCertificacao === iso)
            .sort((a, b) => a.protocolo.localeCompare(b.protocolo));
        const lista = compromissos.length
            ? compromissos.map(item => `<button type="button" class="rotina-agenda-in" data-agenda-intimacao="${escaparHtml(item.id)}" title="Abrir ${escaparHtml(item.protocolo)}">${escaparHtml(item.protocolo)}</button>`).join('')
            : '<span class="rotina-agenda-sem-prazo">Sem prazo</span>';
        return `<article class="rotina-agenda-dia ${iso === hoje ? 'hoje' : ''} ${compromissos.length ? 'com-itens' : ''}">
            <div class="rotina-agenda-dia-cabecalho"><span>${nome}</span><strong>${String(data.getDate()).padStart(2, '0')}</strong><small>${new Intl.DateTimeFormat('pt-BR', {month:'short'}).format(data).replace('.', '')}</small></div>
            <div class="rotina-agenda-dia-itens">${lista}</div>
            ${compromissos.length ? `<span class="rotina-agenda-contagem">${compromissos.length} ${compromissos.length === 1 ? 'prazo' : 'prazos'}</span>` : ''}
        </article>`;
    }).join('');
}

function correspondeBuscaIntimacao(item, termo) {
    if (!termo) return true;
    const valores = [
        item.protocolo, item.credor, item.devedor, item.nomeAndamento, item.certidaoDecursoPrazo,
        ...(item.fase === 'INTIMACAO' ? [item.protocoloRtd, item.numeroOsTri7, item.protocoloTri7,
            ...(item.rtd || []).flatMap(p => [p.protocolo, p.situacao])] : []),
    ];
    const alvo = normalizarBuscaIntimacao(termo);
    const alvoCompacto = alvo.replace(/[^a-z0-9]/g, '');
    return valores.some(valor => {
        const campo = normalizarBuscaIntimacao(valor);
        return campo.includes(alvo) || (alvoCompacto && campo.replace(/[^a-z0-9]/g, '').includes(alvoCompacto));
    });
}

function formatarMoeda(valor) {
    const numero = Number(valor);
    if (!Number.isFinite(numero)) return '—';
    return new Intl.NumberFormat('pt-BR', {style:'currency', currency:'BRL'}).format(numero);
}

function valorOuTraco(valor) {
    return valor ? escaparHtml(valor) : '—';
}

function renderizarCabecalho() {
    const titulos = [
        'Situação AERI', 'Protocolo', 'Credor', 'Devedor', 'Andamento interno do AERI',
        'Data do andamento AERI', 'RTD · somente fase inicial', 'Pasta', 'Ações',
    ];
    const tabela = document.querySelector('.rotina-table');
    tabela.classList.remove('rotina-table-fase-inicial');
    document.getElementById('rotina-cabecalho').innerHTML = titulos.map(titulo => `<th>${titulo}</th>`).join('');
}

function botaoPastaIntimacao(item, comRotulo = false) {
    const titulo = `Abrir pasta de ${item.protocolo}`;
    return `<button class="rotina-folder-btn ativo" data-acao="abrir-pasta" data-protocolo="${escaparHtml(item.protocolo)}" title="${escaparHtml(titulo)}" aria-label="${escaparHtml(titulo)}">
        <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M3 7.5A2.5 2.5 0 0 1 5.5 5H10l2 2h6.5A2.5 2.5 0 0 1 21 9.5v7A2.5 2.5 0 0 1 18.5 19h-13A2.5 2.5 0 0 1 3 16.5z"/>
        </svg>
        ${comRotulo ? '<span>Abrir pasta</span>' : ''}
    </button>`;
}

function acoesIntimacao(item, incluirDetalhes = false) {
    const pendente = intimacoesPendentes.has(item.id);
    if (exibindoLixeira) return cargoAdministrativo()
        ? `<div class="rotina-row-actions"><button data-acao="restaurar" data-id="${item.id}">Restaurar</button></div>`
        : '<span class="rotina-total">Somente leitura</span>';
    const disponiveis = [
        incluirDetalhes ? `<button class="rotina-detalhes-btn" data-acao="detalhes" data-id="${item.id}" aria-expanded="${detalhesAbertos.has(item.id)}">${detalhesAbertos.has(item.id) ? 'Fechar detalhes' : 'Detalhes'}</button>` : '',
        pode('conferir_intimacoes') ? `<button class="rotina-check" data-acao="conferir" data-id="${item.id}" title="Registrar conferência de hoje" ${pendente ? 'disabled' : ''}>${pendente ? 'Salvando...' : '✓ Check'}</button>` : '',
        pode('alterar_intimacoes') ? `<button data-acao="editar" data-id="${item.id}" title="Editar">Editar</button>` : '',
        cargoAdministrativo() ? `<button class="perigo" data-acao="excluir" data-id="${item.id}" title="Excluir">Excluir</button>` : '',
    ].filter(Boolean).join('');
    return disponiveis ? `<div class="rotina-row-actions">${disponiveis}</div>` : '<span class="rotina-total">Somente leitura</span>';
}

function rotuloFaseIntimacao(fase) {
    return ({INTIMACAO:'Intimação', EDITAL:'Edital', CONSOLIDACAO:'Consolidação'})[fase] || 'Intimação';
}

function protocolosRtdIntimacao(item) {
    if (item?.fase !== 'INTIMACAO') return [];
    const vinculados = Array.isArray(item.rtd) ? item.rtd.map(pedido => pedido?.protocolo) : [];
    return [...new Set([item.protocoloRtd, ...vinculados]
        .map(valor => String(valor || '').trim())
        .filter(Boolean))];
}

function proximaAcaoIntimacao(item) {
    if (temNovidadeRtd(item)) return {
        titulo:'Confira a atualização recebida no RTD',
        texto:'Compare a situação e os documentos do RTD com o andamento registrado no AERI. Depois, abra os detalhes para marcar a atualização como vista e registrar a conferência diária, se aplicável.',
        botao:'Revisar RTD e documentos', acao:'detalhes',
    };
    const situacao = situacaoIntimacao(item);
    if (item.fase !== 'INTIMACAO') {
        const etapa = item.fase === 'EDITAL' ? 'edital' : 'consolidação';
        if (situacao.classe !== 'verde' && pode('conferir_intimacoes')) return {
            titulo:`Confira o andamento da fase de ${etapa}`,
            texto:`Verifique as providências e os prazos do protocolo conforme o manual de ${etapa}; depois, registre a conferência no AERI.`,
            botao:'Conferir agora', acao:'conferir',
        };
        if (situacao.classe !== 'verde') return {
            titulo:'Conferência interna pendente',
            texto:`Este protocolo está na fase de ${etapa}. Consulte os detalhes e siga as providências e os prazos previstos no manual.`,
            botao:'Ver detalhes', acao:'detalhes',
        };
        return {
            titulo:`Acompanhe a fase de ${etapa}`,
            texto:`Consulte os detalhes do protocolo e siga as providências e os prazos previstos no manual de ${etapa}.`,
            botao:'Abrir detalhes', acao:'detalhes',
        };
    }
    if (situacao.classe !== 'verde' && pode('conferir_intimacoes')) return {
        titulo:'Faça a conferência diária deste IN',
        texto:'Consulte este protocolo no Ofício Eletrônico. Se houver andamento novo, registre-o no AERI; se não houver, confirme que o andamento atual permanece.',
        botao:'Conferir agora', acao:'conferir',
    };
    if (situacao.classe !== 'verde') return {
        titulo:'Conferência diária pendente',
        texto:'Este protocolo ainda precisa ser conferido por alguém com permissão para registrar a rotina. Consulte os detalhes para acompanhar a situação.',
        botao:'Ver detalhes', acao:'detalhes',
    };
    return {
        titulo:'Conferência de hoje concluída',
        texto:'Acompanhe novas movimentações e retome a conferência na próxima rotina diária.',
        botao:'Abrir detalhes', acao:'detalhes',
    };
}

function renderizarCartaoFila(item) {
    const situacao = situacaoIntimacao(item);
    const novidade = temNovidadeRtd(item);
    const selecionado = item.id === intimacaoSelecionadaId;
    const protocolosRtd = protocolosRtdIntimacao(item);
    return `<article class="rotina-fila-cartao ${selecionado ? 'selecionado' : ''} ${situacao.classe}">
        <button type="button" class="rotina-fila-selecionar" data-selecionar-intimacao="${escaparHtml(item.id)}" aria-pressed="${selecionado}">
            <span class="rotina-fila-conteudo">
                <span class="rotina-fila-linha"><strong>${escaparHtml(item.protocolo)}</strong><span class="rotina-fila-etiquetas"><span class="rotina-fila-fase fase-${String(item.fase || '').toLowerCase()}">${escaparHtml(rotuloFaseIntimacao(item.fase))}</span><span class="rotina-fila-situacao ${novidade ? 'rtd' : situacao.classe}">${novidade ? 'Nova movimentação RTD' : escaparHtml(situacao.rotulo)}</span></span></span>
                <span class="rotina-fila-partes">${escaparHtml(item.credor)} <i>·</i> ${escaparHtml(item.devedor)}</span>
                <span class="rotina-fila-andamento">${escaparHtml(item.nomeAndamento || 'Andamento não informado')}</span>
                ${item.fase === 'INTIMACAO' ? `<span class="rotina-fila-protocolo-rtd"><strong>Protocolo${protocolosRtd.length === 1 ? '' : 's'} RTD:</strong> ${protocolosRtd.length ? protocolosRtd.map(escaparHtml).join(' · ') : 'não cadastrado'}</span>` : ''}
                <span class="rotina-fila-data">${formatarDataRotina(item.ultimoAndamento)}${item.ultimaConferencia ? ` · Conferida em ${formatarDataRotina(item.ultimaConferencia)}` : ' · Ainda sem conferência'}</span>
            </span>
            <span class="rotina-fila-chevron" aria-hidden="true">›</span>
        </button>
    </article>`;
}

function renderizarFocoIntimacao(item, fila) {
    const foco = document.getElementById('rotina-foco');
    if (!foco) return;
    if (!item) {
        foco.innerHTML = '<div class="rotina-in-vazio"><h2>Nenhum IN encontrado</h2><p>Confira a busca ou os filtros de fase. A lista diária inclui todos os INs ativos.</p></div>';
        return;
    }
    const situacao = situacaoIntimacao(item);
    const novidade = temNovidadeRtd(item);
    const protocolosRtd = protocolosRtdIntimacao(item);
    const indice = Math.max(0, fila.findIndex(registro => registro.id === item.id)) + 1;
    const total = fila.length;
    const fase = item.fase || 'INTIMACAO';
    const podeExcluirProtocolosRtd = somenteAdm() && fase === 'INTIMACAO'
        && (protocolosRtd.length > 0 || Boolean(item.protocoloRtd));
    const status = novidade ? 'Novidade do RTD' : situacao.rotulo;
    const classeStatus = novidade ? 'amarelo' : situacao.classe;
    const conferidoHoje = situacao.classe === 'verde' && !novidade;
    const pendente = intimacoesPendentes.has(item.id);
    const somenteLeitura = exibindoLixeira || !pode('conferir_intimacoes');
    const avisoRtd = novidade ? `<div class="rotina-in-aviso-rtd"><strong>O AERI detectou uma novidade no RTD.</strong> Compare o andamento e consulte o histórico antes de concluir a conferência.<br><button type="button" data-acao="detalhes" data-id="${escaparHtml(item.id)}">Ver detalhes e documentos</button></div>` : '';
    const dadosRtd = fase === 'INTIMACAO' ? `<section class="rotina-in-protocolo-rtd" aria-label="Número do protocolo RTD"><span>${protocolosRtd.length === 1 ? 'Número do protocolo RTD' : 'Protocolos RTD vinculados a este IN'}</span>${protocolosRtd.length ? protocolosRtd.map((protocolo, posicao) => `<strong class="rotina-in-protocolo-item">${escaparHtml(protocolo)}</strong>`).join('') : '<strong>Não informado no AERI</strong>'}</section>` : '';
    const rascunho = rascunhosConferencia.get(item.id) || {modo:'', nome:'', data:hojeLocal()};
    const ativo = document.activeElement;
    const preservarFoco = ativo?.closest('[data-mesa-conferencia]')?.dataset.id === item.id
        ? {nome:ativo.name, valor:ativo.value, inicio:ativo.selectionStart, fim:ativo.selectionEnd} : null;
    const mudou = rascunho.modo === 'mudou';
    const desabilitar = pendente || !rascunho.modo || (rascunho.modo === 'igual' && conferidoHoje);
    const rotuloConfirmar = pendente ? 'Salvando conferência…'
        : mudou ? 'Salvar novo andamento e conferir'
        : rascunho.modo === 'igual' ? (conferidoHoje ? 'Conferência já registrada hoje' : 'Registrar conferência sem alteração')
        : 'Escolha o resultado da sua consulta';
    const botoesConferencia = somenteLeitura
        ? `<p class="mesa-somente-leitura">${exibindoLixeira ? 'Este IN está na lixeira. A restauração está disponível em Mais ações.' : 'Seu perfil permite consultar este IN, mas não registrar a conferência.'}</p>`
        : `<form class="mesa-editor" data-mesa-conferencia data-id="${escaparHtml(item.id)}">
            <fieldset ${pendente ? 'disabled' : ''}>
                <legend>Como está o andamento no Ofício?</legend>
                <div class="mesa-escolhas">
                    <label><input type="radio" name="tipoConferencia" value="igual" data-mesa-modo ${rascunho.modo === 'igual' ? 'checked' : ''} required><span><strong>Mesmo andamento</strong><small>Está igual ao registro do AERI.</small></span></label>
                    <label><input type="radio" name="tipoConferencia" value="mudou" data-mesa-modo ${mudou ? 'checked' : ''} required><span><strong>Novo andamento</strong><small>Encontrei uma movimentação diferente.</small></span></label>
                </div>
                <div class="mesa-novo-andamento" ${mudou ? '' : 'hidden'}>
                    <label><span>Novo andamento no Ofício</span><input id="rotina-in-novo-andamento" name="novoAndamento" maxlength="160" value="${escaparHtml(rascunho.nome)}" ${mudou ? 'required' : 'disabled'} placeholder="Digite exatamente o que aparece no Ofício"></label>
                    <label><span>Data desse andamento</span><input name="dataAndamento" type="date" value="${escaparHtml(rascunho.data)}" max="${hojeLocal()}" ${mudou ? 'required' : 'disabled'}></label>
                </div>
                <button type="submit" class="mesa-confirmar" ${desabilitar ? 'disabled' : ''}>${rotuloConfirmar}</button>
                <p class="mesa-ajuda">${mudou ? 'O novo andamento e sua data serão salvos junto com a conferência de hoje.' : 'Selecionar uma opção não salva nada. Confirme a conferência no botão acima.'}</p>
            </fieldset>
        </form>`;
    const botoesNavegacao = total > 1 ? `<div class="rotina-in-controles"><button type="button" data-foco-navegar="-1">← IN anterior</button><button type="button" data-foco-navegar="1">Próximo IN →</button></div>` : '';
    foco.innerHTML = `<article class="rotina-in-cartao">
        <div class="rotina-in-cabecalho"><div><span class="rotina-in-posicao">${escaparHtml(rotuloFaseIntimacao(fase).toLocaleUpperCase('pt-BR'))} · IN ${indice} DE ${total}</span><h2>${escaparHtml(item.protocolo)}</h2></div><span class="rotina-in-estado ${classeStatus}">${escaparHtml(status || 'Falta conferir')}</span></div>
        <div class="rotina-in-partes"><div class="rotina-in-dado"><span>Credor</span><strong>${escaparHtml(item.credor || 'Não informado')}</strong></div><div class="rotina-in-dado"><span>Devedor</span><strong>${escaparHtml(item.devedor || 'Não informado')}</strong></div></div>
        ${dadosRtd}
        ${avisoRtd}
        <div class="mesa-comparacao">
            <section class="mesa-referencia"><span class="mesa-rotulo">NO AERI</span><strong>${escaparHtml(item.nomeAndamento || 'Não informado')}</strong><small>Último andamento · ${formatarDataRotina(item.ultimoAndamento)}</small></section>
            <section class="mesa-consulta"><span class="mesa-rotulo">NO OFÍCIO ELETRÔNICO</span><strong>Consulte antes de registrar</strong><p>Compare o andamento deste IN com o registro ao lado.</p><a href="https://www.oficioeletronico.onr.org.br" target="_blank" rel="noopener noreferrer">Abrir Ofício Eletrônico ↗</a></section>
        </div>
        ${botoesConferencia}
        <div class="mesa-ferramentas"><button type="button" data-acao="detalhes" data-id="${escaparHtml(item.id)}" aria-expanded="${detalhesAbertos.has(item.id)}">${detalhesAbertos.has(item.id) ? 'Fechar histórico e documentos' : 'Histórico e documentos'}</button>${botaoPastaIntimacao(item, true)}${pode('alterar_intimacoes') && !exibindoLixeira ? `<button type="button" data-acao="editar" data-id="${escaparHtml(item.id)}">Editar cadastro</button>` : ''}${pode('alterar_intimacoes') && fase === 'INTIMACAO' && !exibindoLixeira ? `<button type="button" data-acao="novo-envio-rtd" data-id="${escaparHtml(item.id)}">Preparar envio ao RTD</button>` : ''}</div>
        ${botoesNavegacao}
        ${cargoAdministrativo() ? `<details class="rotina-in-mais-acoes"><summary>Mais ações administrativas</summary><div>${exibindoLixeira ? `<button type="button" data-acao="restaurar" data-id="${escaparHtml(item.id)}">Restaurar IN</button>` : `<button type="button" class="perigo" data-acao="excluir" data-id="${escaparHtml(item.id)}">Mover IN para a lixeira</button>`}${podeExcluirProtocolosRtd && !exibindoLixeira ? `<button type="button" class="rtd-exclusao-atalho" data-acao="excluir-protocolos-rtd" data-id="${escaparHtml(item.id)}">Remover protocolos RTD</button>` : ''}</div></details>` : ''}
        ${detalhesAbertos.has(item.id) ? `<div class="rotina-foco-detalhes">${detalhesFaseInicial(item)}</div>` : ''}
    </article>`;
    if (preservarFoco) {
        const campo = [...foco.querySelectorAll('[name]')].find(el => el.name === preservarFoco.nome
            && (el.type !== 'radio' || el.value === preservarFoco.valor));
        campo?.focus({preventScroll:true});
        if (campo?.type === 'text' && preservarFoco.inicio !== null) campo.setSelectionRange(preservarFoco.inicio, preservarFoco.fim);
    }
}

function renderizarCentralAcao(filtradas) {
    const lista = document.getElementById('rotina-fila');
    const contador = document.getElementById('rotina-total-fila');
    if (!lista) return;
    let fila = filtradas;
    if (filtroFila === 'PENDENTES') fila = fila.filter(item => situacaoIntimacao(item).classe !== 'verde');
    if (filtroFila === 'RTD') fila = fila.filter(temNovidadeRtd);
    filaConferenciaAtual = fila;
    const feedback = document.getElementById('mesa-feedback');
    if (feedback) { feedback.textContent = avisoMesa; feedback.hidden = !avisoMesa; }
    if (!fila.some(item => item.id === intimacaoSelecionadaId)) intimacaoSelecionadaId = fila[0]?.id || null;
    const selecionada = fila.find(item => item.id === intimacaoSelecionadaId) || null;
    const vazio = filtroFila === 'RTD'
        ? 'Nenhuma atualização nova do RTD nos protocolos que correspondem aos filtros.'
        : filtroFila === 'PENDENTES'
            ? 'Nenhum protocolo pendente de conferência nesta seleção.'
            : 'Nenhum protocolo corresponde à busca atual.';
    lista.innerHTML = fila.map(renderizarCartaoFila).join('') || `<div class="rotina-fila-vazia">${vazio}</div>`;
    if (contador) contador.textContent = `${fila.length} ${fila.length === 1 ? 'protocolo' : 'protocolos'}`;
    document.querySelectorAll('[data-fila-filtro]').forEach(botao => {
        const ativo = botao.dataset.filaFiltro === filtroFila;
        botao.classList.toggle('ativa', ativo);
        botao.setAttribute('aria-pressed', String(ativo));
    });
    renderizarFocoIntimacao(selecionada, fila);
}

function renderizarCoberturaIntimacao() {
    const painel = document.querySelector('.rotina-cobertura');
    if (painel) painel.hidden = exibindoLixeira;
    if (exibindoLixeira) return;
    const total = intimacoes.length;
    const conferidas = intimacoes.filter(item => situacaoIntimacao(item).classe === 'verde').length;
    const restantes = Math.max(0, total - conferidas);
    const percentual = total ? Math.round(conferidas / total * 100) : 0;
    const progresso = document.querySelector('.rotina-cobertura-trilho');
    const barra = document.getElementById('rotina-cobertura-barra');
    const contagem = document.getElementById('rotina-cobertura-contagem');
    const textoRestantes = document.getElementById('rotina-cobertura-restantes');
    const proximo = document.getElementById('btn-proximo-in-pendente');
    if (!progresso || !barra || !contagem || !textoRestantes || !proximo) return;
    contagem.textContent = `${conferidas} de ${total} conferidos hoje · ${percentual}%`;
    textoRestantes.textContent = restantes
        ? `${restantes} ${restantes === 1 ? 'IN ainda precisa' : 'INs ainda precisam'} de conferência`
        : total ? 'Conferência diária concluída para todos os INs ativos.' : 'Nenhum IN ativo na fila.';
    barra.style.width = `${percentual}%`;
    progresso.setAttribute('aria-valuenow', String(conferidas));
    progresso.setAttribute('aria-valuemax', String(total));
    proximo.disabled = !restantes;
    proximo.querySelector('strong').textContent = restantes ? 'Revisar próximo IN pendente' : 'Todos conferidos por hoje';
}

async function abrirProximoInPendente() {
    if (exibindoLixeira) {
        exibindoLixeira = false;
        const botaoLixeira = document.querySelector('[data-lixeira-intimacoes]');
        if (botaoLixeira) botaoLixeira.textContent = 'Lixeira';
        await carregarIntimacoes();
    }
    const pendente = intimacoes
        .filter(item => situacaoIntimacao(item).classe !== 'verde')
        .sort((a, b) => situacaoIntimacao(a).ordem - situacaoIntimacao(b).ordem || a.protocolo.localeCompare(b.protocolo))[0];
    if (!pendente) return;
    faseAtiva = 'TODAS';
    filtroSituacao = 'TODAS';
    filtroFila = 'PENDENTES';
    document.getElementById('busca-intimacao').value = '';
    document.getElementById('filtro-situacao-intimacao').value = 'TODAS';
    intimacaoSelecionadaId = pendente.id;
    renderizarIntimacoes();
    document.getElementById('rotina-central-acao').scrollIntoView({block:'start', behavior:'smooth'});
}

function navegarFocoIntimacao(direcao = 1) {
    const ids = [...document.querySelectorAll('#rotina-fila [data-selecionar-intimacao]')]
        .map(botao => botao.dataset.selecionarIntimacao);
    if (!ids.length) return;
    const atual = ids.indexOf(intimacaoSelecionadaId);
    const proximo = atual < 0 ? 0 : (atual + direcao + ids.length) % ids.length;
    intimacaoSelecionadaId = ids[proximo];
    mostrandoFormularioAndamentoId = null;
    renderizarIntimacoes();
}

function campoCard(rotulo, valor, classe = '') {
    return `<div class="rotina-card-campo ${classe}">
        <span>${rotulo}</span>
        <strong>${valor}</strong>
    </div>`;
}

function detalhesFaseInicial(item) {
    const historico = historicosOperacionais.get(item.id);
    const eventos = Array.isArray(historico)
        ? historico.map(evento => `<li><strong>${escaparHtml(evento.tipo)}</strong><span>${new Intl.DateTimeFormat('pt-BR', {dateStyle:'short', timeStyle:'short'}).format(new Date(evento.criado_em))} · ${escaparHtml(evento.usuario)}</span></li>`).join('')
        : '<li><span>Carregando histórico operacional…</span></li>';
    const envios = enviosRtdPorIntimacao.get(item.id) || [];
    const rotulosEnvio = {
        ENVIANDO: 'Envio em andamento', CRIADO: 'Enviado à Central',
        HOMOLOGACAO_OK: 'Teste aceito na homologação',
        CRIADO_REVISAR: 'Enviado · conferir protocolo e vínculo', INCERTO: 'Verificar na Central antes de reenviar',
        FALHA_ARQUIVO: 'Documento principal não enviado',
        FALHA_VALIDACAO: 'Revisar destino', RECUSADO: 'Central recusou o pedido',
    };
    const listaEnvios = envios.length
        ? `<ul class="rtd-envios-lista">${envios.map(envio => `<li><strong>${escaparHtml(rotulosEnvio[envio.estado] || envio.estado)}</strong>${envio.ambiente === 'homologacao' ? '<span class="rtd-envio-ambiente">HOMOLOGAÇÃO</span>' : ''}${envio.protocolo ? `<span>Protocolo ${escaparHtml(envio.protocolo)}</span>` : ''}${envio.erro ? `<small>${escaparHtml(envio.erro)}</small>` : ''}<time>${new Intl.DateTimeFormat('pt-BR', {dateStyle:'short', timeStyle:'short'}).format(new Date(envio.criadoEm))}</time></li>`).join('')}</ul>`
        : (enviosRtdCarregando.has(item.id) ? '<p>Carregando envios…</p>' : '<p>Nenhum envio feito pelo AERI.</p>');
    return `<div class="rotina-intimacao-detalhes">
        ${detalhesRtd(item)}
        <div class="rotina-detalhes-separador"><span>CONTROLE INTERNO DO AERI</span><h3>Fase e conferências internas</h3></div>
        <section class="rotina-card-grade rotina-card-identificacao">
            ${item.fase === 'INTIMACAO' ? campoCard('Protocolo RTD', valorOuTraco(item.protocoloRtd)) : ''}
            ${campoCard('N.º OS Tri7', valorOuTraco(item.numeroOsTri7))}
            ${campoCard('Protocolo Tri7', valorOuTraco(item.protocoloTri7))}
            ${campoCard('Certidão de Decurso de Prazo', valorOuTraco(item.certidaoDecursoPrazo), 'rotina-card-campo-largo')}
            ${campoCard('Devedor', escaparHtml(item.devedor), 'rotina-card-campo-total')}
        </section>
        <section class="rotina-card-grade rotina-card-andamento">
            ${campoCard('Data do Último Andamento', formatarDataRotina(item.ultimoAndamento))}
            ${campoCard('Último Andamento', escaparHtml(item.nomeAndamento || 'Não informado'), 'rotina-card-campo-largo')}
            ${campoCard('Data da Intimação', formatarDataRotina(item.dataIntimacao))}
            ${campoCard('Dias Úteis Certificação', formatarDataRotina(item.dataCertificacao))}
        </section>
        <section class="rotina-card-financeiro">
            ${campoCard('Valor pago pelo Cliente na ONR', formatarMoeda(item.valorPagoOnr))}
            ${campoCard('Valor Usado', formatarMoeda(item.valorUsado))}
            ${campoCard('Saldo na OS', formatarMoeda(item.saldoOs), 'rotina-card-saldo')}
        </section>
        ${pode('alterar_intimacoes') ? `<section class="rotina-documentos-acoes">
            <div><h3>Movimentação financeira</h3><p>Crédito, repasse e estorno são lançados sem sobrescrever o histórico.</p></div>
            <button type="button" data-acao="financeiro" data-id="${item.id}">Novo lançamento</button>
        </section>
        <section class="rotina-documentos-acoes">
            <div><h3>Checklist da desistência</h3><p>Pedido, documentos, signatário e nota permanecem registrados no protocolo.</p></div>
            <button type="button" data-acao="checklist" data-id="${item.id}">Atualizar checklist</button>
        </section>` : ''}
        ${pode('alterar_intimacoes') ? `<section class="rotina-documentos-acoes">
            <div>
                <h3>Documentos do processo</h3>
                <p>Lê os PDFs do processo e o arquivo "Pedido de Desistência" em "Recebido para Intimacao". A nota abre no Word para conferir o signatário no ITI.</p>
            </div>
            <button type="button" class="rotina-gerar-desistencia" data-acao="gerar-desistencia" data-protocolo="${escaparHtml(item.protocolo)}">
                Gerar nota de Desistência
            </button>
        </section>` : ''}
        ${pode('alterar_intimacoes') && item.fase === 'INTIMACAO' ? `<section class="rotina-documentos-acoes">
            <div><h3>Autuação e documentos da intimação</h3><p>Leia o ofício e a projeção, confira os dados e prepare os textos para os modelos da aba “Texto” da Tri7.</p></div>
            <button type="button" class="rotina-gerar-desistencia" data-acao="preparar-documentos-intimacao" data-id="${item.id}">Preparar documentos</button>
        </section>` : ''}
        ${item.fase === 'INTIMACAO' ? `<section class="rtd-envios-historico">
            <div class="rtd-envio-cabecalho"><div><span class="rtd-origem">SOLICITAÇÕES ENVIADAS PELO AERI</span><h3>Histórico de envios</h3></div>
                ${pode('alterar_intimacoes') && item.fase === 'INTIMACAO' ? `<button type="button" data-acao="novo-envio-rtd" data-id="${item.id}">Preparar notificação</button>` : ''}
            </div>
            ${listaEnvios}
            <p>Enviar uma notificação cria um novo pedido na Central RTD; isso não responde nem altera o andamento interno do AERI.</p>
        </section>` : ''}
        <section class="rotina-historico-operacional">
            <h3>Histórico operacional</h3>
            <ul>${eventos || '<li><span>Nenhum evento registrado.</span></li>'}</ul>
        </section>
    </div>`;
}

async function carregarHistoricoOperacional(id) {
    if (historicosOperacionais.has(id)) return;
    try {
        historicosOperacionais.set(id, await requisicaoAeri(`/api/intimacoes/${id}/historico`));
    } catch (erro) {
        historicosOperacionais.set(id, [{tipo:'ERRO', criado_em:new Date().toISOString(), usuario:erro.message}]);
    }
}

async function carregarEnviosRtd(id, forcar = false) {
    if (intimacoes.find(registro => registro.id === id)?.fase !== 'INTIMACAO') return;
    if (!forcar && (enviosRtdPorIntimacao.has(id) || enviosRtdCarregando.has(id))) return;
    enviosRtdCarregando.add(id);
    try {
        const dados = await requisicaoAeri(`/api/rtd-intimacoes/intimacao/${id}/envios`);
        enviosRtdPorIntimacao.set(id, dados.envios || []);
    } catch (_erro) {
        enviosRtdPorIntimacao.set(id, []);
    } finally {
        enviosRtdCarregando.delete(id);
    }
}

function novoCampoNotificado({copiarPessoa = false} = {}) {
    const lista = document.getElementById('rtd-notificados-lista');
    const atual = lista.querySelectorAll('[data-rtd-notificado]').length;
    if (atual >= 20) return;
    const origem = copiarPessoa ? lista.querySelector('[data-rtd-notificado]:last-of-type') : null;
    const indice = atual + 1;
    const bloco = document.createElement('section');
    bloco.className = 'rtd-notificado';
    bloco.dataset.rtdNotificado = '';
    bloco.innerHTML = `<div class="rtd-envio-secao-titulo"><h4>Destinatário/endereço ${indice}</h4>${indice > 1 ? '<button type="button" class="rtd-remover-notificado" data-remover-notificado>Remover</button>' : ''}</div>
        <div class="rtd-envio-linha">
            <label><span>Nome completo</span><input data-pessoa="Nome" maxlength="160" required></label>
            <label><span>CPF/CNPJ</span><input data-pessoa="CpfCnpj" maxlength="18" inputmode="numeric" required></label>
        </div>
        <div class="rtd-envio-endereco">
            <label><span>CEP</span><input data-endereco="CEP" maxlength="9" inputmode="numeric" required></label>
            <label><span>Logradouro</span><input data-endereco="Logradouro" maxlength="160" required></label>
            <label><span>Número</span><input data-endereco="Numero" maxlength="40" required></label>
            <label><span>Complemento</span><input data-endereco="Complemento" maxlength="100"></label>
            <label><span>Bairro</span><input data-endereco="Bairro" maxlength="100" required></label>
            <label><span>Cidade</span><input data-endereco="Cidade" maxlength="100" required></label>
            <label><span>Estado</span><input data-endereco="UF" maxlength="2" required></label>
        </div>`;
    lista.append(bloco);
    if (origem) {
        for (const campo of ['Nome', 'CpfCnpj']) {
            bloco.querySelector(`[data-pessoa="${campo}"]`).value = origem.querySelector(`[data-pessoa="${campo}"]`)?.value || '';
        }
    }
    return bloco;
}

function preencherParRtd(par) {
    const bloco = document.querySelector('#rtd-notificados-lista [data-rtd-notificado]');
    bloco.querySelector('[data-pessoa="Nome"]').value = par.pessoa.nome;
    bloco.querySelector('[data-pessoa="CpfCnpj"]').value = par.pessoa.cpf || par.pessoa.cnpj || '';
    for (const [chave, valor] of Object.entries(par.endereco)) {
        const input = bloco.querySelector(`[data-endereco="${chave}"]`);
        if (input) input.value = valor;
    }
    document.getElementById('rtd-destino-cidade').value = par.endereco.Cidade || 'Morrinhos';
    document.getElementById('rtd-destino-uf').value = par.endereco.UF || 'GO';
}

function atualizarFilaRtd() {
    const ativa = Array.isArray(filaRtdSeparada);
    document.getElementById('btn-adicionar-notificado-rtd').hidden = ativa;
    document.getElementById('btn-adicionar-endereco-rtd').hidden = ativa;
    document.getElementById('rtd-fila-indicador').hidden = !ativa;
    document.getElementById('rtd-ajuda-notificados').textContent = ativa
        ? 'Um envio por vez. Após a confirmação da Central, o AERI mostrará o próximo par de pessoa e endereço para nova revisão.'
        : 'Cadastre cada endereço como um destinatário separado. Se for a mesma pessoa em dois endereços, use o botão correspondente; os dados pessoais serão repetidos para conferência.';
    if (ativa) {
        const total = filaRtdSeparada.length;
        document.getElementById('rtd-fila-indicador').textContent = `Notificação ${indiceFilaRtdSeparada + 1} de ${total}: um devedor em um endereço por pedido.`;
        document.getElementById('btn-confirmar-rtd-notificacao').textContent = `Enviar ${indiceFilaRtdSeparada + 1} de ${total}`;
    }
}

function descartarPreparacaoEnvioRtd() {
    versaoExtracaoRtd += 1;
    uploadRtdController?.abort();
    uploadRtdController = null;
    if (uploadRtdAtual) void removerUploadRtd(uploadRtdAtual);
    arquivoRtdPendente = null;
    intimacaoEnvioRtdId = null;
    envioRtdConcluido = false;
    filaRtdSeparada = null;
    filaRtdDosOriginais = false;
    indiceFilaRtdSeparada = 0;
    filaRtdFinalizada = false;
}

function abrirEnvioRtd(id, paresRtd = null, dadosCredor = null) {
    const item = intimacoes.find(registro => registro.id === id);
    if (!item || item.fase !== 'INTIMACAO' || !pode('alterar_intimacoes')) return;

    const modal = document.getElementById('modal-rtd-notificacao');
    // Reabrir o mesmo IN sempre retoma a preparação desta aba, inclusive
    // depois de um envio concluído. Uma nova remessa precisa ser explícita.
    if (intimacaoEnvioRtdId === id && !paresRtd?.length) {
        modal.classList.add('aberta');
        return;
    }
    if (intimacaoEnvioRtdId === id && !envioRtdConcluido) {
        modal.classList.add('aberta');
        return;
    }
    if (intimacaoEnvioRtdId && !envioRtdConcluido) {
        if (envioRtdEmCurso || extracaoRtdEmCurso) {
            alert('Aguarde a etapa atual terminar antes de trocar de intimação.');
            return;
        }
        const enviados = filaRtdSeparada ? indiceFilaRtdSeparada : 0;
        const aviso = enviados
            ? `${enviados} notificação(ões) já confirmada(s) continuam registradas. Somente a preparação ainda não enviada será descartada. Quer prosseguir?`
            : 'A preparação desta notificação será descartada. Nenhum envio concluído será desfeito. Quer prosseguir?';
        if (!confirm(aviso)) return;
    }
    if (intimacaoEnvioRtdId) descartarPreparacaoEnvioRtd();

    versaoExtracaoRtd += 1;
    extracaoRtdEmCurso = false;
    document.getElementById('form-rtd-notificacao').reset();
    document.getElementById('rtd-arquivo-notificacao').disabled = false;
    arquivoRtdPendente = null;
    document.getElementById('btn-repetir-envio-pdf-rtd').hidden = true;
    document.getElementById('rtd-extracao-status').textContent = '';
    document.getElementById('rtd-envio-intimacao-id').value = id;
    document.getElementById('rtd-envio-operacao-id').value = novaChaveOperacaoRtd();
    intimacaoEnvioRtdId = id;
    envioRtdConcluido = false;
    document.getElementById('btn-nova-notificacao-rtd').hidden = true;
    document.getElementById('rtd-destino-uf').value = 'GO';
    document.getElementById('rtd-destino-cidade').value = 'Morrinhos';
    document.getElementById('rtd-entrega-destinatario').checked = true;
    document.getElementById('rtd-credor-notificacao').value = dadosCredor?.credor || item.credor || '';
    document.getElementById('rtd-credor-cnpj').value = dadosCredor?.cnpj || '';
    document.getElementById('rtd-destino-cartorio').innerHTML = '<option value="">Busque pela cidade primeiro</option>';
    document.getElementById('rtd-destino-cartorio').disabled = true;
    document.getElementById('rtd-envio-ambiente-aviso').hidden = true;
    const avisoEnvio = document.getElementById('rtd-envio-status');
    avisoEnvio.textContent = `Intimação ${item.protocolo}. Nenhum pedido será enviado até você confirmar.`;
    document.getElementById('btn-confirmar-rtd-notificacao').textContent = 'Enviar notificação';
    document.getElementById('rtd-confirmacao-envio-texto').textContent = 'Revisei destinatários, endereços, cartório e documento; autorizo o envio desta notificação à Central RTD.';
    document.getElementById('rtd-notificados-lista').replaceChildren();
    novoCampoNotificado();
    filaRtdSeparada = paresRtd?.length ? paresRtd : null;
    filaRtdDosOriginais = Boolean(filaRtdSeparada);
    indiceFilaRtdSeparada = 0;
    filaRtdFinalizada = false;
    if (filaRtdSeparada) preencherParRtd(filaRtdSeparada[0]);
    atualizarFilaRtd();
    modal.classList.add('aberta');
}

function fecharEnvioRtd() {
    if (envioRtdEmCurso) return;
    document.getElementById('modal-rtd-notificacao').classList.remove('aberta');
    document.getElementById('rtd-envio-status').textContent =
        'Janela fechada; progresso mantido nesta aba. Reabra este IN para continuar sem repetir as notificações já confirmadas.';
}

function prepararProximoEnvioRtd() {
    if (!envioRtdConcluido || envioRtdEmCurso || !intimacaoEnvioRtdId) return;
    if (!confirm('O envio anterior permanece no histórico. Um novo envio criará outro protocolo no RTD. Revise os destinatários para evitar duplicidade. Continuar?')) return;

    document.getElementById('rtd-arquivo-notificacao').value = '';
    document.getElementById('rtd-arquivo-notificacao').disabled = false;
    document.getElementById('btn-repetir-envio-pdf-rtd').hidden = true;
    document.getElementById('rtd-confirmar-sem-duplicidade').checked = false;
    document.getElementById('rtd-confirmar-envio').checked = false;
    document.getElementById('rtd-envio-operacao-id').value = novaChaveOperacaoRtd();
    document.getElementById('btn-confirmar-rtd-notificacao').disabled = true;
    document.getElementById('btn-confirmar-rtd-notificacao').textContent = 'Enviar notificação';
    document.getElementById('btn-nova-notificacao-rtd').hidden = true;
    filaRtdSeparada = null;
    filaRtdDosOriginais = false;
    indiceFilaRtdSeparada = 0;
    filaRtdFinalizada = false;
    envioRtdConcluido = false;
    document.getElementById('rtd-envio-status').textContent =
        'Envio anterior preservado no histórico. Os dados preenchidos foram mantidos; selecione o PDF e revise os destinatários antes de enviar novamente.';
}

async function extrairDocumentoRtdSelecionado(arquivoForcado = null) {
    const arquivoInput = document.getElementById('rtd-arquivo-notificacao');
    const arquivo = arquivoForcado instanceof File ? arquivoForcado : arquivoInput.files?.[0];
    const status = document.getElementById('rtd-envio-status');
    const statusExtracao = document.getElementById('rtd-extracao-status');
    const mostrarStatus = mensagem => { status.textContent = mensagem; statusExtracao.textContent = mensagem; };
    const id = document.getElementById('rtd-envio-intimacao-id').value;
    if (!arquivo || !id) return;
    const versao = ++versaoExtracaoRtd;
    uploadRtdController?.abort();
    const controlador = new AbortController();
    uploadRtdController = controlador;
    const uploadAnterior = uploadRtdAtual;
    uploadRtdAtual = null;
    document.getElementById('btn-repetir-envio-pdf-rtd').hidden = true;
    if (arquivo.name.toLocaleLowerCase('pt-BR') !== 'documentos rtd.pdf' || arquivo.size > LIMITE_PDF_RTD) {
        mostrarStatus('Selecione Documentos RTD.pdf da pasta deste IN, com até 25 MB.');
        arquivoInput.value = '';
        extracaoRtdEmCurso = false;
        document.getElementById('btn-confirmar-rtd-notificacao').disabled = true;
        if (uploadAnterior) void removerUploadRtd(uploadAnterior);
        uploadRtdController = null;
        return;
    }
    extracaoRtdEmCurso = true;
    document.getElementById('btn-confirmar-rtd-notificacao').disabled = true;
    mostrarStatus('Enviando o PDF com segurança para leitura e envio ao RTD…');
    let uploadConcluido = false;
    let etapaExtracao = 'iniciar o envio seguro do PDF';
    try {
        if (uploadAnterior) await removerUploadRtd(uploadAnterior);
        etapaExtracao = 'registrar o PDF temporário no AERI';
        const sessao = await requisicaoAeri('/api/rtd-intimacoes/uploads', opcoesJsonRtd({
            intimacao_id:id, nome_arquivo:arquivo.name, tamanho:arquivo.size,
        }, controlador.signal));
        const upload = {id:sessao.upload_id, arquivo};
        uploadRtdAtual = upload;
        etapaExtracao = 'autorizar o envio ao armazenamento privado';
        const autorizacao = await urlTemporariaRtd(upload.id, 'put', controlador.signal);
        etapaExtracao = 'enviar o PDF ao armazenamento privado';
        const respostaUpload = await fetch(autorizacao.url, {
            method:'PUT', body:arquivo, signal:controlador.signal,
        });
        if (!respostaUpload.ok) throw new Error('O armazenamento não confirmou o envio. Tente selecionar o PDF novamente.');
        uploadConcluido = true;
        arquivoRtdPendente = null;
        if (versao !== versaoExtracaoRtd || document.getElementById('rtd-envio-intimacao-id').value !== id
            || arquivoInput.files?.[0] !== arquivo) return;
        if (filaRtdDosOriginais) {
            mostrarStatus('PDF enviado com segurança. Os devedores e endereços vieram dos documentos originais; confira-os antes de enviar ao RTD.');
            return;
        }
        filaRtdSeparada = null;
        indiceFilaRtdSeparada = 0;
        filaRtdFinalizada = false;
        document.getElementById('rtd-notificados-lista').replaceChildren();
        novoCampoNotificado();
        atualizarFilaRtd();
        mostrarStatus('PDF recebido. Lendo os devedores e endereços…');
        etapaExtracao = 'autorizar a leitura do PDF temporário';
        const leitura = await urlTemporariaRtd(upload.id, 'get', controlador.signal);
        etapaExtracao = 'extrair os devedores e endereços do PDF';
        const dados = await requisicaoAeri(`/api/intimacoes/${id}/extrair-documento-rtd`,
            opcoesJsonRtd({upload_id:upload.id, url_assinada:leitura.url}, controlador.signal));
        if (versao !== versaoExtracaoRtd || document.getElementById('rtd-envio-intimacao-id').value !== id
            || arquivoInput.files?.[0] !== arquivo) return;
        const pessoas = dados.devedores || [];
        const enderecos = (dados.enderecos || []).filter(endereco =>
            String(endereco.cidade).toLocaleUpperCase('pt-BR') === 'MORRINHOS' && endereco.uf === 'GO');
        const pares = pessoas.flatMap(pessoa => enderecos.map(endereco => ({
            pessoa,
            endereco:{CEP:endereco.cep, Logradouro:endereco.logradouro, Numero:endereco.numero,
                Complemento:endereco.complemento, Bairro:endereco.bairro,
                Cidade:endereco.cidade, UF:endereco.uf},
        })));
        if (!pares.length || pares.length > 20) {
            mostrarStatus('O PDF foi guardado e será anexado à notificação ao RTD. Não consegui identificar uma combinação válida de devedor e endereço de Morrinhos; confira o documento e preencha esses campos manualmente antes de enviar.');
            return;
        }
        if (dados.cnpjCredor) document.getElementById('rtd-credor-cnpj').value = dados.cnpjCredor;
        filaRtdSeparada = pares;
        indiceFilaRtdSeparada = 0;
        filaRtdFinalizada = false;
        preencherParRtd(pares[0]);
        atualizarFilaRtd();
        for (const campoId of ['rtd-confirmar-sem-duplicidade', 'rtd-confirmar-envio']) {
            document.getElementById(campoId).checked = false;
        }
        mostrarStatus(`${pessoas.length} devedor(es) e ${enderecos.length} endereço(s) de Morrinhos identificados: ${pares.length} notificação(ões) individual(is). ${dados.cnpjCredor ? 'CNPJ do credor preenchido a partir do PDF; confira se corresponde ao nome exibido.' : ''} ${(dados.avisos || []).join(' ')}`);
    } catch (erro) {
        if (!uploadConcluido && uploadRtdAtual?.arquivo === arquivo) {
            const uploadFalhou = uploadRtdAtual;
            uploadRtdAtual = null;
            void removerUploadRtd(uploadFalhou);
        }
        if (versao === versaoExtracaoRtd && erro.name !== 'AbortError') {
            const falhaDeRede = erro instanceof TypeError
                && /failed to fetch|networkerror|load failed/i.test(erro.message || '');
            if (!uploadConcluido) {
                arquivoRtdPendente = arquivo;
                document.getElementById('btn-repetir-envio-pdf-rtd').hidden = false;
                const motivo = falhaDeRede ? `A conexão falhou ao ${etapaExtracao}.` : erro.message;
                mostrarStatus(`${motivo} O PDF ainda não foi guardado; por isso não pode ser anexado nem enviado ao RTD. Mantive o arquivo selecionado. Tente enviar o PDF novamente.`);
            } else {
                const motivo = falhaDeRede ? `A conexão falhou ao ${etapaExtracao}.` : erro.message;
                mostrarStatus(`${motivo} O PDF já foi guardado e será anexado quando você confirmar o envio ao RTD. A leitura automática não terminou; confira e preencha os campos manualmente. A notificação ainda não foi enviada.`);
            }
        }
    } finally {
        if (versao === versaoExtracaoRtd) {
            extracaoRtdEmCurso = false;
            document.getElementById('btn-confirmar-rtd-notificacao').disabled = filaRtdFinalizada || !uploadRtdAtual;
        }
        if (uploadRtdController === controlador) uploadRtdController = null;
    }
}

async function buscarCartoriosRtd() {
    const uf = document.getElementById('rtd-destino-uf').value.trim().toUpperCase();
    const cidade = document.getElementById('rtd-destino-cidade').value.trim();
    const seletor = document.getElementById('rtd-destino-cartorio');
    const status = document.getElementById('rtd-envio-status');
    const avisoAmbiente = document.getElementById('rtd-envio-ambiente-aviso');
    const botao = document.getElementById('btn-buscar-cartorios-rtd');
    seletor.disabled = true;
    botao.disabled = true;
    avisoAmbiente.hidden = true;
    status.textContent = 'Consultando os cartórios disponíveis na Central…';
    try {
        const query = new URLSearchParams({uf, cidade});
        const dados = await requisicaoAeri(`/api/rtd-intimacoes/cartorios?${query}`);
        const homologacao = dados.ambiente === 'homologacao';
        status.classList.toggle('is-homologacao', homologacao);
        seletor.innerHTML = '<option value="">Selecione o cartório de destino</option>' + (dados.cartorios || []).map(item =>
            `<option value="${Number(item.id)}">${escaparHtml(item.nome)}</option>`).join('');
        seletor.disabled = !(dados.cartorios || []).length;
        if (homologacao) {
            avisoAmbiente.textContent = 'HOMOLOGAÇÃO: o envio será registrado somente na Central de treinamento. Não gera pedido na produção nem entra na fila de produção.';
            avisoAmbiente.hidden = false;
            document.getElementById('btn-confirmar-rtd-notificacao').textContent = 'Enviar teste';
            document.getElementById('rtd-confirmacao-envio-texto').textContent = 'Revisei os dados e autorizo o envio deste teste ao ambiente de homologação.';
            status.textContent = (dados.cartorios || []).length ? 'Selecione o cartório de destino.' : 'Nenhum cartório foi encontrado para essa cidade e estado.';
        } else {
            document.getElementById('btn-confirmar-rtd-notificacao').textContent = 'Enviar notificação';
            document.getElementById('rtd-confirmacao-envio-texto').textContent = 'Revisei destinatários, endereços, cartório e documento; autorizo o envio desta notificação à Central RTD.';
            status.textContent = (dados.cartorios || []).length ? 'Selecione o cartório de destino.' : 'Nenhum cartório foi encontrado para essa cidade e estado.';
        }
    } catch (erro) {
        seletor.innerHTML = '<option value="">Não foi possível carregar os cartórios</option>';
        status.textContent = erro.message;
    } finally {
        botao.disabled = false;
    }
}

function lerParteRtd(container, tipo) {
    const camposEndereco = Object.fromEntries([...container.querySelectorAll('[data-endereco]')]
        .map(input => [input.dataset.endereco, input.value.trim()]));
    const nome = container.querySelector('[data-pessoa="Nome"]')?.value.trim()
        || document.getElementById('rtd-remetente-nome').value.trim();
    const documento = (container.querySelector('[data-pessoa="CpfCnpj"]')?.value
        || document.getElementById('rtd-remetente-documento').value).replace(/\D/g, '');
    const parte = {Nome:nome, Endereco:camposEndereco};
    parte[tipo === 'remetente' ? 'CPFCNPJ' : 'CpfCnpj'] = documento;
    return parte;
}

function formatarCnpjRtd(valor) {
    const numeros = String(valor || '').replace(/\D/g, '');
    if (numeros.length !== 14) return '';
    return `${numeros.slice(0,2)}.${numeros.slice(2,5)}.${numeros.slice(5,8)}/${numeros.slice(8,12)}-${numeros.slice(12)}`;
}

async function enviarNotificacaoRtd(evento) {
    evento.preventDefault();
    const form = evento.currentTarget;
    if (extracaoRtdEmCurso || !form.reportValidity() || envioRtdEmCurso || filaRtdFinalizada) return;
    const arquivo = document.getElementById('rtd-arquivo-notificacao').files?.[0];
    const status = document.getElementById('rtd-envio-status');
    const pdfValido = arquivoItem => arquivoItem && arquivoItem.size <= LIMITE_PDF_RTD
        && arquivoItem.name.toLocaleLowerCase('pt-BR').endsWith('.pdf')
        && (!arquivoItem.type || arquivoItem.type === 'application/pdf');
    if (!pdfValido(arquivo)) {
        status.textContent = 'Selecione o PDF Documentos RTD.pdf, com até 25 MB.';
        return;
    }
    if (arquivo.name.toLocaleLowerCase('pt-BR') !== 'documentos rtd.pdf') {
        status.textContent = 'Selecione o arquivo chamado exatamente “Documentos RTD.pdf” da pasta deste IN.';
        return;
    }
    if (!uploadRtdAtual || uploadRtdAtual.arquivo !== arquivo) {
        status.textContent = 'Aguarde o envio seguro do PDF terminar ou selecione-o novamente.';
        return;
    }
    const cartorioId = Number(document.getElementById('rtd-destino-cartorio').value);
    if (!cartorioId) {
        status.textContent = 'Pesquise e selecione o cartório de destino antes de enviar.';
        return;
    }
    const credor = document.getElementById('rtd-credor-notificacao').value.trim();
    const cnpjCredor = formatarCnpjRtd(document.getElementById('rtd-credor-cnpj').value);
    if (!credor || !cnpjCredor) {
        status.textContent = 'Informe o nome e o CNPJ do credor conforme os documentos do processo.';
        return;
    }
    const observacoes = document.getElementById('rtd-informacoes-adicionais').value.trim();
    const pedido = {
        Remetente:lerParteRtd(document.querySelector('[data-parte="remetente"]'), 'remetente'),
        CartorioId:cartorioId,
        CidadeDestino:document.getElementById('rtd-destino-cidade').value.trim(),
        UFDestino:document.getElementById('rtd-destino-uf').value.trim().toUpperCase(),
        InformacoesAdicionais:`Recebido em nome de: ${credor}, inscrita no CNPJ: ${cnpjCredor}.${observacoes ? ` ${observacoes}` : ''}`,
        EntregueSomenteAoDestinatario:document.getElementById('rtd-entrega-destinatario').checked,
        Notificados:[...document.querySelectorAll('[data-rtd-notificado]')].map(bloco => lerParteRtd(bloco, 'destinatario')),
    };
    if (filaRtdSeparada && pedido.Notificados.length !== 1) {
        status.textContent = 'Esta sequência exige exatamente um destinatário e um endereço por pedido.';
        return;
    }
    envioRtdEmCurso = true;
    document.getElementById('btn-confirmar-rtd-notificacao').disabled = true;
    document.getElementById('btn-cancelar-rtd-notificacao').disabled = true;
    document.getElementById('btn-fechar-rtd-notificacao').disabled = true;
    status.textContent = 'Preparando o documento privado e solicitando a notificação à Central. Não feche esta janela.';
    let removerAoFinal = false;
    try {
        const leitura = await urlTemporariaRtd(uploadRtdAtual.id, 'get');
        status.textContent = 'Enviando o documento e solicitando a notificação à Central. Não feche esta janela.';
        const dados = {
            intimacao_id:document.getElementById('rtd-envio-intimacao-id').value,
            chave_operacao:document.getElementById('rtd-envio-operacao-id').value,
            pedido,
            upload_id:uploadRtdAtual.id,
            url_assinada:leitura.url,
        };
        const resultado = await requisicaoAeri('/api/rtd-intimacoes/notificacoes', opcoesJsonRtd(dados));
        if (resultado.estado === 'CRIADO') {
            status.textContent = `Notificação enviada à Central. Protocolo: ${resultado.protocolo}.`;
        } else if (resultado.estado === 'HOMOLOGACAO_OK') {
            status.textContent = `Teste aceito pela Central de homologação. Protocolo: ${resultado.protocolo}. Não entrou na fila de produção.`;
        } else {
            status.textContent = `A Central respondeu, mas o AERI marcou o resultado para revisão. Protocolo: ${resultado.protocolo || 'não informado'}.`;
        }
        await carregarEnviosRtd(document.getElementById('rtd-envio-intimacao-id').value, true);
        await carregarIntimacoes();
        if (filaRtdSeparada && ['CRIADO', 'HOMOLOGACAO_OK'].includes(resultado.estado)) {
            document.getElementById('rtd-arquivo-notificacao').disabled = true;
            indiceFilaRtdSeparada += 1;
            if (indiceFilaRtdSeparada < filaRtdSeparada.length) {
                document.getElementById('rtd-envio-operacao-id').value = novaChaveOperacaoRtd();
                preencherParRtd(filaRtdSeparada[indiceFilaRtdSeparada]);
                for (const id of ['rtd-confirmar-sem-duplicidade', 'rtd-confirmar-envio']) {
                    document.getElementById(id).checked = false;
                }
                atualizarFilaRtd();
                status.textContent += ` Próximo pedido: ${indiceFilaRtdSeparada + 1} de ${filaRtdSeparada.length}. Revise e confirme de novo; o próximo não será enviado automaticamente.`;
            } else {
                filaRtdFinalizada = true;
                removerAoFinal = true;
                status.textContent += ` Sequência concluída: ${filaRtdSeparada.length} pedidos individuais.`;
            }
        } else if (['CRIADO', 'HOMOLOGACAO_OK'].includes(resultado.estado)) {
            removerAoFinal = true;
        }
        if (removerAoFinal) {
            const upload = uploadRtdAtual;
            document.getElementById('rtd-arquivo-notificacao').value = '';
            await removerUploadRtd(upload);
            envioRtdConcluido = true;
            document.getElementById('btn-nova-notificacao-rtd').hidden = false;
        }
    } catch (erro) {
        status.textContent = erro.message;
        const id = document.getElementById('rtd-envio-intimacao-id').value;
        await carregarEnviosRtd(id, true);
        renderizarIntimacoes();
    } finally {
        envioRtdEmCurso = false;
        document.getElementById('btn-confirmar-rtd-notificacao').disabled = filaRtdFinalizada || envioRtdConcluido || !uploadRtdAtual;
        document.getElementById('btn-cancelar-rtd-notificacao').disabled = false;
        document.getElementById('btn-fechar-rtd-notificacao').disabled = false;
    }
}

function renderizarIntimacoes() {
    const tbody = document.getElementById('rotina-tbody');
    renderizarCabecalho();
    document.querySelector('label[for="importar-intimacoes"]').hidden = !(pode('criar_intimacoes') && pode('alterar_intimacoes'));
    document.getElementById('btn-nova-intimacao').hidden = !pode('criar_intimacoes');
    const termo = document.getElementById('busca-intimacao').value.trim();
    const daFase = intimacoes.filter(item => faseAtiva === 'TODAS' || item.fase === faseAtiva);
    const filtradas = daFase.filter(item => correspondeBuscaIntimacao(item, termo))
        .filter(item => filtroSituacao === 'TODAS' || (filtroSituacao === 'RTD' ? temNovidadeRtd(item) : filtroSituacao === 'PENDENTES' ? ['vermelho','cinza'].includes(situacaoIntimacao(item).classe) : situacaoIntimacao(item).classe === filtroSituacao))
        .sort((a, b) => ordenarNovidadesRtd(a,b) || situacaoIntimacao(a).ordem - situacaoIntimacao(b).ordem || a.protocolo.localeCompare(b.protocolo));

    renderizarCoberturaIntimacao();
    renderizarAgendaIntimacoes();
    tbody.innerHTML = filtradas.map(item => {
        const situacao = situacaoIntimacao(item);
        const acoes = acoesIntimacao(item, true);
        const linha = `<tr class="rotina-row rotina-row-${situacao.classe}">
            <td><span class="rotina-status ${situacao.classe}"><i></i>${situacao.rotulo}</span><small>${situacao.detalhe}</small><small>Última conferência: ${item.ultimaConferencia ? formatarDataRotina(item.ultimaConferencia) : '—'}</small></td>
            <td><strong class="rotina-protocolo">${escaparHtml(item.protocolo)}</strong></td>
            <td>${escaparHtml(item.credor)}</td>
            <td>${escaparHtml(item.devedor)}${item.fase === 'INTIMACAO' && item.devedorFonte === 'RTD' ? '<small>Identificado no documento RTD</small>' : ''}</td>
            <td>${escaparHtml(item.nomeAndamento || 'Não informado')}</td>
            <td>${formatarDataRotina(item.ultimoAndamento)}</td>
            <td class="rtd-coluna">${item.fase === 'INTIMACAO' ? resumoRtd(item) : '—'}</td>
            <td>${botaoPastaIntimacao(item)}</td>
            <td>${acoes}</td>
        </tr>`;
        if (!detalhesAbertos.has(item.id)) return linha;
        return `${linha}<tr class="rotina-detalhes-row"><td colspan="9">${detalhesFaseInicial(item)}</td></tr>`;
    }).join('') || '<tr><td colspan="9" class="rotina-vazio">Nenhuma intimação cadastrada. Use “Nova intimação” ou importe sua planilha em CSV.</td></tr>';
    renderizarCentralAcao(filtradas);

    const contagens = {verde:0, amarelo:0, vermelho:0, cinza:0};
    daFase.forEach(item => contagens[situacaoIntimacao(item).classe]++);
    const novidadesRtd = intimacoes.filter(temNovidadeRtd).length;
    const pendentes = daFase.filter(item => situacaoIntimacao(item).classe !== 'verde').length;
    const resumo = document.getElementById('rotina-resumo');
    if (resumo) resumo.innerHTML = [
        ['azul','Protocolos no escopo',daFase.length], ['amarelo','Ações pendentes',pendentes],
        ['rtd','Novidades do RTD',novidadesRtd], ['verde','Conferidas hoje',contagens.verde],
    ].map(([classe, rotulo, valor]) => `<div class="rotina-resumo-card ${classe}"><span>${rotulo}</span><strong>${valor}</strong></div>`).join('');
    [...FASES_INTIMACAO, 'TODAS'].forEach(fase => {
        const total = fase === 'TODAS' ? intimacoes.length : intimacoes.filter(item => item.fase === fase).length;
        document.querySelector(`[data-total-fase="${fase}"]`).textContent = total;
    });
    document.querySelectorAll('.rotina-fase-btn').forEach(botao => {
        const ativa = botao.dataset.fase === faseAtiva;
        botao.classList.toggle('ativa', ativa);
        botao.setAttribute('aria-selected', String(ativa));
    });
    document.getElementById('rotina-total').textContent = `${filtradas.length} de ${daFase.length} protocolos no escopo`;
}

export async function carregarIntimacoes(opcoes = {}) {
    try {
        const recebidas = await requisicaoAeri(
            `/api/intimacoes${exibindoLixeira ? '?lixeira=true' : ''}`,
            {background:Boolean(opcoes.background)},
        );
        const atuaisPorId = new Map(intimacoes.map(item => [item.id, item]));
        intimacoes = recebidas.map(recebida => {
            const atual = atuaisPorId.get(recebida.id);
            // A atualização automática roda a cada 5s (INTERVALO_ATUALIZACAO_MS
            // em app.js) e pode buscar a intimação um instante antes de uma
            // criação/edição/conferência ter comitado no banco. Sem essa
            // checagem, essa resposta desatualizada sobrescrevia silenciosamente
            // a mudança recém-feita, fazendo o item "voltar" na tela (mesma
            // causa do bug em custas.js).
            if (atual && new Date(atual.atualizadoEm) > new Date(recebida.atualizadoEm)) return atual;
            return recebida;
        });
    } catch (falha) {
        console.error(falha);
        // Mantém a última lista conhecida em vez de zerar: uma falha
        // passageira do polling não deve apagar tudo que já estava na tela.
    }
    renderizarIntimacoes();
}

export function limparIntimacoes() {
    intimacoes = [];
    rascunhosConferencia.clear();
    filaConferenciaAtual = [];
    avisoMesa = '';
    intimacaoSelecionadaId = null;
    renderizarIntimacoes();
}

let edicaoIntimacaoAtualizadoEm = null;

function atualizarCamposFaseIntimacao() {
    const secao = document.getElementById('intimacao-campos-fase-inicial');
    const fase = document.getElementById('intimacao-fase')?.value;
    if (secao) secao.hidden = fase !== 'INTIMACAO';
}

function abrirFormularioIntimacao() {
    if (!pode('criar_intimacoes')) return;
    edicaoIntimacaoAtualizadoEm = null;
    document.getElementById('form-intimacao').reset();
    document.getElementById('intimacao-id').value = '';
    document.getElementById('titulo-form-intimacao').textContent = 'Nova intimação';
    document.getElementById('intimacao-andamento').value = hojeLocal();
    document.getElementById('intimacao-fase').value = FASES_INTIMACAO.includes(faseAtiva) ? faseAtiva : 'INTIMACAO';
    atualizarCamposFaseIntimacao();
    document.getElementById('intimacao-valor-pago').value = '530.07';
    document.getElementById('intimacao-valor-usado').value = '0.00';
    atualizarSaldoFormulario();
    document.getElementById('modal-intimacao').classList.add('aberta');
    document.getElementById('intimacao-protocolo').focus();
}

function fecharFormularioIntimacao() {
    document.getElementById('modal-intimacao').classList.remove('aberta');
}

function atualizarSaldoFormulario() {
    const pago = Number(document.getElementById('intimacao-valor-pago').value || 0);
    const usado = Number(document.getElementById('intimacao-valor-usado').value || 0);
    document.getElementById('intimacao-saldo-os').value = formatarMoeda(pago - usado);
}

async function salvarIntimacao(evento) {
    evento.preventDefault();
    const botaoSalvar = evento.submitter;
    const id = document.getElementById('intimacao-id').value;
    const protocolo = document.getElementById('intimacao-protocolo').value.trim().toUpperCase();
    if (intimacoes.some(item => item.protocolo === protocolo && item.id !== id)) {
        return alert('Este protocolo já está cadastrado.');
    }
    const item = {
        protocolo,
        credor: document.getElementById('intimacao-credor').value.trim(),
        devedor: document.getElementById('intimacao-devedor').value.trim(),
        nomeAndamento: document.getElementById('intimacao-nome-andamento').value.trim(),
        ultimoAndamento: document.getElementById('intimacao-andamento').value,
        fase: document.getElementById('intimacao-fase').value,
        protocoloRtd: document.getElementById('intimacao-protocolo-rtd').value.trim(),
        numeroOsTri7: document.getElementById('intimacao-os-tri7').value.trim(),
        protocoloTri7: document.getElementById('intimacao-protocolo-tri7').value.trim(),
        certidaoDecursoPrazo: document.getElementById('intimacao-certidao-decurso').value.trim(),
        dataIntimacao: document.getElementById('intimacao-data-intimacao').value,
        dataCertificacao: document.getElementById('intimacao-data-certificacao').value,
        valorPagoOnr: document.getElementById('intimacao-valor-pago').value,
        valorUsado: document.getElementById('intimacao-valor-usado').value,
        atualizadoEm: edicaoIntimacaoAtualizadoEm,
    };
    try {
        botaoSalvar.disabled = true;
        botaoSalvar.textContent = 'Salvando...';
        const salvo = await requisicaoAeri(id ? `/api/intimacoes/${id}` : '/api/intimacoes', {
            method: id ? 'PUT' : 'POST',
            headers: {'Content-Type':'application/json'},
            body: JSON.stringify(item),
        });
        const indice = intimacoes.findIndex(atual => atual.id === salvo.id);
        if (indice >= 0) intimacoes[indice] = salvo;
        else intimacoes.push(salvo);
        fecharFormularioIntimacao();
        renderizarIntimacoes();
    } catch (falha) {
        if (falha.message.includes('alterada por outra pessoa')) {
            fecharFormularioIntimacao();
            alert(falha.message);
            carregarIntimacoes();
            return;
        }
        alert(falha.message);
    } finally {
        botaoSalvar.disabled = false;
        botaoSalvar.textContent = 'Salvar intimação';
    }
}

function editarIntimacao(id) {
    if (!pode('alterar_intimacoes')) return;
    const item = intimacoes.find(atual => atual.id === id);
    if (!item) return;
    edicaoIntimacaoAtualizadoEm = item.atualizadoEm;
    document.getElementById('intimacao-id').value = item.id;
    document.getElementById('intimacao-protocolo').value = item.protocolo;
    document.getElementById('intimacao-credor').value = item.credor;
    document.getElementById('intimacao-devedor').value = item.devedor;
    document.getElementById('intimacao-nome-andamento').value = item.nomeAndamento || 'Não informado';
    document.getElementById('intimacao-andamento').value = item.ultimoAndamento;
    document.getElementById('intimacao-fase').value = item.fase || 'INTIMACAO';
    atualizarCamposFaseIntimacao();
    document.getElementById('intimacao-protocolo-rtd').value = item.protocoloRtd || '';
    document.getElementById('intimacao-os-tri7').value = item.numeroOsTri7 || '';
    document.getElementById('intimacao-protocolo-tri7').value = item.protocoloTri7 || '';
    document.getElementById('intimacao-certidao-decurso').value = item.certidaoDecursoPrazo || '';
    document.getElementById('intimacao-data-intimacao').value = item.dataIntimacao || '';
    document.getElementById('intimacao-data-certificacao').value = item.dataCertificacao || '';
    document.getElementById('intimacao-valor-pago').value = Number(item.valorPagoOnr ?? 530.07).toFixed(2);
    document.getElementById('intimacao-valor-usado').value = Number(item.valorUsado ?? 0).toFixed(2);
    atualizarSaldoFormulario();
    document.getElementById('titulo-form-intimacao').textContent = 'Editar intimação';
    document.getElementById('modal-intimacao').classList.add('aberta');
}

function fecharCheckIntimacao() {
    document.getElementById('modal-check-intimacao').classList.remove('aberta');
    document.getElementById('form-check-andamento').hidden = true;
    document.getElementById('check-intimacao-escolha').hidden = false;
    document.getElementById('form-check-andamento').reset();
    intimacaoCheckId = null;
}

function abrirCheckIntimacao(id) {
    if (!pode('conferir_intimacoes')) return;
    const item = intimacoes.find(atual => atual.id === id);
    if (!item || intimacoesPendentes.has(id)) return;
    intimacaoCheckId = id;
    document.getElementById('check-intimacao-protocolo').textContent = `${item.protocolo} — andamento atual: ${item.nomeAndamento || 'Não informado'}`;
    document.getElementById('check-intimacao-escolha').hidden = false;
    document.getElementById('form-check-andamento').hidden = true;
    document.getElementById('modal-check-intimacao').classList.add('aberta');
}

function escolherNovoAndamento() {
    document.getElementById('check-intimacao-escolha').hidden = true;
    document.getElementById('form-check-andamento').hidden = false;
    document.getElementById('check-novo-andamento').focus();
}

async function conferirIntimacao(id, novoAndamento = null, dataAndamento = null) {
    const indice = intimacoes.findIndex(item => item.id === id);
    if (indice < 0 || intimacoesPendentes.has(id)) return;
    const anterior = {...intimacoes[indice], historico:[...(intimacoes[indice].historico || [])]};
    const faseNova = novoAndamento ? fasePorAndamento(novoAndamento, anterior.fase) : anterior.fase;
    if (faseNova !== anterior.fase && !confirm(
        `O andamento "${novoAndamento}" moverá o protocolo de ${anterior.fase} para ${faseNova}. Confirmar?`,
    )) return;
    const hoje = hojeLocal();
    intimacoesPendentes.add(id);
    intimacoes[indice] = {
        ...anterior,
        ultimaConferencia: hoje,
        historico: [...new Set([...(anterior.historico || []), hoje])],
        ...(novoAndamento ? {
            nomeAndamento: novoAndamento,
            ultimoAndamento: dataAndamento || hoje,
            fase: fasePorAndamento(novoAndamento, anterior.fase),
        } : {}),
    };
    fecharCheckIntimacao();
    renderizarIntimacoes();
    try {
        const opcoes = {method:'POST'};
        if (novoAndamento) {
            opcoes.headers = {'Content-Type':'application/json'};
            opcoes.body = JSON.stringify({nomeAndamento: novoAndamento, ...(dataAndamento ? {dataAndamento} : {})});
        }
        const salvo = await requisicaoAeri(`/api/intimacoes/${id}/conferir`, opcoes);
        const indiceAtual = intimacoes.findIndex(item => item.id === id);
        if (indiceAtual >= 0) intimacoes[indiceAtual] = salvo;
        mostrandoFormularioAndamentoId = null;
        rascunhosConferencia.delete(id);
        avisoMesa = `${salvo.protocolo}: ${novoAndamento ? 'novo andamento salvo e conferência registrada.' : 'conferência registrada sem alteração do andamento.'}`;
    } catch (falha) {
        const indiceAtual = intimacoes.findIndex(item => item.id === id);
        if (indiceAtual >= 0) intimacoes[indiceAtual] = anterior;
        alert(falha.message);
    } finally {
        intimacoesPendentes.delete(id);
        renderizarIntimacoes();
    }
}

async function excluirIntimacao(id) {
    if (!confirm('Mover esta intimação para a lixeira? Ela poderá ser restaurada.')) return;
    try {
        await requisicaoAeri(`/api/intimacoes/${id}`, {method:'DELETE'});
        intimacoes = intimacoes.filter(item => item.id !== id);
        renderizarIntimacoes();
    } catch (falha) {
        alert(falha.message);
    }
}

function fecharExclusaoRtd() {
    const modal = document.getElementById('modal-rtd-exclusao');
    if (!modal) return;
    modal.classList.remove('aberta');
    modal.hidden = true;
    document.getElementById('form-rtd-exclusao')?.reset();
    document.getElementById('rtd-exclusao-status').textContent = '';
    exclusaoRtdIntimacaoId = null;
}

function abrirExclusaoRtd(id) {
    if (!somenteAdm()) return;
    const item = intimacoes.find(registro => registro.id === id);
    if (!item || item.fase !== 'INTIMACAO') return;
    exclusaoRtdIntimacaoId = id;
    document.getElementById('rtd-exclusao-intimacao-id').value = id;
    document.getElementById('rtd-exclusao-protocolo').textContent = `IN selecionado: ${item.protocolo}`;
    document.getElementById('rtd-exclusao-confirmacao').placeholder = item.protocolo;
    document.getElementById('rtd-exclusao-senha').value = '';
    document.getElementById('rtd-exclusao-status').textContent = '';
    const modal = document.getElementById('modal-rtd-exclusao');
    modal.hidden = false;
    modal.classList.add('aberta');
    document.getElementById('rtd-exclusao-confirmacao').focus();
}

async function confirmarExclusaoRtd(evento) {
    evento.preventDefault();
    if (!somenteAdm() || !exclusaoRtdIntimacaoId || exclusaoRtdEmCurso) return;
    const item = intimacoes.find(registro => registro.id === exclusaoRtdIntimacaoId);
    const confirmacao = document.getElementById('rtd-exclusao-confirmacao').value.trim().toUpperCase();
    const senha = document.getElementById('rtd-exclusao-senha').value;
    const status = document.getElementById('rtd-exclusao-status');
    const botao = document.getElementById('btn-confirmar-rtd-exclusao');
    if (!item || confirmacao !== item.protocolo.toUpperCase()) {
        status.textContent = 'O número digitado não corresponde ao IN selecionado.';
        document.getElementById('rtd-exclusao-confirmacao').focus();
        return;
    }
    exclusaoRtdEmCurso = true;
    botao.disabled = true;
    status.textContent = 'Validando a senha e removendo os vínculos RTD somente do AERI…';
    try {
        const resultado = await requisicaoAeri(
            `/api/rtd-intimacoes/intimacao/${encodeURIComponent(item.id)}/excluir-protocolos`,
            {method:'POST', headers:{'Content-Type':'application/json'},
                body:JSON.stringify({senha, confirmacao})},
        );
        enviosRtdPorIntimacao.delete(item.id);
        fecharExclusaoRtd();
        await carregarIntimacoes();
        const removidos = Number(resultado.pedidos_rtd || 0) + Number(resultado.envios_com_protocolo || 0);
        alert(resultado.jaEstavaLimpo
            ? `O IN ${item.protocolo} já estava sem protocolos RTD no AERI. A verificação foi registrada.`
            : `Concluído: ${removidos} registro(s) RTD removido(s) do AERI para o ${item.protocolo}. A ação foi registrada; tentativas sem protocolo foram preservadas.`);
    } catch (erro) {
        status.textContent = erro.message;
        if (erro.status === 401) {
            document.getElementById('rtd-exclusao-senha').value = '';
            document.getElementById('rtd-exclusao-senha').focus();
        }
    } finally {
        exclusaoRtdEmCurso = false;
        botao.disabled = false;
    }
}

async function abrirPastaIntimacao(protocolo) {
    // O caminho de rede é resolvido pelo aplicativo local. Ele não fica
    // exposto nem codificado no JavaScript servido aos navegadores.
    window.location.href = `aeri-intimacao://abrir/${encodeURIComponent(protocolo)}`;
}

async function restaurarIntimacao(id) {
    try {
        await requisicaoAeri(`/api/intimacoes/${id}/restaurar`, {method:'POST'});
        intimacoes = intimacoes.filter(item => item.id !== id);
        renderizarIntimacoes();
    } catch (falha) { alert(falha.message); }
}

async function novoLancamentoFinanceiro(id) {
    const tipo = prompt('Tipo do lançamento: CREDITO, REPASSE ou ESTORNO', 'REPASSE');
    if (!tipo) return;
    const valor = prompt('Valor do lançamento (ex.: 139,93):', '0,00');
    if (!valor) return;
    const descricao = prompt('Descrição do lançamento:', '') || '';
    try {
        await requisicaoAeri(`/api/intimacoes/${id}/financeiro`, {
            method:'POST', headers:{'Content-Type':'application/json'},
            body:JSON.stringify({tipo:tipo.toUpperCase(), valor:valor.replace(',', '.'), descricao}),
        });
        await carregarIntimacoes();
    } catch (erro) { alert(erro.message); }
}

async function atualizarChecklist(id) {
    const item = intimacoes.find(atual => atual.id === id);
    const atual = item?.checklistDesistencia || {};
    const signatario = prompt('Nome do signatário validado no ITI:', atual.signatario || '');
    if (signatario === null) return;
    const dados = {
        pedidoLocalizado: confirm('O Pedido de Desistência foi localizado?'),
        documentosConferidos: confirm('Todos os documentos foram conferidos?'),
        signatario,
        notaGerada: confirm('A nota em DOCX já foi gerada?'),
    };
    try {
        await requisicaoAeri(`/api/intimacoes/${id}/checklist-desistencia`, {
            method:'PUT', headers:{'Content-Type':'application/json'}, body:JSON.stringify(dados),
        });
        await carregarIntimacoes();
    } catch (erro) { alert(erro.message); }
}

function gerarNotaDesistencia(protocolo) {
    const confirmado = confirm(
        `O AERI analisará os PDFs da pasta ${protocolo} e o "Pedido de Desistência" em "Recebido para Intimacao". O DOCX será aberto para conferir obrigatoriamente o signatário no ITI. Continuar?`,
    );
    if (!confirmado) return;
    window.location.href = `aeri-intimacao://gerar-desistencia/${encodeURIComponent(protocolo)}`;
}

function normalizarCabecalho(valor) {
    return String(valor || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().trim();
}

function lerLinhaCsv(linha, separador) {
    const valores = [];
    let atual = '';
    let aspas = false;
    for (let i = 0; i < linha.length; i++) {
        const caractere = linha[i];
        if (caractere === '"' && linha[i + 1] === '"') { atual += '"'; i++; }
        else if (caractere === '"') aspas = !aspas;
        else if (caractere === separador && !aspas) { valores.push(atual.trim()); atual = ''; }
        else atual += caractere;
    }
    valores.push(atual.trim());
    return valores;
}

function converterDataImportada(valor) {
    const texto = String(valor || '').trim();
    if (/^\d{4}-\d{2}-\d{2}$/.test(texto)) return texto;
    const partes = texto.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
    return partes ? `${partes[3]}-${partes[2].padStart(2,'0')}-${partes[1].padStart(2,'0')}` : '';
}

function importarIntimacoesCsv(evento) {
    if (!(pode('criar_intimacoes') && pode('alterar_intimacoes'))) return;
    const input = evento.target;
    const arquivo = input.files?.[0];
    if (!arquivo) return;
    const leitor = new FileReader();
    leitor.onload = async () => {
        const texto = String(leitor.result || '').replace(/^\uFEFF/, '');
        const linhas = texto.split(/\r?\n/).filter(linha => linha.trim());
        if (linhas.length < 2) return alert('O CSV não possui registros.');
        const separador = (linhas[0].match(/;/g) || []).length >= (linhas[0].match(/,/g) || []).length ? ';' : ',';
        const cabecalhos = lerLinhaCsv(linhas[0], separador).map(normalizarCabecalho);
        const indice = nome => cabecalhos.findIndex(cabecalho => cabecalho.includes(nome));
        const ip = indice('protocolo');
        const ic = indice('credor') >= 0 ? indice('credor') : indice('solicitante');
        const id = indice('devedor');
        const ina = indice('nome do andamento') >= 0 ? indice('nome do andamento')
            : (indice('nome andamento') >= 0 ? indice('nome andamento') : indice('status'));
        const ia = indice('data do ultimo andamento') >= 0 ? indice('data do ultimo andamento')
            : (indice('ultimo andamento') >= 0 ? indice('ultimo andamento') : indice('data status'));
        if ([ip,ic,ia].some(i => i < 0)) return alert('Use as colunas: Protocolo, Credor/Solicitante e Data do Último Andamento/Data Status.');
        let importados = 0, atualizados = 0, ignorados = 0;
        const registros = new Map();
        linhas.slice(1).forEach(linha => {
            const colunas = lerLinhaCsv(linha, separador);
            const protocolo = (colunas[ip] || '').trim().toUpperCase();
            const nomeAndamento = ina >= 0 ? (colunas[ina] || '').trim() : 'Não informado';
            if (normalizarCabecalho(nomeAndamento) === 'desistencia concluida') { ignorados++; return; }
            if (!/^IN\d{8}C$/.test(protocolo)) { ignorados++; return; }
            const existente = intimacoes.find(item => item.protocolo === protocolo);
            const item = {
                protocolo,
                credor:(colunas[ic] || '').trim(),
                devedor:id >= 0 ? (colunas[id] || '').trim() : (existente?.devedor || 'Não informado no relatório'),
                nomeAndamento: nomeAndamento || 'Não informado',
                ultimoAndamento:converterDataImportada(colunas[ia]),
                fase: existente?.fase || faseAtiva,
                protocoloRtd: existente?.protocoloRtd || '',
                numeroOsTri7: existente?.numeroOsTri7 || '',
                protocoloTri7: existente?.protocoloTri7 || '',
                certidaoDecursoPrazo: existente?.certidaoDecursoPrazo || '',
                dataIntimacao: existente?.dataIntimacao || '',
                dataCertificacao: existente?.dataCertificacao || '',
                valorPagoOnr: existente?.valorPagoOnr ?? 530.07,
                valorUsado: existente?.valorUsado ?? 0,
            };
            if (item.credor && item.devedor && item.ultimoAndamento) registros.set(protocolo, {item, existente});
            else ignorados++;
        });
        for (const {item, existente} of registros.values()) {
            try {
                const salvo = await requisicaoAeri(existente ? `/api/intimacoes/${existente.id}` : '/api/intimacoes', {
                    method: existente ? 'PUT' : 'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(item),
                });
                if (existente) {
                    intimacoes[intimacoes.findIndex(atual => atual.id === existente.id)] = salvo;
                    atualizados++;
                } else {
                    intimacoes.push(salvo);
                    importados++;
                }
            } catch (falha) {
                console.warn(item.protocolo, falha.message);
                ignorados++;
            }
        }
        renderizarIntimacoes();
        input.value = '';
        alert(`${importados} novas, ${atualizados} atualizadas e ${ignorados} ignoradas.`);
    };
    leitor.readAsText(arquivo, 'UTF-8');
}

function exportarIntimacoesCsv() {
    const cabecalho = 'Protocolo ONR;Protocolo RTD;N.º OS Tri7;Saldo na OS;Protocolo Tri7;Certidão de Decurso de Prazo;Credor;Devedor;Fase;Último Andamento;Data do Último Andamento;Data da Intimação;Dias Úteis Certificação;Valor pago pelo Cliente na ONR;Valor Usado;Última Conferência';
    const linhas = intimacoes.map(item => [
        item.protocolo, item.fase === 'INTIMACAO' ? item.protocoloRtd || '' : '', item.numeroOsTri7 || '', item.saldoOs ?? '',
        item.protocoloTri7 || '', item.certidaoDecursoPrazo || '', item.credor, item.devedor,
        item.fase || '', item.nomeAndamento || 'Não informado', item.ultimoAndamento,
        item.dataIntimacao || '', item.dataCertificacao || '', item.valorPagoOnr ?? '',
        item.valorUsado ?? '', item.ultimaConferencia || '',
    ]
        .map(valor => `"${String(valor).replace(/"/g,'""')}"`).join(';'));
    baixarArquivo('\uFEFF' + [cabecalho,...linhas].join('\n'), 'text/csv;charset=utf-8', `intimacoes-aeri-${hojeLocal()}.csv`);
}

async function tratarAcaoTabela(evento) {
    const botao = evento.target.closest('button[data-acao]');
    if (!botao) return;
    if (botao.dataset.acao === 'rtd-lido') {
        botao.disabled = true;
        try {
            await requisicaoAeri(`/api/rtd-intimacoes/${botao.dataset.rtd}/lido`, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({versao:Number(botao.dataset.versao)})});
            await carregarIntimacoes();
        } catch (erro) { alert(erro.message); }
        finally { botao.disabled = false; }
        return;
    }
    if (botao.dataset.acao === 'rtd-documentos') {
        const protocolo = botao.dataset.rtd;
        botao.disabled = true;
        await carregarDocumentosRtd(protocolo);
        renderizarIntimacoes();
        return;
    }
    if (botao.dataset.acao === 'abrir-pasta') abrirPastaIntimacao(botao.dataset.protocolo);
    if (botao.dataset.acao === 'gerar-desistencia') gerarNotaDesistencia(botao.dataset.protocolo);
    if (botao.dataset.acao === 'detalhes') {
        if (detalhesAbertos.has(botao.dataset.id)) detalhesAbertos.delete(botao.dataset.id);
        else {
            detalhesAbertos.add(botao.dataset.id);
            const item = intimacoes.find(registro => registro.id === botao.dataset.id);
            await Promise.all([carregarHistoricoOperacional(botao.dataset.id),
                ...(item?.fase === 'INTIMACAO' ? [carregarEnviosRtd(botao.dataset.id)] : [])]);
        }
        renderizarIntimacoes();
    }
    if (botao.dataset.acao === 'novo-envio-rtd') abrirEnvioRtd(botao.dataset.id);
    if (botao.dataset.acao === 'excluir-protocolos-rtd') abrirExclusaoRtd(botao.dataset.id);
    if (botao.dataset.acao === 'preparar-documentos-intimacao') {
        const item = intimacoes.find(registro => registro.id === botao.dataset.id);
        if (item && pode('alterar_intimacoes')) abrirDocumentosIntimacao(item);
    }
    if (botao.dataset.acao === 'conferir') abrirCheckIntimacao(botao.dataset.id);
    if (botao.dataset.acao === 'editar') editarIntimacao(botao.dataset.id);
    if (botao.dataset.acao === 'excluir') excluirIntimacao(botao.dataset.id);
    if (botao.dataset.acao === 'restaurar') restaurarIntimacao(botao.dataset.id);
    if (botao.dataset.acao === 'financeiro') novoLancamentoFinanceiro(botao.dataset.id);
    if (botao.dataset.acao === 'checklist') atualizarChecklist(botao.dataset.id);
}

export function iniciarIntimacoes() {
    iniciarDocumentosIntimacao((id, pares, credor) => abrirEnvioRtd(id, pares, credor));
    if (!document.getElementById('rtd-estilos')) {
        const css = document.createElement('link');
        css.id = 'rtd-estilos'; css.rel = 'stylesheet';
        css.href = '/static/css/rtd_intimacoes.css?v=20261022-modais-claros-v1';
        // O legado RTD vem antes dos temas, sem mudar a prioridade das telas.
        document.head.insertBefore(css, document.getElementById('sync-theme'));
    }
    window.addEventListener('aeri:abrir-alerta', async evento => {
        if (evento.detail.modulo !== 'rotina') return;
        faseAtiva='TODAS'; filtroSituacao='PENDENTES'; filtroFila='PENDENTES'; exibindoLixeira=false;
        document.getElementById('filtro-situacao-intimacao').value='PENDENTES';
        await carregarIntimacoes();
    });
    const busca = document.getElementById('busca-intimacao');
    const seletor = document.createElement('select');
    seletor.id = 'filtro-situacao-intimacao';
    seletor.innerHTML = '<option value="TODAS">Todas as situações</option><option value="PENDENTES">Pendentes / atrasadas / sem atividade</option><option value="verde">Conferidas hoje</option><option value="amarelo">Vencem hoje</option><option value="vermelho">Atrasadas</option><option value="cinza">Sem atividade</option>';
    seletor.addEventListener('change', () => { filtroSituacao = seletor.value; renderizarIntimacoes(); });
    busca.parentElement.appendChild(seletor);
    if (cargoAdministrativo()) {
        const lixeira = document.createElement('button');
        lixeira.type = 'button'; lixeira.className = 'rotina-btn-secondary'; lixeira.textContent = 'Lixeira';
        lixeira.dataset.lixeiraIntimacoes = '';
        lixeira.addEventListener('click', async () => {
            exibindoLixeira = !exibindoLixeira;
            lixeira.textContent = exibindoLixeira ? 'Voltar às intimações' : 'Lixeira';
            await carregarIntimacoes();
        });
        busca.parentElement.appendChild(lixeira);
    }
    document.getElementById('busca-intimacao').addEventListener('input', renderizarIntimacoes);
    document.getElementById('rotina-fases').addEventListener('click', evento => {
        const botao = evento.target.closest('button[data-fase]');
        if (!botao) return;
        faseAtiva = botao.dataset.fase;
        renderizarIntimacoes();
    });
    document.getElementById('btn-nova-intimacao').addEventListener('click', abrirFormularioIntimacao);
    document.getElementById('btn-fechar-intimacao').addEventListener('click', fecharFormularioIntimacao);
    document.getElementById('btn-cancelar-intimacao').addEventListener('click', fecharFormularioIntimacao);
    document.getElementById('modal-intimacao').addEventListener('click', evento => {
        if (evento.target.id === 'modal-intimacao') fecharFormularioIntimacao();
    });
    document.getElementById('btn-fechar-check-intimacao').addEventListener('click', fecharCheckIntimacao);
    document.getElementById('modal-check-intimacao').addEventListener('click', evento => {
        if (evento.target.id === 'modal-check-intimacao') fecharCheckIntimacao();
    });
    document.getElementById('btn-check-sem-andamento').addEventListener('click', () => {
        if (intimacaoCheckId) conferirIntimacao(intimacaoCheckId);
    });
    document.getElementById('btn-check-com-andamento').addEventListener('click', escolherNovoAndamento);
    document.getElementById('btn-voltar-check').addEventListener('click', () => {
        document.getElementById('form-check-andamento').hidden = true;
        document.getElementById('check-intimacao-escolha').hidden = false;
    });
    document.getElementById('form-check-andamento').addEventListener('submit', evento => {
        evento.preventDefault();
        const novoAndamento = document.getElementById('check-novo-andamento').value.trim();
        if (intimacaoCheckId && novoAndamento) conferirIntimacao(intimacaoCheckId, novoAndamento);
    });
    document.getElementById('intimacao-protocolo').addEventListener('input', evento => {
        evento.target.value = evento.target.value.toUpperCase();
    });
    document.getElementById('form-intimacao').addEventListener('submit', salvarIntimacao);
    document.getElementById('intimacao-fase').addEventListener('change', atualizarCamposFaseIntimacao);
    document.getElementById('intimacao-valor-pago').addEventListener('input', atualizarSaldoFormulario);
    document.getElementById('intimacao-valor-usado').addEventListener('input', atualizarSaldoFormulario);
    document.getElementById('intimacao-protocolo-rtd').addEventListener('input', evento => {
        evento.target.value = evento.target.value.replace(/\D/g, '').slice(0, 17);
    });
    document.getElementById('rotina-tbody').addEventListener('click', tratarAcaoTabela);
    document.getElementById('btn-proximo-in-pendente').addEventListener('click', abrirProximoInPendente);
    document.getElementById('rotina-fila-filtros').addEventListener('click', evento => {
        const filtro = evento.target.closest('[data-fila-filtro]');
        if (!filtro) return;
        filtroFila = filtro.dataset.filaFiltro;
        filtroSituacao = 'TODAS';
        document.getElementById('filtro-situacao-intimacao').value = 'TODAS';
        if (['RTD', 'TODAS'].includes(filtroFila)) faseAtiva = 'TODAS';
        renderizarIntimacoes();
    });
    document.getElementById('rotina-central-acao').addEventListener('click', async evento => {
        const selecao = evento.target.closest('[data-selecionar-intimacao]');
        if (selecao) {
            intimacaoSelecionadaId = selecao.dataset.selecionarIntimacao;
            mostrandoFormularioAndamentoId = null;
            renderizarIntimacoes();
            return;
        }
        const navegacao = evento.target.closest('[data-foco-navegar]');
        if (navegacao) {
            navegarFocoIntimacao(Number(navegacao.dataset.focoNavegar));
            return;
        }
        const conferencia = evento.target.closest('[data-conferencia]');
        if (conferencia) {
            const id = conferencia.dataset.id;
            if (conferencia.dataset.conferencia === 'igual') {
                if (pode('conferir_intimacoes')) await conferirIntimacao(id);
            } else if (conferencia.dataset.conferencia === 'mudou') {
                if (!pode('conferir_intimacoes')) return;
                mostrandoFormularioAndamentoId = id;
                renderizarIntimacoes();
                document.getElementById('rotina-in-novo-andamento')?.focus();
            } else if (conferencia.dataset.conferencia === 'pular') {
                navegarFocoIntimacao(1);
            }
            return;
        }
        await tratarAcaoTabela(evento);
    });
    const centralMesa = document.getElementById('rotina-central-acao');
    centralMesa.addEventListener('input', evento => {
        const formulario = evento.target.closest('[data-mesa-conferencia]');
        if (!formulario || evento.target.type === 'radio') return;
        const dados = new FormData(formulario);
        rascunhosConferencia.set(formulario.dataset.id, {
            modo:dados.get('tipoConferencia') || '',
            nome:dados.get('novoAndamento') || '',
            data:dados.get('dataAndamento') || hojeLocal(),
        });
    });
    centralMesa.addEventListener('change', evento => {
        if (!evento.target.matches('[data-mesa-modo]')) return;
        const formulario = evento.target.closest('[data-mesa-conferencia]');
        const anterior = rascunhosConferencia.get(formulario.dataset.id) || {nome:'', data:hojeLocal()};
        rascunhosConferencia.set(formulario.dataset.id, {...anterior, modo:evento.target.value});
        renderizarFocoIntimacao(intimacoes.find(item => item.id === formulario.dataset.id), filaConferenciaAtual);
    });
    centralMesa.addEventListener('submit', async evento => {
        const formulario = evento.target.closest('[data-mesa-conferencia]');
        if (!formulario) return;
        evento.preventDefault();
        if (!pode('conferir_intimacoes') || exibindoLixeira || !formulario.reportValidity()) return;
        const id = formulario.dataset.id;
        const dados = new FormData(formulario);
        const modo = dados.get('tipoConferencia');
        const andamento = dados.get('novoAndamento')?.toString().trim();
        if (modo === 'igual') await conferirIntimacao(id);
        else if (modo === 'mudou' && andamento) await conferirIntimacao(id, andamento, dados.get('dataAndamento'));
    });
    document.getElementById('rotina-agenda-dias').addEventListener('click', evento => {
        const protocolo = evento.target.closest('[data-agenda-intimacao]');
        if (!protocolo) return;
        intimacaoSelecionadaId = protocolo.dataset.agendaIntimacao;
        faseAtiva = 'TODAS';
        filtroSituacao = 'TODAS';
        filtroFila = 'TODAS';
        document.getElementById('filtro-situacao-intimacao').value = 'TODAS';
        renderizarIntimacoes();
        document.querySelector('.rotina-fila-cartao.selecionado')?.scrollIntoView({block:'nearest', behavior:'smooth'});
    });
    document.querySelector('.rotina-agenda-controles').addEventListener('click', evento => {
        const deslocamento = evento.target.closest('[data-agenda-semana]');
        if (deslocamento) deslocamentoSemanaAgenda += Number(deslocamento.dataset.agendaSemana);
        else if (evento.target.closest('[data-agenda-hoje]')) deslocamentoSemanaAgenda = 0;
        else return;
        renderizarAgendaIntimacoes();
    });
    document.getElementById('importar-intimacoes').addEventListener('change', importarIntimacoesCsv);
    document.getElementById('btn-exportar-intimacoes').addEventListener('click', exportarIntimacoesCsv);
    document.getElementById('btn-fechar-rtd-notificacao').addEventListener('click', fecharEnvioRtd);
    document.getElementById('btn-cancelar-rtd-notificacao').addEventListener('click', fecharEnvioRtd);
    document.getElementById('btn-nova-notificacao-rtd').addEventListener('click', prepararProximoEnvioRtd);
    document.getElementById('modal-rtd-notificacao').addEventListener('click', evento => {
        if (evento.target !== evento.currentTarget) return;
        // Um clique/soltura do mouse fora do painel não fecha nem aciona a tela
        // que está atrás do modal. O usuário fecha pelo botão explícito.
        evento.preventDefault();
        evento.stopPropagation();
        if (!envioRtdEmCurso) {
            document.getElementById('rtd-envio-status').textContent =
                'A preparação continua aberta. Use “Fechar por agora” para sair sem perder o progresso.';
        }
    });
    document.getElementById('btn-buscar-cartorios-rtd').addEventListener('click', buscarCartoriosRtd);
    document.getElementById('rtd-arquivo-notificacao').addEventListener('change', () => {
        arquivoRtdPendente = null;
        document.getElementById('btn-repetir-envio-pdf-rtd').hidden = true;
        void extrairDocumentoRtdSelecionado();
    });
    document.getElementById('btn-repetir-envio-pdf-rtd').addEventListener('click', () => {
        if (arquivoRtdPendente) void extrairDocumentoRtdSelecionado(arquivoRtdPendente);
    });
    document.getElementById('btn-adicionar-notificado-rtd').addEventListener('click', novoCampoNotificado);
    document.getElementById('btn-adicionar-endereco-rtd').addEventListener('click', () => novoCampoNotificado({copiarPessoa:true}));
    document.getElementById('btn-abrir-pasta-rtd').addEventListener('click', () => {
        const id = document.getElementById('rtd-envio-intimacao-id').value;
        const item = intimacoes.find(registro => registro.id === id);
        if (item) abrirPastaIntimacao(item.protocolo);
    });
    document.getElementById('rtd-notificados-lista').addEventListener('click', evento => {
        if (evento.target.closest('[data-remover-notificado]')) evento.target.closest('[data-rtd-notificado]')?.remove();
    });
    document.getElementById('modal-rtd-notificacao').addEventListener('input', evento => {
        if (evento.target.matches('#rtd-remetente-documento,#rtd-credor-cnpj,[data-pessoa="CpfCnpj"],[data-endereco="CEP"]')) {
            const limite = evento.target.matches('[data-endereco="CEP"]') ? 8 : 14;
            evento.target.value = evento.target.value.replace(/\D/g, '').slice(0, limite);
        }
        if (evento.target.matches('[data-endereco="UF"],#rtd-destino-uf')) evento.target.value = evento.target.value.toUpperCase();
    });
    document.getElementById('form-rtd-notificacao').addEventListener('submit', enviarNotificacaoRtd);
    document.getElementById('btn-fechar-rtd-exclusao').addEventListener('click', fecharExclusaoRtd);
    document.getElementById('btn-cancelar-rtd-exclusao').addEventListener('click', fecharExclusaoRtd);
    document.getElementById('modal-rtd-exclusao').addEventListener('click', evento => {
        if (evento.target.id === 'modal-rtd-exclusao' && !exclusaoRtdEmCurso) fecharExclusaoRtd();
    });
    document.getElementById('form-rtd-exclusao').addEventListener('submit', confirmarExclusaoRtd);
    document.addEventListener('keydown', evento => {
        if (evento.key === 'Escape' && !exclusaoRtdEmCurso
            && document.getElementById('modal-rtd-exclusao').classList.contains('aberta')) fecharExclusaoRtd();
    });
    renderizarIntimacoes();
}

