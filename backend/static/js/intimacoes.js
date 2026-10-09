import {requisicaoAeri} from './api.js?v=20260902-arquivo-v1';
import {baixarArquivo, escaparHtml, hojeLocal} from './util.js';
import {temNovidadeRtd, ordenarNovidadesRtd, resumoRtd, detalhesRtd} from './rtd_intimacoes.js?v=20261006-fluxo-v2';
import {abrirDocumentosIntimacao, iniciarDocumentosIntimacao} from './intimacao_documentos.js?v=20261009-v1';

let intimacoes = [];
const intimacoesPendentes = new Set();
const detalhesAbertos = new Set();
const historicosOperacionais = new Map();
let intimacaoCheckId = null;
let faseAtiva = 'INTIMACAO';
const FASES_INTIMACAO = ['INTIMACAO', 'EDITAL', 'CONSOLIDACAO'];
let filtroSituacao = 'TODAS';
let exibindoLixeira = false;
let statusRtd = null;
let statusRtdConsultado = 0;
const enviosRtdPorIntimacao = new Map();
const enviosRtdCarregando = new Set();
let envioRtdEmCurso = false;
let extracaoRtdEmCurso = false;
let versaoExtracaoRtd = 0;
let filaRtdSeparada = null;
let filaRtdDosOriginais = false;
let indiceFilaRtdSeparada = 0;
let filaRtdFinalizada = false;

function novaChaveOperacaoRtd() {
    return globalThis.crypto?.randomUUID?.()
        || 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, letra => {
            const numero = Math.random() * 16 | 0;
            return (letra === 'x' ? numero : (numero & 0x3 | 0x8)).toString(16);
        });
}

function renderizarPainelRtd() {
    const painel = document.getElementById('rtd-painel');
    if (!painel) return;
    const pedidosNovos = intimacoes.flatMap(item => item.rtd || []).filter(pedido => pedido.novo).length;
    const sync = statusRtd?.sincronizacao;
    const contagens = statusRtd?.contagens;
    const ultima = sync?.ultimo_sucesso;
    const atrasado = ultima && Date.now() - Date.parse(ultima) > 10 * 60000;
    const horario = ultima ? new Intl.DateTimeFormat('pt-BR', {dateStyle:'short', timeStyle:'short'}).format(new Date(ultima)) : null;
    painel.innerHTML = `<div class="rtd-painel-cabecalho"><div><span class="rtd-origem">ACOMPANHAMENTO EXTERNO</span><strong>Central RTD</strong></div>
        <span class="rtd-contador ${pedidosNovos ? 'com-novidade' : ''}">${pedidosNovos ? `${pedidosNovos} ${pedidosNovos === 1 ? 'pedido atualizado' : 'pedidos atualizados'}` : 'Sem novidades para conferir'}</span></div>
        <p>${horario ? `Última consulta concluída com sucesso: ${horario}.` : 'Aguardando a primeira sincronização do executor.'} A Central é consultada automaticamente a cada 5 minutos.</p>
        <p class="rtd-separacao">O andamento da Central RTD é independente da fase, do último andamento e das conferências internas do AERI.</p>
        ${atrasado ? '<p role="status">Atualização atrasada. Confira se o executor está ligado.</p>' : ''}
        ${sync?.erro ? `<p role="alert">${escaparHtml(sync.erro)}</p>` : ''}
        ${contagens ? `<div class="rtd-metricas"><span>${contagens.vinculados} vinculados</span><span>${contagens.fila} aguardando consulta</span><span>${contagens.falhas} com falha</span><span>${contagens.sem_vinculo} sem vínculo</span></div>` : ''}
        ${pedidosNovos ? '<button type="button" data-rtd-novidades>Ver atualizações</button>' : ''}
        ${statusRtd?.revisao?.length ? `<details><summary>Pedidos que precisam de revisão</summary><ul>${statusRtd.revisao.map(p => `<li>${escaparHtml(p.protocolo)} · ${escaparHtml(p.in_documento || '')} · ${escaparHtml(p.erro || ({SEM_IN:'IN não identificado no documento',IN_AMBIGUO:'Mais de um IN no documento',IN_NAO_CADASTRADO:'IN ainda não cadastrado',CONFLITO:'Vínculo divergente'})[p.vinculo] || p.vinculo)}</li>`).join('')}</ul></details>` : ''}`;
}

function pode(permissao) {
    return ['ADMIN', 'SUBSTITUTO'].includes(document.body.dataset.perfil) || Boolean(window.aeriPermissoes?.[permissao]);
}

