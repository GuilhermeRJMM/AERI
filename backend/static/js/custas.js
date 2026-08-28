import {requisicaoAeri} from './api.js?v=20260824-csrf-v1';
import {escaparHtml} from './util.js';

let itens = [];
let aba = 'andamento';
let filtroStatus = 'TODOS';
let arquivoPendente = null;
const selecionados = new Set();
const formatadorData = new Intl.DateTimeFormat('pt-BR', {dateStyle:'short'});
const STATUS_FINAIS = new Set(['DUPLICADO_DEVOLVIDO', 'RESPONDIDO', 'SEM_PAGAMENTO']);

const STATUS = {
    FAZER_PESQUISA: ['Fazer pesquisa', '#ffffff'],
    BUSCA_REALIZADA: ['Busca realizada', '#ffff00'],
    DUPLICADO_DEVOLVIDO: ['Duplicado / devolvido', '#ff0066'],
    PAGO_PROCESSANDO: ['Pago / processando', '#ffc000'],
    CUSTAS_INFORMADAS: ['Custas informadas', '#00b050'],
    RESPONDIDO: ['Respondido', '#0070c0'],
    SEM_PAGAMENTO: ['Sem pagamento', '#ff0000'],
    CUSTAS_ERRADAS: ['Custas erradas', '#7030a0'],
};

function rotuloModalidade(valor) {
    return valor === 'ALIENACAO_FIDUCIARIA' ? 'Alienação fiduciária' : 'Penhor';
}

function rotuloResultado(valor) {
    return {PENDENTE:'Pendente', POSITIVA:'Positiva', NEGATIVA:'Negativa'}[valor] || valor;
}

