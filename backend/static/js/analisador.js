import {escaparHtml} from './util.js';
import {requisicaoAeri} from './api.js';

const ICONE_PROCESSAR = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4v7"/><path d="m4 4 7 7"/><path d="M20 13v7h-7"/><path d="m20 20-7-7"/></svg>Buscar e processar';
const ICONE_COPIAR = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>Copiar';
const ICONE_APRENDER = '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"/></svg>';

function resumo(ato, todosAtos) {
    if (ato.status === 'CANCELADO') {
        const autor = ato.cancelado_por || 'outro ato';
        if (ato.categoria === 'ÔNUS') return `Gravame cancelado (pela ${autor})`;
        if (ato.categoria === 'RESTRIÇÃO') return `Restrição cancelada (pela ${autor})`;
        return `Ato cancelado (pela ${autor})`;
    }
    if (ato.categoria === 'CANCELAMENTO') {
        if (ato.cancela_atos?.length) {
            return `Cancelamento processado (Cancelou ${ato.cancela_atos.join(', ')})`;
        }
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

function detalheOnus(ato) {
    if (ato.categoria !== 'ÔNUS' || !ato.tipo_onus) return '';
    const grau = ato.grau_onus ? ` - ${ato.grau_onus}` : '';
    return `<div class="status-ato">Tipo: <strong>${escaparHtml(ato.tipo_onus + grau)}</strong></div>`;
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
            ${detalheOnus(ato)}
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

function renderizarGrupoImovel(titulo, itens) {
    if (!itens?.length) return '';
    return `
        <section class="imovel-grupo">
            <h3>${escaparHtml(titulo)}</h3>
            <div class="imovel-lista">
                ${itens.map(item => `
                    <div class="imovel-linha ${item.rotulo === 'Descrição registral' ? 'imovel-linha-ampla' : ''} ${item.ausente ? 'imovel-linha-ausente' : ''}">
                        <span>${escaparHtml(item.rotulo)}</span>
                        <strong>${escaparHtml(item.valor)}</strong>
                        ${item.origem && item.origem !== 'Cabeçalho' ? `<small>${escaparHtml(item.origem)}</small>` : ''}
                    </div>`).join('')}
            </div>
        </section>`;
}

const NAO_CONSTA = 'NÃO CONSTA';

function normalizarRotulo(valor) {
    return String(valor || '')
        .normalize('NFD')
        .replace(/[\u0300-\u036f]/g, '')
        .trim()
        .toUpperCase();
}

function completarCamposImovel(itens, campos) {
    const lista = Array.isArray(itens) ? itens : [];
    const usados = new Set();
    const completos = [];

    campos.forEach(campo => {
        const encontrados = [];
        lista.forEach((item, indice) => {
            if (campo.corresponde(item)) {
                encontrados.push({...item, rotulo: campo.rotulo});
                usados.add(indice);
            }
        });
        if (encontrados.length) completos.push(...encontrados);
        else completos.push({rotulo: campo.rotulo, valor: NAO_CONSTA, ausente: true});
    });

    lista.forEach((item, indice) => {
        if (!usados.has(indice)) completos.push(item);
    });
    return completos;
}

function campoPorRotulos(rotulo, ...rotulos) {
    const aceitos = new Set(rotulos.map(normalizarRotulo));
    return {
        rotulo,
        corresponde: item => aceitos.has(normalizarRotulo(item.rotulo)),
    };
}

function grupoGenerico(itens, rotulo) {
    return Array.isArray(itens) && itens.length
        ? itens
        : [{rotulo, valor: NAO_CONSTA, ausente: true}];
}

function gruposCompletosImovel(imovel) {
    const tipo = normalizarRotulo(imovel.tipo);
    const rural = tipo === 'RURAL';
    const urbano = tipo === 'URBANO';
    const camposIdentificacao = [campoPorRotulos('Matrícula', 'Matrícula')];
    if (!urbano) camposIdentificacao.push(
        campoPorRotulos('Nome / denominação', 'Nome', 'Denominação'),
    );
    if (!rural) camposIdentificacao.push(
        campoPorRotulos('Lote', 'Lote'),
        campoPorRotulos('Quadra', 'Quadra'),
        campoPorRotulos('Rua', 'Rua'),
        campoPorRotulos('Número', 'Número'),
        campoPorRotulos('Setor', 'Setor'),
    );
    const identificacaoPermitida = (Array.isArray(imovel.identificacao) ? imovel.identificacao : [])
        .filter(item => {
            const rotulo = normalizarRotulo(item.rotulo);
            if (rural) return ['MATRICULA', 'NOME', 'DENOMINACAO'].includes(rotulo);
            if (urbano) return !['NOME', 'DENOMINACAO'].includes(rotulo);
            return true;
        });
    const identificacao = completarCamposImovel(identificacaoPermitida, camposIdentificacao);
    const confrontacoes = completarCamposImovel(imovel.confrontacoes, [
        campoPorRotulos('Frente', 'Frente'),
        campoPorRotulos('Lado direito', 'Lado direito'),
        campoPorRotulos('Lado esquerdo', 'Lado esquerdo'),
        campoPorRotulos('Fundos', 'Fundos'),
    ]);
    const camposAreas = [
        campoPorRotulos('Área registral', 'Área'),
        campoPorRotulos('Área construída', 'Área construída'),
    ];
    if (!urbano) camposAreas.push(
        campoPorRotulos('Área no CCIR', 'Área no CCIR'),
        campoPorRotulos('Área declarada no CAR', 'Área declarada no CAR'),
    );
    const areasPermitidas = (Array.isArray(imovel.areas) ? imovel.areas : [])
        .filter(item => !urbano || ![
            'AREA NO CCIR',
            'AREA DECLARADA NO CAR',
        ].includes(normalizarRotulo(item.rotulo)));
    const areas = completarCamposImovel(areasPermitidas, camposAreas);

    const cadastroMunicipal = {
        rotulo: 'Cadastro municipal / CCI',
        corresponde: item => ['CADASTRO MUNICIPAL', 'CCI', 'CADASTRO MUNICIPAL / CCI']
            .includes(normalizarRotulo(item.rotulo)) || /\bCCI\b/i.test(String(item.valor || '')),
    };
    const camposCadastros = [];
    if (!rural) camposCadastros.push(cadastroMunicipal, campoPorRotulos('CEP', 'CEP'));
    if (!urbano) camposCadastros.push(
        campoPorRotulos('CCIR / código rural', 'CCIR / código rural'),
        campoPorRotulos('INCRA', 'INCRA'),
        campoPorRotulos('CAR', 'CAR'),
        campoPorRotulos('Coordenadas do CAR', 'Coordenadas do CAR'),
    );
    const rotulosRurais = new Set([
        'CCIR / CODIGO RURAL',
        'INCRA',
        'CAR',
        'COORDENADAS DO CAR',
    ]);
    const cadastrosPermitidos = (Array.isArray(imovel.cadastros) ? imovel.cadastros : [])
        .filter(item => !urbano || !rotulosRurais.has(normalizarRotulo(item.rotulo)))
        .map(item => cadastroMunicipal.corresponde(item)
            ? {...item, rotulo: cadastroMunicipal.rotulo}
            : item);
    const cadastros = completarCamposImovel(cadastrosPermitidos, camposCadastros);
    const restricoes = grupoGenerico(imovel.restricoes, 'Restrições e dados ambientais');
    const divergencias = grupoGenerico(imovel.divergencias, 'Divergências');
    return {identificacao, confrontacoes, areas, cadastros, restricoes, divergencias};
}

export function renderizarImovel(imovel) {
    if (!imovel) {
        imovel = {};
    }
    const situacao = imovel.situacao || {};
    const grupos = gruposCompletosImovel(imovel);
    const matriculasSucessoras = Array.isArray(situacao.matriculas_sucessoras)
        ? situacao.matriculas_sucessoras
        : (situacao.matricula_sucessora ? [situacao.matricula_sucessora] : []);
    const situacaoStatus = situacao.status || NAO_CONSTA;
    const situacaoOrigem = situacao.origem || NAO_CONSTA;
    const sucessorasValor = matriculasSucessoras.length ? matriculasSucessoras.join(', ') : NAO_CONSTA;
    const alertas = (imovel.alertas || []).map(alerta => `
        <div class="imovel-alerta">
            <div><strong>${escaparHtml(alerta.tipo)}</strong><span>${escaparHtml(alerta.mensagem)}</span></div>
            <small>${escaparHtml(alerta.origem)}</small>
        </div>`).join('');

    return `
        <div class="imovel-painel">
            <div class="imovel-resumo">
                <div class="imovel-resumo-item"><span>Situação</span><strong class="imovel-situacao ${situacaoStatus !== 'ATIVA' ? 'encerrada' : ''}">${escaparHtml(situacaoStatus)}</strong><small>${escaparHtml(situacaoOrigem)}</small></div>
                <div class="imovel-resumo-item"><span>Tipo</span><strong>${escaparHtml(imovel.tipo || NAO_CONSTA)}</strong></div>
                <div class="imovel-resumo-item"><span>Matrículas sucessoras</span><strong>${escaparHtml(sucessorasValor)}</strong></div>
            </div>
            ${alertas ? `<div class="imovel-alertas">${alertas}</div>` : ''}
            ${renderizarGrupoImovel('Identificação', grupos.identificacao)}
            ${renderizarGrupoImovel('Confrontações', grupos.confrontacoes)}
            ${renderizarGrupoImovel('Áreas', grupos.areas)}
            ${renderizarGrupoImovel('Cadastros', grupos.cadastros)}
            ${renderizarGrupoImovel('Restrições e dados ambientais', grupos.restricoes)}
            ${renderizarGrupoImovel('Divergências', grupos.divergencias)}
        </div>`;
}

function renderizarAprendizado() {
    return `
        <div class="aprendizado-painel">
            <div class="aprendizado-cabecalho">
                <div>
                    <span class="eyebrow">APRENDIZADO</span>
                    <h3>Correção de regra</h3>
                </div>
                <span class="aprendizado-status">Revisão obrigatória</span>
            </div>
            <div class="aprendizado-form">
                <label><span>Termo encontrado</span><input id="aprendizado-expressao" maxlength="120" placeholder="Ex.: afetação patrimonial"></label>
                <label><span>Classificação correta</span><select id="aprendizado-categoria">
                    <option value="ÔNUS">Ônus</option>
                    <option value="RESTRIÇÃO">Restrição</option>
                    <option value="PUBLICIDADE">Publicidade</option>
                    <option value="CANCELAMENTO">Cancelamento</option>
                    <option value="IGNORAR">Ignorar</option>
                </select></label>
                <label><span>Tipo de ônus</span><input id="aprendizado-tipo-onus" maxlength="80" placeholder="Ex.: hipoteca, usufruto, alienação fiduciária"></label>
                <label class="aprendizado-full"><span>Justificativa</span><textarea id="aprendizado-justificativa" maxlength="500"></textarea></label>
                <div class="aprendizado-acoes">
                    <span id="aprendizado-retorno" aria-live="polite"></span>
                    <button type="button" class="btn btn-primary" data-acao="enviar-aprendizado">${ICONE_APRENDER}Enviar sugestão</button>
                </div>
            </div>
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
                <div><span class="resultado-matricula">MATRÍCULA ${escaparHtml(dados.numero_matricula || '')}</span><h2>${escaparHtml(dados.resultado)}</h2></div><div class="sub-status">${escaparHtml(dados.publicidade)}</div>
            </div>
            <div class="tabs-container">
                <button class="tab-btn active" data-tab="tab-atos">Atos Registrais (${dados.atos.length})</button>
                <button class="tab-btn" data-tab="tab-imovel">Imóvel</button>
                <button class="tab-btn" data-tab="tab-prop">Proprietários (${proprietarios.length})</button>
            </div>
            <div id="tab-atos" class="tab-content active"><div class="cards">${renderizarAtos(dados)}</div></div>
            <div id="tab-imovel" class="tab-content">${renderizarImovel(dados.imovel)}</div>
            <div id="tab-prop" class="tab-content" style="padding:16px">${renderizarProprietarios(proprietarios)}</div>
        </div>`;
    const modal = document.getElementById('modal-resultado');
    modal.classList.add('aberta');
    modal.setAttribute('aria-hidden', 'false');
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

async function enviarSugestaoAprendizado(botao) {
    const painel = botao.closest('.aprendizado-painel');
    const retorno = painel.querySelector('#aprendizado-retorno');
    const dados = {
        expressao: painel.querySelector('#aprendizado-expressao').value.trim(),
        categoria: painel.querySelector('#aprendizado-categoria').value,
        tipo_onus: painel.querySelector('#aprendizado-tipo-onus').value.trim(),
        justificativa: painel.querySelector('#aprendizado-justificativa').value.trim(),
    };
    botao.disabled = true;
    retorno.textContent = 'Registrando...';
    try {
        const salvo = await requisicaoAeri('/analisar/aprendizado/sugestoes', {
            method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(dados),
        });
        retorno.textContent = salvo.status === 'APROVADA'
            ? 'Regra já aprovada; ocorrência registrada.'
            : `Sugestão registrada (${salvo.votos} ocorrência${salvo.votos === 1 ? '' : 's'}).`;
        painel.querySelector('#aprendizado-justificativa').value = '';
    } catch (erro) {
        retorno.textContent = erro.message;
    } finally {
        botao.disabled = false;
    }
}

async function tratarAcaoResultado(evento) {
    const botao = evento.target.closest('button');
    if (!botao) return;
    if (botao.dataset.tab) trocarAba(botao.dataset.tab);
    if (botao.dataset.acao === 'copiar-cadeia') copiarCadeia(botao);
    if (botao.dataset.acao === 'enviar-aprendizado') await enviarSugestaoAprendizado(botao);
}

function fecharModal() {
    const modal = document.getElementById('modal-resultado');
    modal.classList.remove('aberta');
    modal.setAttribute('aria-hidden', 'true');
}

async function analisar(evento) {
    evento?.preventDefault();
    const campo = document.getElementById('numero-matricula');
    const erroBusca = document.getElementById('erro-busca-matricula');
    const numeroMatricula = campo.value.trim();
    if (!numeroMatricula || !campo.reportValidity()) return;
    const botao = document.getElementById('btn-analisar');
    botao.textContent = 'Buscando na Tri7...';
    botao.disabled = true;
    botao.style.opacity = '0.7';
    erroBusca.textContent = '';
    try {
        renderizarResultado(await requisicaoAeri('/analisar/matricula', {
            method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({numero_matricula: numeroMatricula}),
        }));
    } catch (erro) {
        erroBusca.textContent = erro.message;
        campo.focus();
    } finally {
        botao.innerHTML = ICONE_PROCESSAR;
        botao.disabled = false;
        botao.style.opacity = '1';
    }
}

export function iniciarAnalisador() {
    document.getElementById('form-busca-matricula').addEventListener('submit', analisar);
    document.getElementById('btn-limpar').addEventListener('click', () => {
        document.getElementById('numero-matricula').value = '';
        document.getElementById('erro-busca-matricula').textContent = '';
        fecharModal();
        document.getElementById('numero-matricula').focus();
    });
    const modal = document.getElementById('modal-resultado');
    modal.setAttribute('aria-hidden', 'true');
    modal.addEventListener('click', evento => {
        if (evento.target.closest('#btn-fechar-resultado') || evento.target === modal) {
            evento.preventDefault();
            evento.stopPropagation();
            fecharModal();
        }
    });
    document.getElementById('modal-conteudo').addEventListener('click', tratarAcaoResultado);
    document.addEventListener('keydown', evento => { if (evento.key === 'Escape') fecharModal(); });
}