function cargoAdministrativo() {
    return ['ADMIN', 'SUBSTITUTO'].includes(document.body.dataset.perfil);
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
        'Data do andamento AERI', 'Andamento da Central RTD', 'Pasta', 'Ações',
    ];
    const tabela = document.querySelector('.rotina-table');
    tabela.classList.remove('rotina-table-fase-inicial');
    document.getElementById('rotina-cabecalho').innerHTML = titulos.map(titulo => `<th>${titulo}</th>`).join('');
}

function botaoPastaIntimacao(item) {
    const titulo = `Abrir pasta de ${item.protocolo}`;
    return `<button class="rotina-folder-btn ativo" data-acao="abrir-pasta" data-protocolo="${escaparHtml(item.protocolo)}" title="${escaparHtml(titulo)}" aria-label="${escaparHtml(titulo)}">
        <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M3 7.5A2.5 2.5 0 0 1 5.5 5H10l2 2h6.5A2.5 2.5 0 0 1 21 9.5v7A2.5 2.5 0 0 1 18.5 19h-13A2.5 2.5 0 0 1 3 16.5z"/>
        </svg>
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
            ${campoCard('Protocolo RTD', valorOuTraco(item.protocoloRtd))}
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
        <section class="rtd-envios-historico">
            <div class="rtd-envio-cabecalho"><div><span class="rtd-origem">SOLICITAÇÕES ENVIADAS PELO AERI</span><h3>Histórico de envios</h3></div>
                ${pode('alterar_intimacoes') && item.fase === 'INTIMACAO' ? `<button type="button" data-acao="novo-envio-rtd" data-id="${item.id}">Preparar notificação</button>` : ''}
            </div>
            ${listaEnvios}
            <p>Enviar uma notificação cria um novo pedido na Central RTD; isso não responde nem altera o andamento interno do AERI.</p>
        </section>
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

function abrirEnvioRtd(id, paresRtd = null, dadosCredor = null) {
    const item = intimacoes.find(registro => registro.id === id);
    if (!item || !pode('alterar_intimacoes')) return;
    versaoExtracaoRtd += 1;
    extracaoRtdEmCurso = false;
    document.getElementById('form-rtd-notificacao').reset();
    document.getElementById('rtd-arquivo-notificacao').disabled = false;
    document.getElementById('rtd-extracao-status').textContent = '';
    document.getElementById('rtd-envio-intimacao-id').value = id;
    document.getElementById('rtd-envio-operacao-id').value = novaChaveOperacaoRtd();
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
    document.getElementById('modal-rtd-notificacao').classList.add('aberta');
}

function fecharEnvioRtd() {
    if (envioRtdEmCurso) return;
    versaoExtracaoRtd += 1;
    document.getElementById('modal-rtd-notificacao').classList.remove('aberta');
}

async function extrairDocumentoRtdSelecionado() {
    const arquivoInput = document.getElementById('rtd-arquivo-notificacao');
    const arquivo = arquivoInput.files?.[0];
    const status = document.getElementById('rtd-envio-status');
    const statusExtracao = document.getElementById('rtd-extracao-status');
    const mostrarStatus = mensagem => { status.textContent = mensagem; statusExtracao.textContent = mensagem; };
    const id = document.getElementById('rtd-envio-intimacao-id').value;
    if (!arquivo || !id) return;
    if (arquivo.name.toLocaleLowerCase('pt-BR') !== 'documentos rtd.pdf' || arquivo.size > 4_300_000) {
        mostrarStatus('Selecione Documentos RTD.pdf da pasta deste IN, com até 4,3 MB.');
        return;
    }
    if (filaRtdDosOriginais) {
        mostrarStatus('Devedores e endereços já vieram dos PDFs originais. Confira-os com o Documentos RTD.pdf anexado antes de enviar.');
        return;
    }
    filaRtdSeparada = null;
    indiceFilaRtdSeparada = 0;
    filaRtdFinalizada = false;
    document.getElementById('rtd-notificados-lista').replaceChildren();
    novoCampoNotificado();
    atualizarFilaRtd();
    const versao = ++versaoExtracaoRtd;
    extracaoRtdEmCurso = true;
    document.getElementById('btn-confirmar-rtd-notificacao').disabled = true;
    mostrarStatus('Lendo os devedores e endereços do PDF selecionado…');
    try {
        const corpo = new FormData();
        corpo.set('arquivo', arquivo, arquivo.name);
        const dados = await requisicaoAeri(`/api/intimacoes/${id}/extrair-documento-rtd`, {method:'POST', body:corpo});
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
            mostrarStatus('O PDF não forneceu uma combinação válida de devedor e endereço de Morrinhos. Revise o documento e preencha manualmente.');
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
        if (versao === versaoExtracaoRtd) mostrarStatus(`${erro.message} Os campos continuam disponíveis para preenchimento manual.`);
    } finally {
        if (versao === versaoExtracaoRtd) {
            extracaoRtdEmCurso = false;
            document.getElementById('btn-confirmar-rtd-notificacao').disabled = filaRtdFinalizada;
        }
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
    const pdfValido = arquivoItem => arquivoItem && arquivoItem.size <= 4_300_000
        && arquivoItem.name.toLocaleLowerCase('pt-BR').endsWith('.pdf')
        && (!arquivoItem.type || arquivoItem.type === 'application/pdf');
    if (!pdfValido(arquivo)) {
        status.textContent = 'Selecione o PDF Documentos RTD.pdf, com até 4,3 MB.';
        return;
    }
    if (arquivo.name.toLocaleLowerCase('pt-BR') !== 'documentos rtd.pdf') {
        status.textContent = 'Selecione o arquivo chamado exatamente “Documentos RTD.pdf” da pasta deste IN.';
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
    const dados = new FormData();
    dados.set('intimacao_id', document.getElementById('rtd-envio-intimacao-id').value);
    dados.set('chave_operacao', document.getElementById('rtd-envio-operacao-id').value);
    dados.set('pedido', JSON.stringify(pedido));
    dados.set('arquivo', arquivo, arquivo.name);
    envioRtdEmCurso = true;
    document.getElementById('btn-confirmar-rtd-notificacao').disabled = true;
    document.getElementById('btn-cancelar-rtd-notificacao').disabled = true;
    document.getElementById('btn-fechar-rtd-notificacao').disabled = true;
    status.textContent = 'Enviando o documento e solicitando a notificação à Central. Não feche esta janela.';
    try {
        const resultado = await requisicaoAeri('/api/rtd-intimacoes/notificacoes', {method:'POST', body:dados});
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
                status.textContent += ` Sequência concluída: ${filaRtdSeparada.length} pedidos individuais.`;
            }
        }
    } catch (erro) {
        status.textContent = erro.message;
        const id = document.getElementById('rtd-envio-intimacao-id').value;
        await carregarEnviosRtd(id, true);
        renderizarIntimacoes();
    } finally {
        envioRtdEmCurso = false;
        document.getElementById('btn-confirmar-rtd-notificacao').disabled = filaRtdFinalizada;
        document.getElementById('btn-cancelar-rtd-notificacao').disabled = false;
        document.getElementById('btn-fechar-rtd-notificacao').disabled = false;
    }
}

function renderizarIntimacoes() {
    const tbody = document.getElementById('rotina-tbody');
    renderizarCabecalho();
    document.querySelector('label[for="importar-intimacoes"]').hidden = !(pode('criar_intimacoes') && pode('alterar_intimacoes'));
    document.getElementById('btn-nova-intimacao').hidden = !pode('criar_intimacoes');
    const termo = document.getElementById('busca-intimacao').value.toLowerCase().trim();
    const daFase = intimacoes.filter(item => faseAtiva === 'TODAS' || item.fase === faseAtiva);
    const filtradas = daFase.filter(item => [
        item.protocolo, item.protocoloRtd, item.numeroOsTri7, item.protocoloTri7,
        item.credor, item.devedor, item.nomeAndamento, item.certidaoDecursoPrazo, ...(item.rtd || []).flatMap(p => [p.protocolo,p.situacao]),
    ]
        .some(valor => String(valor || '').toLowerCase().includes(termo)))
        .filter(item => filtroSituacao === 'TODAS' || (filtroSituacao === 'RTD' ? temNovidadeRtd(item) : filtroSituacao === 'PENDENTES' ? ['vermelho','cinza'].includes(situacaoIntimacao(item).classe) : situacaoIntimacao(item).classe === filtroSituacao))
        .sort((a, b) => ordenarNovidadesRtd(a,b) || situacaoIntimacao(a).ordem - situacaoIntimacao(b).ordem || a.protocolo.localeCompare(b.protocolo));

    tbody.innerHTML = filtradas.map(item => {
        const situacao = situacaoIntimacao(item);
        const acoes = acoesIntimacao(item, true);
        const linha = `<tr class="rotina-row rotina-row-${situacao.classe}">
            <td><span class="rotina-status ${situacao.classe}"><i></i>${situacao.rotulo}</span><small>${situacao.detalhe}</small><small>Última conferência: ${item.ultimaConferencia ? formatarDataRotina(item.ultimaConferencia) : '—'}</small></td>
            <td><strong class="rotina-protocolo">${escaparHtml(item.protocolo)}</strong></td>
            <td>${escaparHtml(item.credor)}</td>
            <td>${escaparHtml(item.devedor)}${item.devedorFonte === 'RTD' ? '<small>Identificado no documento RTD</small>' : ''}</td>
            <td>${escaparHtml(item.nomeAndamento || 'Não informado')}</td>
            <td>${formatarDataRotina(item.ultimoAndamento)}</td>
            <td class="rtd-coluna">${resumoRtd(item)}</td>
            <td>${botaoPastaIntimacao(item)}</td>
            <td>${acoes}</td>
        </tr>`;
        if (!detalhesAbertos.has(item.id)) return linha;
        return `${linha}<tr class="rotina-detalhes-row"><td colspan="9">${detalhesFaseInicial(item)}</td></tr>`;
    }).join('') || '<tr><td colspan="9" class="rotina-vazio">Nenhuma intimação cadastrada. Use “Nova intimação” ou importe sua planilha em CSV.</td></tr>';

    const contagens = {verde:0, amarelo:0, vermelho:0, cinza:0};
    daFase.forEach(item => contagens[situacaoIntimacao(item).classe]++);
    document.getElementById('rotina-resumo').innerHTML = [
        ['verde','Conferidas hoje',contagens.verde], ['amarelo','Vencem hoje',contagens.amarelo],
        ['vermelho','Atrasadas',contagens.vermelho], ['cinza','Sem atividade',contagens.cinza],
    ].map(([classe, rotulo, valor]) => `<div class="rotina-resumo-card ${classe}"><span>${rotulo}</span><strong>${valor}</strong></div>`).join('');
    FASES_INTIMACAO.forEach(fase => {
        const total = intimacoes.filter(item => item.fase === fase).length;
        document.querySelector(`[data-total-fase="${fase}"]`).textContent = total;
    });
    document.querySelectorAll('.rotina-fase-btn').forEach(botao => {
        const ativa = botao.dataset.fase === faseAtiva;
        botao.classList.toggle('ativa', ativa);
        botao.setAttribute('aria-selected', String(ativa));
    });
    document.getElementById('rotina-total').textContent = `${filtradas.length} de ${daFase.length} nesta fase`;
    renderizarPainelRtd();
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
        if (Date.now() - statusRtdConsultado > 60000) {
            statusRtdConsultado = Date.now();
            try { statusRtd = await requisicaoAeri('/api/rtd-intimacoes/status', {background:true}); }
            catch (_) { statusRtd = {sincronizacao:{erro:'Não foi possível obter o estado da sincronização RTD.'}}; }
        }
    } catch (falha) {
        console.error(falha);
        // Mantém a última lista conhecida em vez de zerar: uma falha
        // passageira do polling não deve apagar tudo que já estava na tela.
    }
    renderizarIntimacoes();
}

export function limparIntimacoes() {
    intimacoes = [];
    statusRtd = null; statusRtdConsultado = 0;
    renderizarIntimacoes();
}

let edicaoIntimacaoAtualizadoEm = null;

function abrirFormularioIntimacao() {
    if (!pode('criar_intimacoes')) return;
    edicaoIntimacaoAtualizadoEm = null;
    document.getElementById('form-intimacao').reset();
    document.getElementById('intimacao-id').value = '';
    document.getElementById('titulo-form-intimacao').textContent = 'Nova intimação';
    document.getElementById('intimacao-andamento').value = hojeLocal();
    document.getElementById('intimacao-fase').value = faseAtiva;
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

async function conferirIntimacao(id, novoAndamento = null) {
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
            ultimoAndamento: hoje,
            fase: fasePorAndamento(novoAndamento, anterior.fase),
        } : {}),
    };
    fecharCheckIntimacao();
    renderizarIntimacoes();
    try {
        const opcoes = {method:'POST'};
        if (novoAndamento) {
            opcoes.headers = {'Content-Type':'application/json'};
            opcoes.body = JSON.stringify({nomeAndamento: novoAndamento});
        }
        const salvo = await requisicaoAeri(`/api/intimacoes/${id}/conferir`, opcoes);
        const indiceAtual = intimacoes.findIndex(item => item.id === id);
        if (indiceAtual >= 0) intimacoes[indiceAtual] = salvo;
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
        item.protocolo, item.protocoloRtd || '', item.numeroOsTri7 || '', item.saldoOs ?? '',
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
    if (botao.dataset.acao === 'abrir-pasta') abrirPastaIntimacao(botao.dataset.protocolo);
    if (botao.dataset.acao === 'gerar-desistencia') gerarNotaDesistencia(botao.dataset.protocolo);
    if (botao.dataset.acao === 'detalhes') {
        if (detalhesAbertos.has(botao.dataset.id)) detalhesAbertos.delete(botao.dataset.id);
        else {
            detalhesAbertos.add(botao.dataset.id);
            await Promise.all([carregarHistoricoOperacional(botao.dataset.id), carregarEnviosRtd(botao.dataset.id)]);
        }
        renderizarIntimacoes();
    }
    if (botao.dataset.acao === 'novo-envio-rtd') abrirEnvioRtd(botao.dataset.id);
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
        const css = document.createElement('link'); css.id='rtd-estilos'; css.rel='stylesheet'; css.href='/static/css/rtd_intimacoes.css?v=20261009-rtd-procedimento-v1'; document.head.appendChild(css);
        const painel = document.createElement('section'); painel.id='rtd-painel'; painel.className='rtd-painel'; painel.setAttribute('aria-label','Acompanhamento das diligências RTD');
        document.getElementById('rotina-resumo').before(painel);
        painel.addEventListener('click', async evento => {
            if (!evento.target.closest('[data-rtd-novidades]')) return;
            faseAtiva='TODAS'; filtroSituacao='RTD'; exibindoLixeira=false;
            document.getElementById('busca-intimacao').value='';
            document.getElementById('filtro-situacao-intimacao').value='RTD';
            await carregarIntimacoes();
            document.querySelector('.rotina-table-wrap')?.scrollIntoView({behavior:'smooth', block:'start'});
        });
    }
    window.addEventListener('aeri:abrir-alerta', async evento => {
        if (evento.detail.modulo !== 'rotina') return;
        faseAtiva='TODAS'; filtroSituacao='PENDENTES'; exibindoLixeira=false;
        document.getElementById('filtro-situacao-intimacao').value='PENDENTES';
        await carregarIntimacoes();
    });
    const busca = document.getElementById('busca-intimacao');
    const seletor = document.createElement('select');
    seletor.id = 'filtro-situacao-intimacao';
    seletor.innerHTML = '<option value="TODAS">Todas as situações</option><option value="PENDENTES">Pendentes / atrasadas / sem atividade</option><option value="verde">Conferidas hoje</option><option value="amarelo">Vencem hoje</option><option value="vermelho">Atrasadas</option><option value="cinza">Sem atividade</option>';
    seletor.addEventListener('change', () => { filtroSituacao = seletor.value; renderizarIntimacoes(); });
    seletor.insertAdjacentHTML('beforeend', '<option value="RTD">Novidades do RTD</option>');
    busca.parentElement.appendChild(seletor);
    if (cargoAdministrativo()) {
        const lixeira = document.createElement('button');
        lixeira.type = 'button'; lixeira.className = 'rotina-btn-secondary'; lixeira.textContent = 'Lixeira';
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
    document.getElementById('intimacao-valor-pago').addEventListener('input', atualizarSaldoFormulario);
    document.getElementById('intimacao-valor-usado').addEventListener('input', atualizarSaldoFormulario);
    document.getElementById('intimacao-protocolo-rtd').addEventListener('input', evento => {
        evento.target.value = evento.target.value.replace(/\D/g, '').slice(0, 17);
    });
    document.getElementById('rotina-tbody').addEventListener('click', tratarAcaoTabela);
    document.getElementById('importar-intimacoes').addEventListener('change', importarIntimacoesCsv);
    document.getElementById('btn-exportar-intimacoes').addEventListener('click', exportarIntimacoesCsv);
    document.getElementById('btn-fechar-rtd-notificacao').addEventListener('click', fecharEnvioRtd);
    document.getElementById('btn-cancelar-rtd-notificacao').addEventListener('click', fecharEnvioRtd);
    document.getElementById('modal-rtd-notificacao').addEventListener('click', evento => {
        if (evento.target.id === 'modal-rtd-notificacao') fecharEnvioRtd();
    });
    document.getElementById('btn-buscar-cartorios-rtd').addEventListener('click', buscarCartoriosRtd);
    document.getElementById('rtd-arquivo-notificacao').addEventListener('change', extrairDocumentoRtdSelecionado);
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
    renderizarIntimacoes();
}
