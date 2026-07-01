import {requisicaoAeri} from './api.js';
import {baixarArquivo, escaparHtml, hojeLocal} from './util.js';

let intimacoes = [];
const intimacoesPendentes = new Set();

function diasDesde(data) {
    if (!data) return null;
    const hoje = new Date(`${hojeLocal()}T00:00:00`);
    const referencia = new Date(`${data}T00:00:00`);
    return Math.max(0, Math.floor((hoje - referencia) / 86400000));
}

function situacaoIntimacao(item) {
    if (!item.ultimaConferencia) return {classe:'vermelho', rotulo:'Pendente', detalhe:'Nunca conferida', ordem:0};
    const dias = diasDesde(item.ultimaConferencia);
    if (dias === 0) return {classe:'verde', rotulo:'Conferida', detalhe:'Conferida hoje', ordem:3};
    if (dias === 1) return {classe:'amarelo', rotulo:'Vence hoje', detalhe:'Último check ontem', ordem:1};
    if (dias <= 4) return {classe:'vermelho', rotulo:'Atrasada', detalhe:`Sem check há ${dias} dias`, ordem:0};
    return {classe:'cinza', rotulo:'Sem atividade', detalhe:`Sem check há ${dias} dias`, ordem:2};
}

function formatarDataRotina(data) {
    if (!data) return '—';
    return new Intl.DateTimeFormat('pt-BR').format(new Date(`${data}T12:00:00`));
}

function renderizarIntimacoes() {
    const tbody = document.getElementById('rotina-tbody');
    const termo = document.getElementById('busca-intimacao').value.toLowerCase().trim();
    const filtradas = intimacoes.filter(item => [item.protocolo, item.credor, item.devedor]
        .some(valor => String(valor || '').toLowerCase().includes(termo)))
        .sort((a, b) => situacaoIntimacao(a).ordem - situacaoIntimacao(b).ordem || a.protocolo.localeCompare(b.protocolo));

    tbody.innerHTML = filtradas.map(item => {
        const situacao = situacaoIntimacao(item);
        const pendente = intimacoesPendentes.has(item.id);
        return `<tr class="rotina-row rotina-row-${situacao.classe}">
            <td><span class="rotina-status ${situacao.classe}"><i></i>${situacao.rotulo}</span><small>${situacao.detalhe}</small></td>
            <td><strong class="rotina-protocolo">${escaparHtml(item.protocolo)}</strong></td>
            <td>${escaparHtml(item.credor)}</td>
            <td>${escaparHtml(item.devedor)}</td>
            <td>${formatarDataRotina(item.ultimoAndamento)}</td>
            <td>${item.ultimaConferencia ? formatarDataRotina(item.ultimaConferencia) : '—'}</td>
            <td><div class="rotina-row-actions">
                <button class="rotina-check" data-acao="conferir" data-id="${item.id}" title="Registrar conferência de hoje" ${pendente ? 'disabled' : ''}>${pendente ? 'Salvando...' : '✓ Check'}</button>
                <button data-acao="editar" data-id="${item.id}" title="Editar">Editar</button>
                <button class="perigo" data-acao="excluir" data-id="${item.id}" title="Excluir">Excluir</button>
            </div></td>
        </tr>`;
    }).join('') || '<tr><td colspan="7" class="rotina-vazio">Nenhuma intimação cadastrada. Use “Nova intimação” ou importe sua planilha em CSV.</td></tr>';

    const contagens = {verde:0, amarelo:0, vermelho:0, cinza:0};
    intimacoes.forEach(item => contagens[situacaoIntimacao(item).classe]++);
    document.getElementById('rotina-resumo').innerHTML = [
        ['verde','Conferidas hoje',contagens.verde], ['amarelo','Vencem hoje',contagens.amarelo],
        ['vermelho','Atrasadas',contagens.vermelho], ['cinza','Sem atividade',contagens.cinza],
    ].map(([classe, rotulo, valor]) => `<div class="rotina-resumo-card ${classe}"><span>${rotulo}</span><strong>${valor}</strong></div>`).join('');
    document.getElementById('rotina-total').textContent = `${filtradas.length} de ${intimacoes.length} intimações`;
}

export async function carregarIntimacoes() {
    try {
        intimacoes = await requisicaoAeri('/api/intimacoes');
    } catch (falha) {
        console.error(falha);
        intimacoes = [];
    }
    renderizarIntimacoes();
}

export function limparIntimacoes() {
    intimacoes = [];
    renderizarIntimacoes();
}

function abrirFormularioIntimacao() {
    document.getElementById('form-intimacao').reset();
    document.getElementById('intimacao-id').value = '';
    document.getElementById('titulo-form-intimacao').textContent = 'Nova intimação';
    document.getElementById('intimacao-andamento').value = hojeLocal();
    document.getElementById('modal-intimacao').classList.add('aberta');
    document.getElementById('intimacao-protocolo').focus();
}

function fecharFormularioIntimacao() {
    document.getElementById('modal-intimacao').classList.remove('aberta');
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
        ultimoAndamento: document.getElementById('intimacao-andamento').value,
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
        alert(falha.message);
    } finally {
        botaoSalvar.disabled = false;
        botaoSalvar.textContent = 'Salvar intimação';
    }
}

