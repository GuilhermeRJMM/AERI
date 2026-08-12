import {requisicaoAeri} from './api.js';
import {mostrarPagina} from './navegacao.js';
import {escaparHtml} from './util.js';

let estadoAtual = null;
let indexando = false;
let revisando = false;

function formatarNumero(valor) {
    return new Intl.NumberFormat('pt-BR').format(Number(valor || 0));
}

function registrarEvento(mensagem, tipo = 'info') {
    const lista = document.getElementById('buscas-log-lista');
    if (!lista) return;
    const item = document.createElement('li');
    item.dataset.tipo = tipo;
    const horario = new Intl.DateTimeFormat('pt-BR', {timeStyle:'medium'}).format(new Date());
    item.textContent = `${horario} - ${mensagem}`;
    lista.prepend(item);
    while (lista.children.length > 12) lista.lastElementChild?.remove();
}

function atualizarStatus(estado) {
    estadoAtual = estado;
    const progresso = Math.min(100, Number(estado.progressoInicial || 0));
    document.getElementById('buscas-total-indexadas').textContent = formatarNumero(estado.totalIndexadas);
    document.getElementById('buscas-total-ativas').textContent = formatarNumero(estado.matriculasAtivas);
    document.getElementById('buscas-total-encerradas').textContent = formatarNumero(estado.matriculasEncerradas);
    document.getElementById('buscas-total-proprietarios').textContent = formatarNumero(estado.proprietariosAtuais);
    document.getElementById('buscas-auditoria-total').textContent = formatarNumero(estado.auditoriaTotal);
    document.getElementById('buscas-auditoria-validadas').textContent = formatarNumero(estado.auditoriaValidadas);
    document.getElementById('buscas-auditoria-revisar').textContent = formatarNumero(estado.auditoriaRevisar);
    document.getElementById('buscas-auditoria-criticas').textContent = formatarNumero(estado.auditoriaCriticas);
    document.getElementById('buscas-progresso-texto').textContent = `${progresso.toLocaleString('pt-BR')}%`;
    document.getElementById('buscas-progresso-barra').style.width = `${progresso}%`;
    document.getElementById('buscas-proximo').textContent = estado.cargaInicialConcluida
        ? 'Indexação inicial concluída'
        : `Próxima matrícula: ${formatarNumero(estado.proximoInicial)} de ${formatarNumero(estado.limiteInicial)}`;
    document.getElementById('buscas-limite').value = estado.limiteInicial;
    document.getElementById('buscas-atualizado').textContent = estado.ultimaSincronizacao
        ? `Última atualização: ${new Intl.DateTimeFormat('pt-BR', {dateStyle:'short', timeStyle:'short'}).format(new Date(estado.ultimaSincronizacao))}`
        : 'A indexação ainda não foi iniciada.';
    const admin = ['ADMIN', 'SUBSTITUTO'].includes(document.body.dataset.perfil);
    const podeAuditar = admin || Boolean(window.aeriPermissoes?.revisar_auditoria);
    const erros = Number(estado.errosPendentes || 0);
    document.getElementById('btn-buscas-erros').hidden = !admin || !erros;
    document.getElementById('btn-buscas-reprocessar').hidden = !admin || !erros;
    if (!erros) document.getElementById('buscas-erros-painel').hidden = true;
    const pendencias = Number(estado.auditoriaRevisar || 0);
    document.getElementById('btn-buscas-pendencias').hidden = !podeAuditar || !pendencias;
    if (!pendencias) {
        document.getElementById('buscas-pendencias-painel').hidden = true;
        document.getElementById('btn-buscas-pendencias').textContent = 'Ver pendências';
    }
}

function atualizarBotao() {
    const botao = document.getElementById('btn-buscas-indexar');
    botao.textContent = indexando ? 'Pausar indexação' : 'Iniciar indexação';
    botao.classList.toggle('pausar', indexando);
}

export async function carregarBuscas() {
    const autorizado = ['ADMIN', 'SUBSTITUTO'].includes(document.body.dataset.perfil)
        || Boolean(window.aeriPermissoes?.processar_matricula);
    if (!autorizado) return;
    const admin = ['ADMIN', 'SUBSTITUTO'].includes(document.body.dataset.perfil);
    const podeAuditar = admin || Boolean(window.aeriPermissoes?.revisar_auditoria);
    document.getElementById('buscas-sincronizacao').hidden = !podeAuditar;
    document.querySelectorAll('[data-buscas-admin]').forEach(elemento => { elemento.hidden = !admin; });
    document.querySelectorAll('[data-buscas-revisao]').forEach(elemento => { elemento.hidden = !podeAuditar; });
    try {
        atualizarStatus(await requisicaoAeri('/api/buscas/status'));
    } catch (erro) {
        document.getElementById('buscas-atualizado').textContent = erro.message;
    }
}

