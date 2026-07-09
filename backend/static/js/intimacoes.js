import {requisicaoAeri} from './api.js';
import {baixarArquivo, escaparHtml, hojeLocal} from './util.js';

let intimacoes = [];
const intimacoesPendentes = new Set();
let intimacaoCheckId = null;
const PROTOCOLO_PASTA_FUNCIONAL = 'IN01581267C';
const PASTA_BASE_INTIMACOES = 'T:\\Setor Apoio\\Setor Certidao\\04. Processos Intimacao\\02 - Processos SAEC\\07 - 2026\\02 - Agua. pagamento (emolu informados)';
const ABRIDOR_LOCAL_INTIMACOES = 'http://127.0.0.1:8767';

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

function caminhoPastaIntimacao(protocolo) {
    return `${PASTA_BASE_INTIMACOES}\\${protocolo}`;
}

function urlArquivoWindows(caminho) {
    return encodeURI(`file:///${caminho.replace(/\\/g, '/')}`);
}

function botaoPastaIntimacao(item) {
    const funcional = item.protocolo === PROTOCOLO_PASTA_FUNCIONAL;
    const titulo = funcional
        ? `Abrir pasta de ${item.protocolo}`
        : 'Pasta ainda não configurada para este protocolo';
    return `<button class="rotina-folder-btn${funcional ? ' ativo' : ''}" data-acao="abrir-pasta" data-protocolo="${escaparHtml(item.protocolo)}" title="${escaparHtml(titulo)}" ${funcional ? '' : 'disabled'} aria-label="${escaparHtml(titulo)}">
        <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M3 7.5A2.5 2.5 0 0 1 5.5 5H10l2 2h6.5A2.5 2.5 0 0 1 21 9.5v7A2.5 2.5 0 0 1 18.5 19h-13A2.5 2.5 0 0 1 3 16.5z"/>
        </svg>
    </button>`;
}

