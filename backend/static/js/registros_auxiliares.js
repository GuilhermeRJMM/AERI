import {requisicaoAeri} from './api.js?v=20260820-robustez-v1';
import {escaparHtml} from './util.js';

let sincronizando = false;
let revisando = false;
let estadoAtual = null;

function rotuloModalidade(valor) {
    return valor === 'ALIENAÇÃO' ? 'Alienação' : valor.charAt(0) + valor.slice(1).toLowerCase();
}

function formatarNumero(numero) {
    return new Intl.NumberFormat('pt-BR').format(Number(numero));
}

function atualizarStatus(estado) {
    estadoAtual = estado;
    const progresso = Math.min(100, Number(estado.progressoInicial || 0));
    document.getElementById('regaux-total-indexado').textContent = formatarNumero(estado.totalIndexados);
    document.getElementById('regaux-progresso-texto').textContent = `${progresso.toLocaleString('pt-BR')}%`;
    document.getElementById('regaux-progresso-barra').style.width = `${progresso}%`;
    document.getElementById('regaux-proximo').textContent = estado.cargaInicialConcluida
        ? 'Carga inicial concluída'
        : `Próximo: ${formatarNumero(estado.proximoInicial)} de ${formatarNumero(estado.limiteInicial)}`;
    const hashesPendentes = Number(estado.documentosPendentesReindexacao || 0);
    if (hashesPendentes) {
        document.getElementById('regaux-proximo').textContent += ` · ${formatarNumero(hashesPendentes)} documento(s) aguardando reindexação segura`;
    }
    document.getElementById('regaux-limite').value = estado.limiteInicial;
    document.getElementById('regaux-atualizado').textContent = estado.ultimaSincronizacao
        ? `Última atualização: ${new Intl.DateTimeFormat('pt-BR', {dateStyle:'short', timeStyle:'short'}).format(new Date(estado.ultimaSincronizacao))}`
        : 'A sincronização ainda não foi iniciada.';
    const pendencias = Number(estado.errosPendentes || 0);
    if (pendencias) {
        document.getElementById('regaux-lote-status').textContent = `${formatarNumero(pendencias)} registro(s) com falha aguardando nova tentativa.`;
    }
    document.getElementById('btn-regaux-ver-erros').hidden = !pendencias;
    if (!pendencias) {
        document.getElementById('regaux-erros').hidden = true;
    }
}

function formatarMoeda(valor) {
    return new Intl.NumberFormat('pt-BR', {style:'currency', currency:'BRL'}).format(Number(valor));
}

function renderizarResultados(dados) {
    const itens = dados.itens || [];
    const resumo = dados.resumo || {resultado:'NEGATIVA', quantidadeRegistros:0, valorCertidao:'139.93'};
    const corpo = document.getElementById('regaux-resultados');
    document.getElementById('regaux-total-resultados').textContent = `${resumo.quantidadeRegistros} ${resumo.quantidadeRegistros === 1 ? 'resultado' : 'resultados'}`;
    document.getElementById('regaux-certidao-resumo').hidden = false;
    const resultado = document.getElementById('regaux-certidao-resultado');
    resultado.textContent = resumo.resultado;
    resultado.dataset.resultado = resumo.resultado;
    document.getElementById('regaux-certidao-quantidade').textContent = formatarNumero(resumo.quantidadeRegistros);
    document.getElementById('regaux-certidao-valor').textContent = formatarMoeda(resumo.valorCertidao);
    corpo.innerHTML = itens.map(item => {
        const pessoas = (item.pessoas || []).map(pessoa => `
            <div class="regaux-pessoa"><strong>${escaparHtml(pessoa.nome)}</strong><small>${escaparHtml(pessoa.papel)} · ${escaparHtml(pessoa.documento)}</small></div>
        `).join('') || '<span class="regaux-ausente">Nenhuma pessoa identificada</span>';
        const produtos = item.produtos?.length ? item.produtos.join(', ') : 'NÃO CONSTA';
        const safras = item.safras?.length ? item.safras.join(', ') : 'NÃO CONSTA';
        return `<tr>
            <td data-label="Registro"><strong class="regaux-numero">${formatarNumero(item.numero)}</strong><small>${new Intl.DateTimeFormat('pt-BR').format(new Date(item.consultadoEm))}</small></td>
            <td data-label="Situação"><span class="regaux-situacao">${escaparHtml(item.situacao)}</span></td>
            <td data-label="Modalidade"><span class="regaux-modalidade">${escaparHtml(rotuloModalidade(item.modalidade))}</span></td>
            <td data-label="Emitente/devedor">${pessoas}</td>
            <td data-label="Produto">${escaparHtml(produtos)}</td>
            <td data-label="Safra">${escaparHtml(safras)}</td>
        </tr>`;
    }).join('') || '<tr><td colspan="6" class="rotina-vazio">Nenhum Registro Auxiliar ativo encontrado com esses filtros.</td></tr>';
}