export function limparBuscas() {
    indexando = false;
    revisando = false;
    estadoAtual = null;
    atualizarBotao();
    document.getElementById('buscas-pendencias-painel').hidden = true;
    document.getElementById('btn-buscas-pendencias').textContent = 'Ver pendências';
    document.getElementById('buscas-resultados').innerHTML = '<tr><td colspan="8" class="rotina-vazio">Entre novamente para pesquisar.</td></tr>';
}

function atualizarBotaoRevisao() {
    const botao = document.getElementById('btn-buscas-revisar-indice');
    botao.textContent = revisando ? 'Pausar revisão' : 'Revisar índice';
    botao.classList.toggle('pausar', revisando);
}

function renderizarResultados(dados) {
    const itens = dados.itens || [];
    document.getElementById('buscas-total-resultados').textContent = `${itens.length} ${itens.length === 1 ? 'resultado' : 'resultados'}`;
    document.getElementById('buscas-resultados').innerHTML = itens.map(item => {
        const correspondencia = item.correspondencia === 'DOCUMENTO_EXATO' ? 'CPF/CNPJ exato'
            : item.correspondencia === 'NOME_EXATO' ? 'Nome exato' : 'Nome parcial';
        const situacao = String(item.situacao || 'REVISAR').toUpperCase();
        return `<tr>
            <td data-label="Matrícula"><strong class="buscas-matricula">${formatarNumero(item.matricula)}</strong><small class="buscas-situacao" data-situacao="${escaparHtml(situacao)}">${escaparHtml(situacao)}</small></td>
            <td data-label="Proprietário"><strong>${escaparHtml(item.nome)}</strong><small>Confiança ${escaparHtml(item.confianca.toLowerCase())}</small></td>
            <td data-label="Documento">${escaparHtml(item.tipoDocumento || '')} ${escaparHtml(item.documento || 'Não informado')}</td>
            <td data-label="Proporção"><span class="buscas-proporcao">${escaparHtml(item.proporcao)}</span></td>
            <td data-label="Origem">${escaparHtml(item.origem)}</td>
            <td data-label="Correspondência"><span class="buscas-correspondencia" data-tipo="${escaparHtml(item.correspondencia)}">${correspondencia}</span></td>
            <td data-label="Atualização">${new Intl.DateTimeFormat('pt-BR').format(new Date(item.consultadoEm))}</td>
            <td data-label="Ação"><button type="button" class="rotina-btn-secondary buscas-analisar" data-matricula="${item.matricula}">Analisar</button></td>
        </tr>`;
    }).join('') || '<tr><td colspan="8" class="rotina-vazio">Nenhuma matrícula foi encontrada para essa pesquisa.</td></tr>';
}

async function pesquisar(evento) {
    evento.preventDefault();
    const botao = document.getElementById('btn-buscas-pesquisar');
    const termo = document.getElementById('buscas-termo').value.trim();
    botao.disabled = true;
    document.getElementById('buscas-resultados').innerHTML = '<tr><td colspan="8" class="rotina-vazio">Pesquisando titulares no índice registral…</td></tr>';
    try {
        renderizarResultados(await requisicaoAeri(`/api/buscas?termo=${encodeURIComponent(termo)}`));
    } catch (erro) {
        document.getElementById('buscas-resultados').innerHTML = `<tr><td colspan="8" class="rotina-vazio">${escaparHtml(erro.message)}</td></tr>`;
    } finally {
        botao.disabled = false;
    }
}