function editarIntimacao(id) {
    const item = intimacoes.find(atual => atual.id === id);
    if (!item) return;
    document.getElementById('intimacao-id').value = item.id;
    document.getElementById('intimacao-protocolo').value = item.protocolo;
    document.getElementById('intimacao-credor').value = item.credor;
    document.getElementById('intimacao-devedor').value = item.devedor;
    document.getElementById('intimacao-andamento').value = item.ultimoAndamento;
    document.getElementById('titulo-form-intimacao').textContent = 'Editar intimação';
    document.getElementById('modal-intimacao').classList.add('aberta');
}

async function conferirIntimacao(id) {
    const indice = intimacoes.findIndex(item => item.id === id);
    if (indice < 0 || intimacoesPendentes.has(id)) return;
    const anterior = {...intimacoes[indice], historico:[...(intimacoes[indice].historico || [])]};
    const hoje = hojeLocal();
    intimacoesPendentes.add(id);
    intimacoes[indice] = {...anterior, ultimaConferencia: hoje, historico: [...new Set([...(anterior.historico || []), hoje])]};
    renderizarIntimacoes();
    try {
        const salvo = await requisicaoAeri(`/api/intimacoes/${id}/conferir`, {method:'POST'});
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
    if (!confirm('Deseja excluir esta intimação?')) return;
    try {
        await requisicaoAeri(`/api/intimacoes/${id}`, {method:'DELETE'});
        intimacoes = intimacoes.filter(item => item.id !== id);
        renderizarIntimacoes();
    } catch (falha) {
        alert(falha.message);
    }
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
        const ip = indice('protocolo'), ic = indice('credor'), id = indice('devedor'), ia = indice('ultimo andamento');
        if ([ip,ic,id,ia].some(i => i < 0)) return alert('Use as colunas: Protocolo, Credor, Devedor e Data do Último Andamento.');
        let importados = 0;
        const novos = [];
        linhas.slice(1).forEach(linha => {
            const colunas = lerLinhaCsv(linha, separador);
            const protocolo = (colunas[ip] || '').trim().toUpperCase();
            if (!/^IN\d{8}C$/.test(protocolo) || intimacoes.some(item => item.protocolo === protocolo) || novos.some(item => item.protocolo === protocolo)) return;
            const item = {protocolo, credor:(colunas[ic] || '').trim(), devedor:(colunas[id] || '').trim(), ultimoAndamento:converterDataImportada(colunas[ia])};
            if (item.ultimoAndamento) novos.push(item);
        });
        for (const item of novos) {
            try {
                intimacoes.push(await requisicaoAeri('/api/intimacoes', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(item)}));
                importados++;
            } catch (falha) {
                console.warn(item.protocolo, falha.message);
            }
        }
        renderizarIntimacoes();
        input.value = '';
        alert(`${importados} intimações importadas.`);
    };
    leitor.readAsText(arquivo, 'UTF-8');
}

function exportarIntimacoesCsv() {
    const cabecalho = 'Protocolo;Credor;Devedor;Data do Último Andamento;Última Conferência';
    const linhas = intimacoes.map(item => [item.protocolo,item.credor,item.devedor,item.ultimoAndamento,item.ultimaConferencia || '']
        .map(valor => `"${String(valor).replace(/"/g,'""')}"`).join(';'));
    baixarArquivo('\uFEFF' + [cabecalho,...linhas].join('\n'), 'text/csv;charset=utf-8', `intimacoes-aeri-${hojeLocal()}.csv`);
}

function tratarAcaoTabela(evento) {
    const botao = evento.target.closest('button[data-acao]');
    if (!botao) return;
    if (botao.dataset.acao === 'conferir') conferirIntimacao(botao.dataset.id);
    if (botao.dataset.acao === 'editar') editarIntimacao(botao.dataset.id);
    if (botao.dataset.acao === 'excluir') excluirIntimacao(botao.dataset.id);
}

export function iniciarIntimacoes() {
    document.getElementById('busca-intimacao').addEventListener('input', renderizarIntimacoes);
    document.getElementById('btn-nova-intimacao').addEventListener('click', abrirFormularioIntimacao);
    document.getElementById('btn-fechar-intimacao').addEventListener('click', fecharFormularioIntimacao);
    document.getElementById('btn-cancelar-intimacao').addEventListener('click', fecharFormularioIntimacao);
    document.getElementById('modal-intimacao').addEventListener('click', evento => {
        if (evento.target.id === 'modal-intimacao') fecharFormularioIntimacao();
    });
    document.getElementById('intimacao-protocolo').addEventListener('input', evento => {
        evento.target.value = evento.target.value.toUpperCase();
    });
    document.getElementById('form-intimacao').addEventListener('submit', salvarIntimacao);
    document.getElementById('rotina-tbody').addEventListener('click', tratarAcaoTabela);
    document.getElementById('importar-intimacoes').addEventListener('change', importarIntimacoesCsv);
    document.getElementById('btn-exportar-intimacoes').addEventListener('click', exportarIntimacoesCsv);
    renderizarIntimacoes();
}
