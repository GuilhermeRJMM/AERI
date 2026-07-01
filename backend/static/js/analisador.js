import {escaparHtml} from './util.js';

const ICONE_PROCESSAR = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg>Processar Matrícula';
const ICONE_COPIAR = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>Copiar';

function resumo(ato, todosAtos) {
    if (ato.status === 'CANCELADO') {
        const autor = ato.cancelado_por || 'outro ato';
        if (ato.categoria === 'ÔNUS') return `Gravame cancelado (pela ${autor})`;
        if (ato.categoria === 'RESTRIÇÃO') return `Restrição cancelada (pela ${autor})`;
        return `Ato cancelado (pela ${autor})`;
    }
    if (ato.categoria === 'CANCELAMENTO') {
        const referencias = [...ato.descricao.matchAll(/\b(R|AV)[.\-]\s*0*(\d+)/gi)];
        for (const referencia of referencias) {
            const tipo = referencia[1].toUpperCase();
            const numero = referencia[2];
            const alvo = `${tipo}.${numero}`;
            const alvoInverso = `${tipo === 'R' ? 'AV' : 'R'}.${numero}`;
            const proprioCodigo = ato.codigo.replace(/\.0+/, '.');
            const alvoExiste = todosAtos.some(item => item.codigo.replace(/\.0+/, '.') === alvo || item.codigo === alvo);
            const inversoExiste = todosAtos.some(item => item.codigo.replace(/\.0+/, '.') === alvoInverso || item.codigo === alvoInverso);
            if (alvo !== proprioCodigo && alvo !== ato.codigo) {
                if (alvoExiste) return `Cancelamento processado (Cancelou o ${alvo})`;
                if (inversoExiste) return `Cancelamento processado (Cancelou a ${alvoInverso} por erro de digitação do cartório)`;
            }
        }
        return 'Cancelamento processado';
    }
    if (ato.categoria === 'ÔNUS') return 'Gravame ativo encontrado na matrícula';
    if (ato.categoria === 'RESTRIÇÃO') return 'Restrição que impacta emissão';
    if (ato.categoria === 'PUBLICIDADE') return 'Ato sem caráter obstativo';
    return 'Ato informativo/Sem impacto direto';
}

function classeCategoria(categoria) {
    return {'ÔNUS':'badge-red', 'RESTRIÇÃO':'badge-orange', 'PUBLICIDADE':'badge-blue', 'CANCELAMENTO':'badge-green'}[categoria] || 'badge-gray';
}

function genero(nome) {
    return nome.trim().split(/\s+/)[0].toLowerCase().endsWith('a') ? 'inscrita' : 'inscrito';
}

function tipoDocumento(documento) {
    return String(documento || '').replace(/\D/g, '').length === 14 ? 'CNPJ/MF' : 'CPF/MF';
}

function formatarProprietario(proprietario, indice) {
    return `${indice + 1})- ${proprietario.nome}, ${genero(proprietario.nome)} no ${tipoDocumento(proprietario.cpf)} sob o n.º ${proprietario.cpf}, a proporção de ${proprietario.proporcao};`;
}

function renderizarAtos(dados) {
    return dados.atos.map(ato => `
        <div class="card ${ato.status === 'CANCELADO' ? 'card-cancelado' : ''}">
            <div class="card-header">
                <div class="codigo">${escaparHtml(ato.codigo)}</div>
                <div class="badge ${classeCategoria(ato.categoria)}">${escaparHtml(ato.categoria)}</div>
            </div>
            <div class="texto">${escaparHtml(resumo(ato, dados.atos))}</div>
            <div class="status-ato">Status: <strong>${escaparHtml(ato.status)}</strong></div>
        </div>`).join('');
}