async function executarIndexacaoInicial() {
    indexando = true;
    atualizarBotao();
    const limite = Number(document.getElementById('buscas-limite').value || 39850);
    registrarEvento(`Indexação iniciada até a matrícula ${formatarNumero(limite)}.`);
    let falhasTemporarias = 0;
    while (indexando) {
        try {
            const resultado = await requisicaoAeri('/api/buscas/sincronizar', {
                method:'POST', headers:{'Content-Type':'application/json'},
                body:JSON.stringify({modo:'INICIAL', tamanho:20, limite}),
            });
            falhasTemporarias = 0;
            atualizarStatus(resultado.estado);
            const mensagem = resultado.falha || `Lote: ${resultado.processados} consultadas · ${resultado.ativas} ativas · ${resultado.encerradas} encerradas · ${resultado.auditoriasValidadas} validadas · ${resultado.auditoriasRevisar} para conferir · ${resultado.falhas} falha(s)`;
            document.getElementById('buscas-status-operacao').textContent = mensagem;
            registrarEvento(mensagem, resultado.falha ? 'erro' : 'sucesso');
            if (resultado.falha || resultado.estado.cargaInicialConcluida || resultado.processados === 0) {
                if (resultado.estado.cargaInicialConcluida) registrarEvento('Carga inicial concluída.', 'sucesso');
                break;
            }
            await new Promise(resolve => window.setTimeout(resolve, 180));
        } catch (erro) {
            const mensagem = erro.message || 'Falha temporária na indexação.';
            if (/sess[aã]o expirou|permiss[aã]o|troque sua senha/i.test(mensagem)) {
                document.getElementById('buscas-status-operacao').textContent = mensagem;
                registrarEvento(`Indexação interrompida: ${mensagem}`, 'erro');
                break;
            }
            falhasTemporarias += 1;
            const tentativa = `${mensagem} Nova tentativa (${falhasTemporarias}/5).`;
            document.getElementById('buscas-status-operacao').textContent = tentativa;
            registrarEvento(tentativa, 'alerta');
            if (falhasTemporarias >= 5) {
                registrarEvento('Indexação pausada após cinco falhas consecutivas.', 'erro');
                break;
            }
            await new Promise(resolve => window.setTimeout(resolve, 2000 * falhasTemporarias));
        }
    }
    indexando = false;
    atualizarBotao();
}

function alternarIndexacao() {
    if (revisando) {
        document.getElementById('buscas-status-operacao').textContent = 'Pause a revisão antes de iniciar a carga inicial.';
        return;
    }
    if (indexando) {
        indexando = false;
        atualizarBotao();
        document.getElementById('buscas-status-operacao').textContent = 'Pausa solicitada. O lote atual será concluído.';
        registrarEvento('Pausa manual solicitada.', 'alerta');
        return;
    }
    executarIndexacaoInicial();
}

async function executarRevisao() {
    revisando = true;
    atualizarBotaoRevisao();
    const totalEsperado = Number(estadoAtual?.matriculasComTexto || 0);
    let totalProcessado = 0;
    let falhasTemporarias = 0;
    registrarEvento(`Revisão iniciada para ${formatarNumero(totalEsperado)} matrícula(s) com texto.`);
    while (revisando && totalProcessado < totalEsperado) {
        try {
            const resultado = await requisicaoAeri('/api/buscas/sincronizar', {
                method:'POST', headers:{'Content-Type':'application/json'},
                body:JSON.stringify({modo:'REVISAO', tamanho:20}),
            });
            falhasTemporarias = 0;
            totalProcessado += resultado.processados;
            atualizarStatus(resultado.estado);
            const mensagem = `Revisão: ${formatarNumero(totalProcessado)} de ${formatarNumero(totalEsperado)} · ${resultado.alteradas} alteração(ões) · ${resultado.falhas} falha(s).`;
            document.getElementById('buscas-status-operacao').textContent = mensagem;
            registrarEvento(mensagem, resultado.falhas ? 'alerta' : 'sucesso');
            if (resultado.falha || resultado.processados === 0) break;
            await new Promise(resolve => window.setTimeout(resolve, 180));
        } catch (erro) {
            falhasTemporarias += 1;
            const mensagem = `${erro.message || 'Falha temporária na revisão.'} Nova tentativa (${falhasTemporarias}/5).`;
            registrarEvento(mensagem, 'alerta');
            if (falhasTemporarias >= 5) break;
            await new Promise(resolve => window.setTimeout(resolve, 2000 * falhasTemporarias));
        }
    }
    revisando = false;
    atualizarBotaoRevisao();
    if (totalProcessado >= totalEsperado && totalEsperado > 0) registrarEvento('Revisão completa do índice concluída.', 'sucesso');
}