function renderizarIntimacoes() {
    const tbody = document.getElementById('rotina-tbody');
    document.querySelector('label[for="importar-intimacoes"]').hidden = !(pode('criar_intimacoes') && pode('alterar_intimacoes'));
    document.getElementById('btn-nova-intimacao').hidden = !pode('criar_intimacoes');
    const termo = document.getElementById('busca-intimacao').value.toLowerCase().trim();
    const filtradas = intimacoes.filter(item => [item.protocolo, item.credor, item.devedor, item.nomeAndamento]
        .some(valor => String(valor || '').toLowerCase().includes(termo)))
        .sort((a, b) => situacaoIntimacao(a).ordem - situacaoIntimacao(b).ordem || a.protocolo.localeCompare(b.protocolo));

    tbody.innerHTML = filtradas.map(item => {
        const situacao = situacaoIntimacao(item);
        const pendente = intimacoesPendentes.has(item.id);
        const acoesDisponiveis = [
            pode('conferir_intimacoes') ? `<button class="rotina-check" data-acao="conferir" data-id="${item.id}" title="Registrar conferência de hoje" ${pendente ? 'disabled' : ''}>${pendente ? 'Salvando...' : '✓ Check'}</button>` : '',
            pode('alterar_intimacoes') ? `<button data-acao="editar" data-id="${item.id}" title="Editar">Editar</button>` : '',
            cargoAdministrativo() ? `<button class="perigo" data-acao="excluir" data-id="${item.id}" title="Excluir">Excluir</button>` : '',
        ].filter(Boolean).join('');
        const acoes = acoesDisponiveis ? `<div class="rotina-row-actions">${acoesDisponiveis}</div>` : '<span class="rotina-total">Somente leitura</span>';
        return `<tr class="rotina-row rotina-row-${situacao.classe}">
            <td><span class="rotina-status ${situacao.classe}"><i></i>${situacao.rotulo}</span><small>${situacao.detalhe}</small></td>
            <td><strong class="rotina-protocolo">${escaparHtml(item.protocolo)}</strong></td>
            <td>${escaparHtml(item.credor)}</td>
            <td>${escaparHtml(item.devedor)}</td>
            <td>${escaparHtml(item.nomeAndamento || 'Não informado')}</td>
            <td>${formatarDataRotina(item.ultimoAndamento)}</td>
            <td>${item.ultimaConferencia ? formatarDataRotina(item.ultimaConferencia) : '—'}</td>
            <td>${botaoPastaIntimacao(item)}</td>
            <td>${acoes}</td>
        </tr>`;
    }).join('') || '<tr><td colspan="9" class="rotina-vazio">Nenhuma intimação cadastrada. Use “Nova intimação” ou importe sua planilha em CSV.</td></tr>';

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
    if (!pode('criar_intimacoes')) return;
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
        nomeAndamento: document.getElementById('intimacao-nome-andamento').value.trim(),
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
    if (!pode('alterar_intimacoes')) return;
    const item = intimacoes.find(atual => atual.id === id);
    if (!item) return;
    document.getElementById('intimacao-id').value = item.id;
    document.getElementById('intimacao-protocolo').value = item.protocolo;
    document.getElementById('intimacao-credor').value = item.credor;
    document.getElementById('intimacao-devedor').value = item.devedor;
    document.getElementById('intimacao-nome-andamento').value = item.nomeAndamento || 'Não informado';
    document.getElementById('intimacao-andamento').value = item.ultimoAndamento;
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
    const hoje = hojeLocal();
    intimacoesPendentes.add(id);
    intimacoes[indice] = {
        ...anterior,
        ultimaConferencia: hoje,
        historico: [...new Set([...(anterior.historico || []), hoje])],
        ...(novoAndamento ? {nomeAndamento: novoAndamento, ultimoAndamento: hoje} : {}),
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
    if (!confirm('Deseja excluir esta intimação?')) return;
    try {
        await requisicaoAeri(`/api/intimacoes/${id}`, {method:'DELETE'});
        intimacoes = intimacoes.filter(item => item.id !== id);
        renderizarIntimacoes();
    } catch (falha) {
        alert(falha.message);
    }
}

async function abrirPastaIntimacao(protocolo) {
    if (protocolo !== PROTOCOLO_PASTA_FUNCIONAL) return;
    const caminho = caminhoPastaIntimacao(protocolo);
    try {
        await navigator.clipboard?.writeText(caminho);
    } catch (falha) {
        console.warn('Não foi possível copiar o caminho da pasta.', falha);
    }
    try {
        const resposta = await fetch(`${ABRIDOR_LOCAL_INTIMACOES}/abrir?protocolo=${encodeURIComponent(protocolo)}`, {
            method: 'GET',
            cache: 'no-store',
        });
        if (resposta.ok) return;
    } catch (falha) {
        console.warn('Abridor local indisponível.', falha);
    }
    window.open(urlArquivoWindows(caminho), '_blank', 'noopener');
    alert(`Não consegui acionar o abridor local. O caminho foi copiado:\n\n${caminho}\n\nPara abrir direto pelo AERI, execute o arquivo iniciar_abridor_pastas_intimacoes.bat neste computador.`);
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
    const cabecalho = 'Protocolo;Credor;Devedor;Nome do Andamento;Data do Último Andamento;Última Conferência';
    const linhas = intimacoes.map(item => [item.protocolo,item.credor,item.devedor,item.nomeAndamento || 'Não informado',item.ultimoAndamento,item.ultimaConferencia || '']
        .map(valor => `"${String(valor).replace(/"/g,'""')}"`).join(';'));
    baixarArquivo('\uFEFF' + [cabecalho,...linhas].join('\n'), 'text/csv;charset=utf-8', `intimacoes-aeri-${hojeLocal()}.csv`);
}

function tratarAcaoTabela(evento) {
    const botao = evento.target.closest('button[data-acao]');
    if (!botao) return;
    if (botao.dataset.acao === 'abrir-pasta') abrirPastaIntimacao(botao.dataset.protocolo);
    if (botao.dataset.acao === 'conferir') abrirCheckIntimacao(botao.dataset.id);
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
    document.getElementById('rotina-tbody').addEventListener('click', tratarAcaoTabela);
    document.getElementById('importar-intimacoes').addEventListener('change', importarIntimacoesCsv);
    document.getElementById('btn-exportar-intimacoes').addEventListener('click', exportarIntimacoesCsv);
    renderizarIntimacoes();
}