function renderizarProprietarios(proprietarios) {
    if (!proprietarios.length) {
        return '<div style="padding:32px;text-align:center;color:var(--text-muted);font-size:.95rem;background:rgba(0,0,0,.02);border-radius:8px">Nenhum proprietário identificado. Verifique se a matrícula contém atos de transmissão (compra e venda, doação, inventário etc.).</div>';
    }
    const cards = proprietarios.map((item, indice) => `
        <div class="card">
            <div class="card-header"><div class="codigo">${indice + 1})- ${escaparHtml(item.nome)}</div><div class="badge badge-blue">PROPRIETÁRIO</div></div>
            <div class="texto">${genero(item.nome) === 'inscrita' ? 'Inscrita' : 'Inscrito'} no ${tipoDocumento(item.cpf)} sob o n.º <strong>${escaparHtml(item.cpf)}</strong></div>
            <div class="status-ato">Proporção: <strong>${escaparHtml(item.proporcao)}</strong></div>
        </div>`).join('');
    const texto = proprietarios.map(formatarProprietario).join('\n');
    return `<div class="cards">${cards}</div>
        <div class="cadeia-texto-bloco" style="margin:16px 0 0">
            <div class="cadeia-texto-header"><span>Texto gerado</span><button class="btn-copiar" data-acao="copiar-cadeia" data-texto="${encodeURIComponent(texto)}">${ICONE_COPIAR}</button></div>
            <pre class="cadeia-texto-pre">${escaparHtml(texto)}</pre>
        </div>`;
}

function renderizarResultado(dados) {
    let cor = '#16a34a';
    let fundo = '#f0fdf4';
    if (dados.resultado === 'POSITIVA PARA ÔNUS') { cor = '#dc2626'; fundo = '#fef2f2'; }
    else if (dados.resultado === 'NEGATIVA, PORÉM COM PUBLICIDADE') { cor = '#0284c7'; fundo = '#f0f9ff'; }
    const proprietarios = dados.proprietarios_atuais || [];
    document.getElementById('modal-conteudo').innerHTML = `
        <div class="resultado fade-in">
            <div class="topo" style="border-left:5px solid ${cor};background-color:${fundo}">
                <h2>${escaparHtml(dados.resultado)}</h2><div class="sub-status">${escaparHtml(dados.publicidade)}</div>
            </div>
            <div class="tabs-container">
                <button class="tab-btn active" data-tab="tab-atos">Atos Registrais (${dados.atos.length})</button>
                <button class="tab-btn" data-tab="tab-prop">Proprietários (${proprietarios.length})</button>
            </div>
            <div id="tab-atos" class="tab-content active"><div class="cards">${renderizarAtos(dados)}</div></div>
            <div id="tab-prop" class="tab-content" style="padding:16px">${renderizarProprietarios(proprietarios)}</div>
        </div>`;
    document.getElementById('modal-resultado').classList.add('aberta');
}

function trocarAba(tabId) {
    document.querySelectorAll('.tab-btn').forEach(botao => botao.classList.toggle('active', botao.dataset.tab === tabId));
    document.querySelectorAll('.tab-content').forEach(conteudo => conteudo.classList.toggle('active', conteudo.id === tabId));
}

function copiarCadeia(botao) {
    navigator.clipboard.writeText(decodeURIComponent(botao.dataset.texto)).then(() => {
        botao.textContent = '✓ Copiado!';
        window.setTimeout(() => { botao.innerHTML = ICONE_COPIAR; }, 2000);
    });
}

function tratarAcaoResultado(evento) {
    const botao = evento.target.closest('button');
    if (!botao) return;
    if (botao.dataset.tab) trocarAba(botao.dataset.tab);
    if (botao.dataset.acao === 'copiar-cadeia') copiarCadeia(botao);
}

function fecharModal() {
    document.getElementById('modal-resultado').classList.remove('aberta');
}

async function analisar() {
    const texto = document.getElementById('texto').value;
    if (!texto.trim()) return;
    const botao = document.getElementById('btn-analisar');
    botao.textContent = 'Processando...';
    botao.style.opacity = '0.7';
    try {
        const resposta = await fetch('/analisar', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({texto})});
        if (!resposta.ok) throw new Error('Falha na análise');
        renderizarResultado(await resposta.json());
    } catch {
        alert('Erro ao processar a matrícula.');
    } finally {
        botao.innerHTML = ICONE_PROCESSAR;
        botao.style.opacity = '1';
    }
}

export function iniciarAnalisador() {
    document.getElementById('btn-analisar').addEventListener('click', analisar);
    document.getElementById('btn-limpar').addEventListener('click', () => {
        document.getElementById('texto').value = '';
        fecharModal();
    });
    document.getElementById('btn-fechar-resultado').addEventListener('click', fecharModal);
    document.getElementById('modal-resultado').addEventListener('click', evento => {
        if (evento.target.id === 'modal-resultado') fecharModal();
    });
    document.getElementById('modal-conteudo').addEventListener('click', tratarAcaoResultado);
    document.addEventListener('keydown', evento => { if (evento.key === 'Escape') fecharModal(); });
}