function alternarRevisao() {
    if (indexando) {
        document.getElementById('buscas-status-operacao').textContent = 'Pause a indexação antes de iniciar a revisão.';
        return;
    }
    if (revisando) {
        revisando = false;
        atualizarBotaoRevisao();
        registrarEvento('Pausa da revisão solicitada.', 'alerta');
        return;
    }
    executarRevisao();
}

async function atualizarNovas() {
    const botao = document.getElementById('btn-buscas-novas');
    botao.disabled = true;
    try {
        if (Number(estadoAtual?.errosPendentes || 0)) {
            const erros = await requisicaoAeri('/api/buscas/sincronizar', {
                method:'POST', headers:{'Content-Type':'application/json'},
                body:JSON.stringify({modo:'ERROS', tamanho:30}),
            });
            atualizarStatus(erros.estado);
            registrarEvento(`${erros.processados} falha(s) reprocessada(s).`, erros.falhas ? 'alerta' : 'sucesso');
        }
        const resultado = await requisicaoAeri('/api/buscas/sincronizar', {
            method:'POST', headers:{'Content-Type':'application/json'},
            body:JSON.stringify({modo:'NOVOS', tamanho:30}),
        });
        atualizarStatus(resultado.estado);
        const mensagem = `${resultado.encontradas} matrícula(s) nova(s) localizada(s); ${resultado.ativas} ativa(s).`;
        document.getElementById('buscas-status-operacao').textContent = mensagem;
        registrarEvento(mensagem, 'sucesso');
    } catch (erro) {
        document.getElementById('buscas-status-operacao').textContent = erro.message;
        registrarEvento(erro.message, 'erro');
    } finally {
        botao.disabled = false;
    }
}

async function reprocessarFalhas() {
    const botao = document.getElementById('btn-buscas-reprocessar');
    botao.disabled = true;
    let total = 0;
    try {
        for (let lote = 0; lote < 20 && Number(estadoAtual?.errosPendentes || 0) > 0; lote += 1) {
            const resultado = await requisicaoAeri('/api/buscas/sincronizar', {
                method:'POST', headers:{'Content-Type':'application/json'},
                body:JSON.stringify({modo:'ERROS', tamanho:30}),
            });
            atualizarStatus(resultado.estado);
            total += resultado.processados;
            if (resultado.processados === 0 || resultado.falha) break;
        }
        const mensagem = `${total} matrícula(s) com falha reprocessada(s); ${estadoAtual?.errosPendentes || 0} pendente(s).`;
        document.getElementById('buscas-status-operacao').textContent = mensagem;
        registrarEvento(mensagem, Number(estadoAtual?.errosPendentes || 0) ? 'alerta' : 'sucesso');
    } catch (erro) {
        document.getElementById('buscas-status-operacao').textContent = erro.message;
        registrarEvento(erro.message, 'erro');
    } finally {
        botao.disabled = false;
    }
}

async function revisarNumero() {
    const numero = Number(document.getElementById('buscas-numero-revisar').value);
    if (!Number.isInteger(numero) || numero <= 0) {
        document.getElementById('buscas-status-operacao').textContent = 'Informe um número de matrícula válido.';
        return;
    }
    const botao = document.getElementById('btn-buscas-revisar');
    botao.disabled = true;
    try {
        const resultado = await requisicaoAeri(`/api/buscas/${numero}/revisar`, {method:'POST'});
        atualizarStatus(resultado.estado);
        const mensagem = `Matrícula ${formatarNumero(numero)} revisada: ${resultado.situacao.toLowerCase()}${resultado.alterado ? ', com alteração detectada' : ', sem alteração'}.`;
        document.getElementById('buscas-status-operacao').textContent = mensagem;
        registrarEvento(mensagem, 'sucesso');
        document.getElementById('buscas-numero-revisar').value = '';
    } catch (erro) {
        document.getElementById('buscas-status-operacao').textContent = erro.message;
        registrarEvento(erro.message, 'erro');
    } finally {
        botao.disabled = false;
    }
}

async function alternarErros() {
    const painel = document.getElementById('buscas-erros-painel');
    if (!painel.hidden) {
        painel.hidden = true;
        return;
    }
    const botao = document.getElementById('btn-buscas-erros');
    botao.disabled = true;
    try {
        const erros = await requisicaoAeri('/api/buscas/erros');
        document.getElementById('buscas-erros-tbody').innerHTML = erros.map(item => `<tr>
            <td>${formatarNumero(item.numero)}</td><td>${escaparHtml(item.modo)}</td><td>${item.tentativas}</td>
            <td>${new Intl.DateTimeFormat('pt-BR', {dateStyle:'short', timeStyle:'short'}).format(new Date(item.ultimaTentativaEm))}</td>
            <td>${escaparHtml(item.erro)}</td>
        </tr>`).join('') || '<tr><td colspan="5" class="rotina-vazio">Nenhuma falha pendente.</td></tr>';
        painel.hidden = false;
    } catch (erro) {
        registrarEvento(erro.message, 'erro');
    } finally {
        botao.disabled = false;
    }
}