function normalizar(valor) {
    return String(valor || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
}

function notificarCustas(mensagem, tipo = 'sucesso', duracao = 3200) {
    let area = document.getElementById('custas-notificacoes');
    if (!area) {
        area = document.createElement('div');
        area.id = 'custas-notificacoes';
        area.className = 'custas-notificacoes';
        area.setAttribute('aria-live', 'polite');
        document.body.appendChild(area);
    }
    const aviso = document.createElement('div');
    aviso.className = `custas-toast ${tipo}`;
    aviso.textContent = mensagem;
    area.appendChild(aviso);
    requestAnimationFrame(() => aviso.classList.add('visivel'));
    if (duracao > 0) window.setTimeout(() => {
        aviso.classList.remove('visivel');
        window.setTimeout(() => aviso.remove(), 180);
    }, duracao);
    return aviso;
}

function removerNotificacao(aviso) {
    if (!aviso) return;
    aviso.classList.remove('visivel');
    window.setTimeout(() => aviso.remove(), 180);
}

function precisaAtencao(item) {
    return item.status === 'CUSTAS_ERRADAS' || [item.nome, item.documento, item.produto, item.safra].includes('NÃO CONSTA');
}

function atualizarResumo() {
    const andamento = itens.filter(item => !item.finalizado).length;
    const finalizados = itens.length - andamento;
    document.getElementById('custas-total-andamento').textContent = andamento;
    document.getElementById('custas-total-finalizado').textContent = finalizados;
    document.getElementById('custas-total-atencao').textContent = itens.filter(precisaAtencao).length;
    document.querySelector('[data-custas-contagem="andamento"]').textContent = andamento;
    document.querySelector('[data-custas-contagem="finalizado"]').textContent = finalizados;
}

function itensFiltrados() {
    const consulta = normalizar(document.getElementById('custas-busca').value);
    return itens.filter(item => {
        if ((aba === 'finalizado') !== Boolean(item.finalizado)) return false;
        if (filtroStatus !== 'TODOS' && item.status !== filtroStatus) return false;
        const texto = [item.pedido, item.nome, item.documento, item.modalidade, item.produto, item.safra, item.resultado, item.numeroRegistro].join(' ');
        return !consulta || normalizar(texto).includes(consulta);
    });
}

function renderizar() {
    atualizarResumo();
    const visiveis = itensFiltrados();
    document.getElementById('custas-total-visivel').textContent = `${visiveis.length} ${visiveis.length === 1 ? 'pedido' : 'pedidos'}`;
    document.getElementById('custas-tbody').innerHTML = visiveis.map(item => {
        const [rotulo, cor] = STATUS[item.status] || [item.status, '#ffffff'];
        const ausente = precisaAtencao(item) ? '<span class="custas-alerta" title="Há informação ausente ou que precisa de revisão">!</span>' : '';
        return `<tr data-row-status="${escaparHtml(item.status)}" style="--custas-cor:${cor}">
            <td data-label="Pedido"><label class="custas-selecao"><input type="checkbox" data-custas-selecionar="${item.id}" ${selecionados.has(item.id) ? 'checked' : ''}><span></span></label><strong class="custas-pedido">${escaparHtml(item.pedido)}</strong>${ausente}<small>${formatadorData.format(new Date(item.atualizadoEm))}</small></td>
            <td data-label="Nome" class="custas-nome">${escaparHtml(item.nome)}</td>
            <td data-label="CPF/CNPJ">${escaparHtml(item.documento)}</td>
            <td data-label="Modalidade"><span class="custas-modalidade">${escaparHtml(rotuloModalidade(item.modalidade))}</span></td>
            <td data-label="Produto">${escaparHtml(item.produto)}</td><td data-label="Safra">${escaparHtml(item.safra)}</td>
            <td data-label="Resultado"><span class="custas-resultado ${item.resultado.toLowerCase()}">${escaparHtml(rotuloResultado(item.resultado))}</span></td>
            <td data-label="Nº registro">${escaparHtml(item.numeroRegistro || '—')}</td>
            <td data-label="Situação"><span class="custas-status"><i></i>${escaparHtml(rotulo)}</span></td>
            <td data-label="Ações"><div class="custas-acoes"><button type="button" data-custas-acao="pesquisar" data-custas-id="${item.id}">Pesquisar registros</button><button type="button" data-custas-acao="historico" data-custas-id="${item.id}">Histórico</button><button type="button" data-custas-acao="editar" data-custas-id="${item.id}">Editar</button>${item.finalizado
                ? `<button type="button" data-custas-acao="reabrir" data-custas-id="${item.id}">Reabrir</button>`
                : `<button type="button" class="concluir" data-custas-acao="finalizar" data-custas-id="${item.id}">Finalizar</button>`}</div></td>
        </tr>`;
    }).join('') || '<tr><td colspan="10" class="rotina-vazio">Nenhum pedido nesta lista.</td></tr>';
    atualizarAcoesLote();
}

function atualizarAcoesLote() {
    const area = document.getElementById('custas-acoes-lote');
    area.hidden = selecionados.size === 0;
    document.getElementById('custas-selecionados').textContent = `${selecionados.size} selecionado${selecionados.size === 1 ? '' : 's'}`;
}

async function executarAcaoLote(acao) {
    if (!selecionados.size) return;
    const verbo = acao === 'FINALIZAR' ? 'finalizar' : 'reabrir';
    if (!confirm(`Deseja ${verbo} ${selecionados.size} pedido(s)?`)) return;
    const aviso = notificarCustas(`${acao === 'FINALIZAR' ? 'Finalizando' : 'Reabrindo'} pedidos…`, 'info', 0);
    try {
        const resposta = await requisicaoAeri('/api/custas/lote', {
            method:'POST', headers:{'Content-Type':'application/json'},
            body:JSON.stringify({acao, ids:[...selecionados]}),
        });
        const porId = new Map(resposta.itens.map(item => [item.id, item]));
        itens = itens.map(item => porId.get(item.id) || item);
        selecionados.clear();
        renderizar();
        notificarCustas(`${resposta.quantidade} pedido(s) atualizado(s).`);
    } catch (erro) {
        notificarCustas(erro.message, 'erro', 5000);
    } finally {
        removerNotificacao(aviso);
    }
}

export async function carregarCustas(opcoes = {}) {
    const admin = ['ADMIN', 'SUBSTITUTO'].includes(document.body.dataset.perfil);
    if (!admin && !window.aeriPermissoes?.gerenciar_custas) return;
    try {
        const recebidos = await requisicaoAeri(
            '/api/custas',
            {background:Boolean(opcoes.background)},
        );
        const atuaisPorId = new Map(itens.map(item => [item.id, item]));
        itens = recebidos.map(recebido => {
            const atual = atuaisPorId.get(recebido.id);
            // A atualização automática roda a cada 5s (INTERVALO_ATUALIZACAO_MS
            // em app.js) e pode buscar o pedido um instante antes de um
            // Salvar/Finalizar/Reabrir ter comitado no banco. Sem essa
            // checagem, essa resposta desatualizada sobrescrevia silenciosamente
            // a mudança que acabou de acontecer (otimista ou já confirmada),
            // fazendo o pedido "voltar" na tela e obrigando a repetir a ação.
            if (atual && new Date(atual.atualizadoEm) > new Date(recebido.atualizadoEm)) return atual;
            return recebido;
        });
        renderizar();
    } catch (erro) {
        document.getElementById('custas-tbody').innerHTML = `<tr><td colspan="10" class="rotina-vazio">${escaparHtml(erro.message)}</td></tr>`;
    }
}

export function limparCustas() {
    itens = [];
    arquivoPendente = null;
    document.getElementById('custas-tbody').innerHTML = '<tr><td colspan="10" class="rotina-vazio">Entre novamente para consultar.</td></tr>';
}

function fecharImportacao() {
    document.getElementById('modal-custas-importacao').classList.remove('aberta');
    document.getElementById('custas-arquivo').value = '';
    arquivoPendente = null;
}

async function prepararImportacao(evento) {
    const arquivo = evento.target.files?.[0];
    if (!arquivo) return;
    arquivoPendente = arquivo;
    const botao = document.querySelector('.custas-importar-btn');
    botao.classList.add('carregando');
    try {
        const dados = await requisicaoAeri('/api/custas/importar', {method:'POST', headers:{'Content-Type':'application/pdf'}, body:arquivo});
        const categorias = dados.categorias || {};
        document.getElementById('custas-importacao-resumo').textContent = `${dados.total} identificados: ${(categorias.novos || []).length} novos, ${(categorias.existentes || []).length} existentes, ${(categorias.incompletos || []).length} incompletos e ${categorias.ignorados || 0} ignorados.`;
        document.getElementById('custas-preview-tbody').innerHTML = dados.itens.map(item => `<tr><td><strong>${escaparHtml(item.pedido)}</strong></td><td>${escaparHtml(item.nome)}<small>${escaparHtml(item.documento)}</small></td><td>${escaparHtml(rotuloModalidade(item.modalidade))}</td><td>${escaparHtml(item.produto)}<small>${escaparHtml(item.safra)}</small></td></tr>`).join('');
        const alerta = document.getElementById('custas-importacao-alerta');
        alerta.hidden = !dados.alertas.length;
        alerta.textContent = dados.alertas.length ? `${dados.alertas.length} pedido(s) possuem campo não identificado. Eles entrarão sinalizados como “NÃO CONSTA” para revisão.` : '';
        document.getElementById('modal-custas-importacao').classList.add('aberta');
    } catch (erro) {
        alert(erro.message);
        fecharImportacao();
    } finally {
        botao.classList.remove('carregando');
    }
}

async function confirmarImportacao() {
    if (!arquivoPendente) return;
    const botao = document.getElementById('btn-confirmar-custas-importacao');
    const arquivo = arquivoPendente;
    botao.disabled = true;
    fecharImportacao();
    const processando = notificarCustas('Adicionando os pedidos à lista…', 'processando', 0);
    try {
        const dados = await requisicaoAeri('/api/custas/importar?confirmar=true', {method:'POST', headers:{'Content-Type':'application/pdf'}, body:arquivo});
        const novos = dados.itensImportados || [];
        const idsNovos = new Set(novos.map(item => item.id));
        itens = [...novos, ...itens.filter(item => !idsNovos.has(item.id))];
        renderizar();
        removerNotificacao(processando);
        notificarCustas(`${dados.importados} pedido(s) adicionado(s).${dados.duplicados ? ` ${dados.duplicados} já existiam e foram preservados.` : ''}`);
    } catch (erro) {
        removerNotificacao(processando);
        notificarCustas(erro.message, 'erro', 5200);
    } finally {
        botao.disabled = false;
    }
}

let edicaoAtualizadoEm = null;

function abrirEdicao(item) {
    edicaoAtualizadoEm = item.atualizadoEm;
    document.getElementById('custas-edicao-id').value = item.id;
    document.getElementById('custas-edicao-titulo').textContent = item.pedido;
    document.getElementById('custas-edicao-nome').value = item.nome;
    document.getElementById('custas-edicao-documento').value = item.documento;
    document.getElementById('custas-edicao-modalidade').value = item.modalidade;
    document.getElementById('custas-edicao-produto').value = item.produto;
    document.getElementById('custas-edicao-safra').value = item.safra;
    document.getElementById('custas-edicao-resultado').value = item.resultado;
    document.getElementById('custas-edicao-registro').value = item.numeroRegistro || '';
    document.getElementById('custas-edicao-status').value = item.status;
    document.getElementById('modal-custas-edicao').classList.add('aberta');
    document.getElementById('custas-edicao-nome').focus();
}

function fecharEdicao() {
    document.getElementById('modal-custas-edicao').classList.remove('aberta');
}

async function salvarEdicao(evento) {
    evento.preventDefault();
    const id = document.getElementById('custas-edicao-id').value;
    const dados = {
        nome: document.getElementById('custas-edicao-nome').value,
        documento: document.getElementById('custas-edicao-documento').value,
        modalidade: document.getElementById('custas-edicao-modalidade').value,
        produto: document.getElementById('custas-edicao-produto').value,
        safra: document.getElementById('custas-edicao-safra').value,
        resultado: document.getElementById('custas-edicao-resultado').value,
        numeroRegistro: document.getElementById('custas-edicao-registro').value,
        status: document.getElementById('custas-edicao-status').value,
        atualizadoEm: edicaoAtualizadoEm,
    };
    const botao = evento.submitter;
    try {
        botao.disabled = true; botao.textContent = 'Salvando…';
        const salvo = await requisicaoAeri(`/api/custas/${id}`, {method:'PUT', headers:{'Content-Type':'application/json'}, body:JSON.stringify(dados)});
        itens = itens.map(item => item.id === salvo.id ? salvo : item);
        fecharEdicao();
        renderizar();
        notificarCustas('Salvo no banco.');
    } catch (erro) {
        if (erro.message.includes('alterado por outra pessoa') || erro.message.includes('já foi finalizado')) {
            fecharEdicao();
            notificarCustas(erro.message, 'erro', 6000);
            carregarCustas();
            return;
        }
        alert(erro.message);
    } finally {
        botao.disabled = false; botao.textContent = 'Salvar alterações';
    }
}

async function acaoTabela(evento) {
    const botao = evento.target.closest('[data-custas-acao]');
    if (!botao) return;
    const item = itens.find(atual => atual.id === botao.dataset.custasId);
    if (!item) return;
    if (botao.dataset.custasAcao === 'editar') return abrirEdicao(item);
    if (botao.dataset.custasAcao === 'pesquisar') {
        botao.disabled = true; botao.textContent = 'Pesquisando…';
        try {
            const resposta = await requisicaoAeri(`/api/custas/${item.id}/pesquisar-registros`, {method:'POST'});
            itens = itens.map(atual => atual.id === item.id ? resposta.item : atual);
            renderizar();
            notificarCustas(`${resposta.resultado}: ${resposta.registros.length} registro(s). Valor: ${new Intl.NumberFormat('pt-BR', {style:'currency', currency:'BRL'}).format(resposta.valor)}.`);
        } catch (erro) { notificarCustas(erro.message, 'erro', 5200); }
        return;
    }
    if (botao.dataset.custasAcao === 'historico') {
        try {
            const historico = await requisicaoAeri(`/api/custas/${item.id}/historico`);
            alert(historico.length ? historico.map(evento => `${new Date(evento.criado_em).toLocaleString('pt-BR')} · ${evento.tipo} · ${evento.usuario || 'sistema'}`).join('\n') : 'Nenhuma movimentação registrada.');
        } catch (erro) { alert(erro.message); }
        return;
    }
    const acao = botao.dataset.custasAcao;
    if (acao === 'finalizar' && item.resultado === 'PENDENTE' && !STATUS_FINAIS.has(item.status)) {
        notificarCustas('Informe o resultado antes de finalizar.', 'erro', 4200);
        return;
    }
    if (!confirm(acao === 'finalizar' ? `Mover ${item.pedido} para Finalizado?` : `Reabrir ${item.pedido}?`)) return;
    const anterior = {...item};
    const otimista = {
        ...item,
        finalizado: acao === 'finalizar',
        status: acao === 'finalizar' && !STATUS_FINAIS.has(item.status) ? 'RESPONDIDO' : item.status,
        atualizadoEm: new Date().toISOString(),
    };
    itens = itens.map(atual => atual.id === item.id ? otimista : atual);
    renderizar();
    try {
        const salvo = await requisicaoAeri(`/api/custas/${item.id}/${acao}`, {method:'POST'});
        itens = itens.map(atual => atual.id === salvo.id ? salvo : atual);
        renderizar();
        notificarCustas(acao === 'finalizar' ? 'Pedido finalizado.' : 'Pedido reaberto.');
    } catch (erro) {
        itens = itens.map(atual => atual.id === anterior.id ? anterior : atual);
        renderizar();
        notificarCustas(erro.message, 'erro', 5200);
    }
}

function trocarAba(evento) {
    const botao = evento.target.closest('[data-custas-aba]');
    if (!botao) return;
    aba = botao.dataset.custasAba;
    document.querySelectorAll('[data-custas-aba]').forEach(item => {
        const ativa = item === botao;
        item.classList.toggle('ativa', ativa);
        item.setAttribute('aria-selected', String(ativa));
    });
    renderizar();
}

function trocarFiltro(evento) {
    const botao = evento.target.closest('[data-custas-status]');
    if (!botao) return;
    filtroStatus = botao.dataset.custasStatus;
    document.querySelectorAll('[data-custas-status]').forEach(item => item.classList.toggle('ativo', item === botao));
    renderizar();
}

export function iniciarCustas() {
    document.getElementById('custas-arquivo').addEventListener('change', prepararImportacao);
    document.getElementById('btn-confirmar-custas-importacao').addEventListener('click', confirmarImportacao);
    document.getElementById('btn-fechar-custas-importacao').addEventListener('click', fecharImportacao);
    document.getElementById('btn-cancelar-custas-importacao').addEventListener('click', fecharImportacao);
    document.getElementById('form-custas-edicao').addEventListener('submit', salvarEdicao);
    document.getElementById('btn-fechar-custas-edicao').addEventListener('click', fecharEdicao);
    document.getElementById('btn-cancelar-custas-edicao').addEventListener('click', fecharEdicao);
    document.getElementById('custas-tbody').addEventListener('click', acaoTabela);
    document.getElementById('custas-tbody').addEventListener('change', evento => {
        const caixa = evento.target.closest('[data-custas-selecionar]');
        if (!caixa) return;
        if (caixa.checked) selecionados.add(caixa.dataset.custasSelecionar);
        else selecionados.delete(caixa.dataset.custasSelecionar);
        atualizarAcoesLote();
    });
    document.getElementById('btn-custas-finalizar-lote').addEventListener('click', () => executarAcaoLote('FINALIZAR'));
    document.getElementById('btn-custas-reabrir-lote').addEventListener('click', () => executarAcaoLote('REABRIR'));
    document.getElementById('btn-custas-limpar-selecao').addEventListener('click', () => { selecionados.clear(); renderizar(); });
    document.querySelector('.custas-abas').addEventListener('click', trocarAba);
    document.getElementById('custas-legenda').addEventListener('click', trocarFiltro);
    document.getElementById('custas-busca').addEventListener('input', renderizar);
}