export async function carregarRegistrosAuxiliares(opcoes = {}) {
    const admin = ['ADMIN', 'SUBSTITUTO'].includes(document.body.dataset.perfil);
    if (!admin && !window.aeriPermissoes?.gerenciar_custas) return;
    document.getElementById('regaux-sincronizacao').hidden = !admin;
    try {
        atualizarStatus(await requisicaoAeri(
            '/api/registros-auxiliares/status',
            {background:Boolean(opcoes.background)},
        ));
    } catch (erro) {
        document.getElementById('regaux-atualizado').textContent = erro.message;
    }
}

export function limparRegistrosAuxiliares() {
    sincronizando = false;
    estadoAtual = null;
    document.getElementById('regaux-resultados').innerHTML = '<tr><td colspan="6" class="rotina-vazio">Entre novamente para pesquisar.</td></tr>';
    document.getElementById('regaux-certidao-resumo').hidden = true;
}

async function pesquisar(evento) {
    evento?.preventDefault();
    const botao = document.getElementById('btn-regaux-pesquisar');
    botao.disabled = true;
    const parametros = new URLSearchParams();
    const campos = {
        busca: document.getElementById('regaux-busca').value.trim(),
        produto: document.getElementById('regaux-produto').value,
        safra: document.getElementById('regaux-safra').value.trim(),
        modalidade: document.getElementById('regaux-modalidade').value,
    };
    Object.entries(campos).forEach(([chave, valor]) => { if (valor) parametros.set(chave, valor); });
    document.getElementById('regaux-resultados').innerHTML = '<tr><td colspan="6" class="rotina-vazio">Pesquisando nos textos indexados…</td></tr>';
    try {
        renderizarResultados(await requisicaoAeri(`/api/registros-auxiliares?${parametros}`));
    } catch (erro) {
        document.getElementById('regaux-resultados').innerHTML = `<tr><td colspan="6" class="rotina-vazio">${escaparHtml(erro.message)}</td></tr>`;
    } finally {
        botao.disabled = false;
    }
}

function atualizarBotaoSincronizacao() {
    const botao = document.getElementById('btn-regaux-sincronizar');
    botao.textContent = sincronizando ? 'Pausar sincronização' : 'Iniciar sincronização';
    botao.classList.toggle('pausar', sincronizando);
}

async function sincronizarCargaInicial() {
    sincronizando = true;
    atualizarBotaoSincronizacao();
    const limite = Number(document.getElementById('regaux-limite').value || 29538);
    let falhasTemporarias = 0;
    while (sincronizando) {
        try {
            const resultado = await requisicaoAeri('/api/registros-auxiliares/sincronizar', {
                method:'POST', headers:{'Content-Type':'application/json'},
                body:JSON.stringify({modo:'INICIAL', tamanho:20, limite}),
            });
            falhasTemporarias = 0;
            atualizarStatus(resultado.estado);
            document.getElementById('regaux-lote-status').textContent = resultado.falha
                ? resultado.falha
                : `Lote: ${resultado.processados} consultados · ${resultado.encontrados} encontrados · ${resultado.ausentes} sem texto · ${resultado.falhas || 0} falha(s)`;
            if (resultado.falha || resultado.estado.cargaInicialConcluida || resultado.processados === 0) break;
            await new Promise(resolve => window.setTimeout(resolve, 180));
        } catch (erro) {
            const mensagem = erro.message || 'Falha temporária na sincronização.';
            if (/sess[aã]o expirou|permiss[aã]o|troque sua senha/i.test(mensagem)) {
                document.getElementById('regaux-lote-status').textContent = mensagem;
                break;
            }
            falhasTemporarias += 1;
            document.getElementById('regaux-lote-status').textContent = `${mensagem} Tentando novamente (${falhasTemporarias}/5)...`;
            if (falhasTemporarias >= 5) break;
            await new Promise(resolve => window.setTimeout(resolve, 2000 * falhasTemporarias));
        }
    }
    sincronizando = false;
    atualizarBotaoSincronizacao();
}
function atualizarBotaoRevisao() {
    const botao = document.getElementById('btn-regaux-revisar');
    botao.textContent = revisando ? 'Pausar revisão' : 'Revisar registros indexados';
    botao.classList.toggle('pausar', revisando);
}