function rotuloRevisaoComplementar(status) {
    const rotulos = {
        CONCLUIDA: 'Concluída', PENDENTE: 'Pendente', PROCESSANDO: 'Em processamento',
        FALHA: 'Repetir', DESATIVADA: 'Conferência manual', NAO_NECESSARIA: 'Não necessária',
    };
    return rotulos[status] || 'Conferência manual';
}

async function alternarPendencias() {
    const painel = document.getElementById('buscas-pendencias-painel');
    const botao = document.getElementById('btn-buscas-pendencias');
    if (!painel.hidden) {
        painel.hidden = true;
        botao.textContent = 'Ver pendências';
        return;
    }
    painel.hidden = false;
    botao.textContent = 'Ocultar pendências';
    botao.disabled = true;
    document.getElementById('buscas-pendencias-tbody').innerHTML = '<tr><td colspan="8" class="rotina-vazio">Carregando pendências…</td></tr>';
    painel.scrollIntoView({behavior:'smooth', block:'nearest'});
    try {
        const itens = await requisicaoAeri('/api/buscas/auditoria/pendencias?limite=200');
        document.getElementById('buscas-pendencias-tbody').innerHTML = itens.map(item => {
            const alertas = (item.alertas || []).join(', ') || 'Sem alerta detalhado';
            const conclusao = item.diagnosticoComplementar?.conclusao;
            const revisao = conclusao ? `${rotuloRevisaoComplementar(item.analiseComplementar)} · ${conclusao}`
                : rotuloRevisaoComplementar(item.analiseComplementar);
            return `<tr>
                <td><strong>${formatarNumero(item.matricula)}</strong></td>
                <td><span class="buscas-prioridade" data-prioridade="${escaparHtml(item.prioridade)}">${escaparHtml(item.prioridade)}</span></td>
                <td>${escaparHtml(item.confiancaOnus)}</td><td>${escaparHtml(item.confiancaCadeia)}</td>
                <td>${escaparHtml(item.confiancaImovel)}</td><td>${escaparHtml(alertas)}</td>
                <td>${escaparHtml(revisao)}</td>
                <td><button type="button" class="rotina-btn-secondary buscas-analisar" data-matricula="${item.matricula}">Analisar</button></td>
            </tr>`;
        }).join('') || '<tr><td colspan="8" class="rotina-vazio">Nenhuma pendência registral.</td></tr>';
    } catch (erro) {
        registrarEvento(erro.message, 'erro');
        document.getElementById('buscas-pendencias-tbody').innerHTML = `<tr><td colspan="8" class="rotina-vazio">${escaparHtml(erro.message)}</td></tr>`;
    } finally {
        botao.disabled = false;
    }
}

function abrirAnalise(evento) {
    const botao = evento.target.closest('[data-matricula]');
    if (!botao) return;
    mostrarPagina('onus');
    const campo = document.getElementById('numero-matricula');
    campo.value = botao.dataset.matricula;
    campo.focus();
}

export function iniciarBuscas() {
    document.getElementById('form-buscas').addEventListener('submit', pesquisar);
    document.getElementById('btn-buscas-indexar').addEventListener('click', alternarIndexacao);
    document.getElementById('btn-buscas-novas').addEventListener('click', atualizarNovas);
    document.getElementById('btn-buscas-revisar-indice').addEventListener('click', alternarRevisao);
    document.getElementById('btn-buscas-reprocessar').addEventListener('click', reprocessarFalhas);
    document.getElementById('btn-buscas-revisar').addEventListener('click', revisarNumero);
    document.getElementById('btn-buscas-erros').addEventListener('click', alternarErros);
    document.getElementById('btn-buscas-pendencias').addEventListener('click', alternarPendencias);
    document.getElementById('buscas-resultados').addEventListener('click', abrirAnalise);
    document.getElementById('buscas-pendencias-tbody').addEventListener('click', abrirAnalise);
}
