import {requisicaoAeri} from './api.js';
import {escaparHtml} from './util.js';

let sincronizando = false;
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
    document.getElementById('regaux-limite').value = estado.limiteInicial;
    document.getElementById('regaux-atualizado').textContent = estado.ultimaSincronizacao
        ? `Última atualização: ${new Intl.DateTimeFormat('pt-BR', {dateStyle:'short', timeStyle:'short'}).format(new Date(estado.ultimaSincronizacao))}`
        : 'A sincronização ainda não foi iniciada.';
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
            <td data-label="Ação"><button type="button" class="regaux-texto-btn" data-regaux-texto="${item.numero}">Ver texto atualizado</button></td>
        </tr>`;
    }).join('') || '<tr><td colspan="7" class="rotina-vazio">Nenhum Registro Auxiliar ativo encontrado com esses filtros.</td></tr>';
}

export async function carregarRegistrosAuxiliares() {
    const admin = ['ADMIN', 'SUBSTITUTO'].includes(document.body.dataset.perfil);
    if (!admin && !window.aeriPermissoes?.gerenciar_custas) return;
    document.getElementById('regaux-sincronizacao').hidden = !admin;
    try {
        atualizarStatus(await requisicaoAeri('/api/registros-auxiliares/status'));
    } catch (erro) {
        document.getElementById('regaux-atualizado').textContent = erro.message;
    }
}

export function limparRegistrosAuxiliares() {
    sincronizando = false;
    estadoAtual = null;
    document.getElementById('regaux-resultados').innerHTML = '<tr><td colspan="7" class="rotina-vazio">Entre novamente para pesquisar.</td></tr>';
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
    document.getElementById('regaux-resultados').innerHTML = '<tr><td colspan="7" class="rotina-vazio">Pesquisando nos textos indexados…</td></tr>';
    try {
        renderizarResultados(await requisicaoAeri(`/api/registros-auxiliares?${parametros}`));
    } catch (erro) {
        document.getElementById('regaux-resultados').innerHTML = `<tr><td colspan="7" class="rotina-vazio">${escaparHtml(erro.message)}</td></tr>`;
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
    while (sincronizando) {
        try {
            const resultado = await requisicaoAeri('/api/registros-auxiliares/sincronizar', {
                method:'POST', headers:{'Content-Type':'application/json'},
                body:JSON.stringify({modo:'INICIAL', tamanho:20, limite}),
            });
            atualizarStatus(resultado.estado);
            document.getElementById('regaux-lote-status').textContent = resultado.falha
                ? resultado.falha
                : `Lote: ${resultado.processados} consultados · ${resultado.encontrados} encontrados · ${resultado.ausentes} sem texto`;
            if (resultado.falha || resultado.estado.cargaInicialConcluida || resultado.processados === 0) break;
            await new Promise(resolve => window.setTimeout(resolve, 180));
        } catch (erro) {
            document.getElementById('regaux-lote-status').textContent = erro.message;
            break;
        }
    }
    sincronizando = false;
    atualizarBotaoSincronizacao();
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
    try {
        const resultado = await requisicaoAeri('/api/registros-auxiliares/sincronizar', {
            method:'POST', headers:{'Content-Type':'application/json'},
            body:JSON.stringify({modo:'NOVOS', tamanho:30}),
        });
        atualizarStatus(resultado.estado);
        document.getElementById('regaux-lote-status').textContent = `${resultado.novos} novo(s) Registro(s) Auxiliar(es) encontrado(s).`;
    } catch (erro) {
        document.getElementById('regaux-lote-status').textContent = erro.message;
    } finally {
        botao.disabled = false;
    }
}

async function abrirTexto(evento) {
    const botao = evento.target.closest('[data-regaux-texto]');
    if (!botao) return;
    botao.disabled = true;
    try {
        const dados = await requisicaoAeri(`/api/registros-auxiliares/${botao.dataset.regauxTexto}/texto`);
        document.getElementById('regaux-texto-titulo').textContent = `Registro Auxiliar ${formatarNumero(botao.dataset.regauxTexto)}`;
        document.getElementById('regaux-texto-conteudo').textContent = dados.texto;
        document.getElementById('modal-regaux-texto').classList.add('aberta');
    } catch (erro) {
        alert(erro.message);
    } finally {
        botao.disabled = false;
    }
}

function fecharTexto() {
    document.getElementById('modal-regaux-texto').classList.remove('aberta');
    document.getElementById('regaux-texto-conteudo').textContent = '';
}

export function iniciarRegistrosAuxiliares() {
    document.getElementById('form-regaux-pesquisa').addEventListener('submit', pesquisar);
    document.getElementById('btn-regaux-sincronizar').addEventListener('click', alternarSincronizacao);
    document.getElementById('btn-regaux-novos').addEventListener('click', buscarNovos);
    document.getElementById('regaux-resultados').addEventListener('click', abrirTexto);
    document.getElementById('btn-fechar-regaux-texto').addEventListener('click', fecharTexto);
}