async function revisarRegistros() {
    revisando = true;
    atualizarBotaoRevisao();
    const inicioProximoRevisao = estadoAtual?.proximoRevisao ?? 1;
    let processadosNestaVolta = 0;
    let falhasTemporarias = 0;
    while (revisando) {
        try {
            const resultado = await requisicaoAeri('/api/registros-auxiliares/sincronizar', {
                method:'POST', headers:{'Content-Type':'application/json'},
                body:JSON.stringify({modo:'REVISAO', tamanho:20}),
            });
            falhasTemporarias = 0;
            atualizarStatus(resultado.estado);
            processadosNestaVolta += resultado.processados;
            document.getElementById('regaux-lote-status').textContent = resultado.falha
                ? resultado.falha
                : `Revisão: ${processadosNestaVolta} de ${formatarNumero(estadoAtual.totalIndexados)} revisado(s) nesta volta · ${resultado.alterados} atualizado(s) neste lote.`;
            // Uma volta completa termina quando o cursor de revisão volta a
            // cruzar o ponto de partida, ou quando não sobra nada indexado
            // pra revisar.
            const completouVolta = processadosNestaVolta > 0
                && resultado.estado.proximoRevisao >= inicioProximoRevisao
                && processadosNestaVolta >= estadoAtual.totalIndexados;
            if (resultado.falha || resultado.processados === 0 || completouVolta) break;
            await new Promise(resolve => window.setTimeout(resolve, 180));
        } catch (erro) {
            const mensagem = erro.message || 'Falha temporária na revisão.';
            if (/sess[aã]o expirou|permiss[aã]o|troque sua senha/i.test(mensagem)) {
                document.getElementById('regaux-lote-status').textContent = mensagem;
                break;
            }
            falhasTemporarias += 1;
            document.getElementById('regaux-lote-status').textContent = `${mensagem} Tentando novamente (${falhasTemporarias}/5)...`;
            if (falhasTemporarias >= 5) break;
            await new Promise(resolve => window.setTimeout(resolve, 2000 * falhasTemporarias));
        }
    }
    revisando = false;
    atualizarBotaoRevisao();
}

function alternarRevisao() {
    if (revisando) {
        revisando = false;
        atualizarBotaoRevisao();
        document.getElementById('regaux-lote-status').textContent = 'Pausa solicitada. O lote atual será concluído.';
        return;
    }
    revisarRegistros();
}

function alternarSincronizacao() {
    if (sincronizando) {
        sincronizando = false;
        atualizarBotaoSincronizacao();
        document.getElementById('regaux-lote-status').textContent = 'Pausa solicitada. O lote atual será concluído.';
        return;
    }
    sincronizarCargaInicial();
}

async function buscarNovos() {
    const botao = document.getElementById('btn-regaux-novos');
    botao.disabled = true;
    const rotuloOriginal = botao.textContent;
    botao.textContent = 'Consultando…';
    const primeiroNumero = Number(estadoAtual?.ultimoExistente || 0) + 1;
    document.getElementById('regaux-lote-status').textContent = primeiroNumero > 1
        ? `Consultando novos registros a partir do ${formatarNumero(primeiroNumero)}…`
        : 'Consultando novos Registros Auxiliares na Tri7…';
    try {
        let totalReprocessado = 0;
        // Reprocessa até esvaziar a fila de erros (ou até 20 lotes, como
        // limite de segurança), em vez de só um lote de cada vez — falhas
        // transitórias (rede, limite de taxa da Tri7) tendem a se resolver
        // sozinhas numa nova tentativa.
        for (let volta = 0; volta < 20 && Number(estadoAtual?.errosPendentes || 0) > 0; volta += 1) {
            const falhasReprocessadas = await requisicaoAeri('/api/registros-auxiliares/sincronizar', {
                method:'POST', headers:{'Content-Type':'application/json'},
                body:JSON.stringify({modo:'ERROS', tamanho:30}),
            });
            atualizarStatus(falhasReprocessadas.estado);
            totalReprocessado += falhasReprocessadas.processados;
            if (falhasReprocessadas.processados === 0) break;
        }
        const resultado = await requisicaoAeri('/api/registros-auxiliares/sincronizar', {
            method:'POST', headers:{'Content-Type':'application/json'},
            body:JSON.stringify({modo:'NOVOS', tamanho:30}),
        });
        atualizarStatus(resultado.estado);
        const reprocessados = totalReprocessado ? ` ${totalReprocessado} falha(s) reprocessada(s).` : '';
        const incluidos = (resultado.numerosNovos || []).length
            ? ` Incluídos: ${(resultado.numerosNovos || []).map(formatarNumero).join(', ')}.`
            : '';
        document.getElementById('regaux-lote-status').textContent = `${resultado.novos} novo(s) Registro(s) Auxiliar(es) encontrado(s).${incluidos}${reprocessados}`;
    } catch (erro) {
        document.getElementById('regaux-lote-status').textContent = erro.message;
    } finally {
        botao.disabled = false;
        botao.textContent = rotuloOriginal;
    }
}

async function revisarNumero() {
    const campo = document.getElementById('regaux-numero-revisar');
    const botao = document.getElementById('btn-regaux-revisar-numero');
    const numero = Number(campo.value);
    if (!Number.isInteger(numero) || numero <= 0) {
        document.getElementById('regaux-lote-status').textContent = 'Informe um número de Registro Auxiliar válido.';
        return;
    }
    botao.disabled = true;
    document.getElementById('regaux-lote-status').textContent = `Consultando o registro ${numero} na Tri7…`;
    try {
        const resultado = await requisicaoAeri(`/api/registros-auxiliares/${numero}/revisar`, {method:'POST'});
        if (resultado.estado) atualizarStatus(resultado.estado);
        document.getElementById('regaux-lote-status').textContent = resultado.novo
            ? `Registro ${formatarNumero(numero)} incluído no índice com sucesso.`
            : resultado.item.alterado
                ? `Registro ${formatarNumero(numero)} revisado: houve alteração (nova averbação/retificação capturada).`
                : `Registro ${formatarNumero(numero)} revisado: sem alterações desde a última consulta.`;
        campo.value = '';
    } catch (erro) {
        document.getElementById('regaux-lote-status').textContent = erro.message;
    } finally {
        botao.disabled = false;
    }
}

async function verErrosSincronizacao() {
    const botao = document.getElementById('btn-regaux-ver-erros');
    const painel = document.getElementById('regaux-erros');
    if (!painel.hidden) {
        painel.hidden = true;
        return;
    }
    botao.disabled = true;
    try {
        const erros = await requisicaoAeri('/api/registros-auxiliares/erros');
        document.getElementById('regaux-erros-tbody').innerHTML = erros.map(item => `<tr>
            <td>${formatarNumero(item.numero)}</td>
            <td>${item.tentativas}</td>
            <td>${new Intl.DateTimeFormat('pt-BR', {dateStyle:'short', timeStyle:'short'}).format(new Date(item.ultimaTentativaEm))}</td>
            <td>${escaparHtml(item.erro)}</td>
        </tr>`).join('') || '<tr><td colspan="4" class="rotina-vazio">Nenhuma falha pendente.</td></tr>';
        painel.hidden = false;
    } catch (erro) {
        alert(erro.message);
    } finally {
        botao.disabled = false;
    }
}

export function iniciarRegistrosAuxiliares() {
    document.getElementById('form-regaux-pesquisa').addEventListener('submit', pesquisar);
    document.getElementById('btn-regaux-sincronizar').addEventListener('click', alternarSincronizacao);
    document.getElementById('btn-regaux-novos').addEventListener('click', buscarNovos);
    document.getElementById('btn-regaux-ver-erros').addEventListener('click', verErrosSincronizacao);
    document.getElementById('btn-regaux-revisar').addEventListener('click', alternarRevisao);
    document.getElementById('btn-regaux-revisar-numero').addEventListener('click', revisarNumero);
}
