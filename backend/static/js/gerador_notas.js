import {requisicaoAeri} from './api.js?v=20260824-csrf-v1';
import {escaparHtml} from './util.js';

const API = '/api/gerador-notas';
let acessoPermitido = false;
let iniciado = false;
let catalogo = null;
let legislacao = null;
let base = null;
let apenasSelecionadas = false;
const selecionadas = new Set();
const valores = new Map();
const $ = id => document.getElementById(`gn-${id}`);

function identificarErro(erro) {
    return erro.identificador ? `${erro.message} Código para suporte: ${erro.identificador}.` : erro.message;
}

function estado(tipo, mensagem) {
    const alvo = $('estado');
    alvo.className = `modulo-estado ${tipo || ''}`.trim();
    alvo.querySelector('span:last-child').textContent = mensagem;
    alvo.hidden = !mensagem;
}

function vazio(texto) {
    return `<div class="gerador-notas-vazio">${escaparHtml(texto)}</div>`;
}

function abrirModal(titulo, corpo) {
    $('modal-titulo').textContent = titulo;
    $('modal-corpo').innerHTML = corpo;
    const modal = $('modal');
    modal.hidden = false;
    modal.classList.add('aberta');
}

function fecharModal() {
    const modal = $('modal');
    modal.classList.remove('aberta');
    modal.hidden = true;
}

function montarItens() {
    return [...selecionadas].map(id => {
        const exigencia = catalogo.exigencias.find(item => item.id === id);
        return {
            exigencia: id,
            valores: Object.fromEntries(exigencia.campos.map(campo => [
                campo, (valores.get(`${id}|${campo}`) || '').trim(),
            ])),
        };
    });
}

function atualizarResumo() {
    const total = selecionadas.size;
    $('contagem').textContent = total
        ? `${total} pendência${total === 1 ? '' : 's'} selecionada${total === 1 ? '' : 's'}`
        : 'Nenhuma pendência selecionada';
    const pendentes = catalogo.exigencias.filter(item => selecionadas.has(item.id) && !item.revisado).length;
    $('aviso').textContent = pendentes
        ? `${pendentes} item(ns) ainda exige(m) conferência interna da fundamentação.` : '';
}

function desenharLista() {
    const termo = $('filtro').value.trim().toLocaleLowerCase('pt-BR');
    const visiveis = catalogo.exigencias.filter(item =>
        (!apenasSelecionadas || selecionadas.has(item.id))
        && (!termo || `${item.rotulo} ${item.assunto} ${item.defeito}`.toLocaleLowerCase('pt-BR').includes(termo))
    );
    $('apenas-selecionadas').classList.toggle('ativo', apenasSelecionadas);
    $('apenas-selecionadas').textContent = selecionadas.size
        ? `Selecionadas (${selecionadas.size})` : 'Apenas selecionadas';
    $('lista').innerHTML = visiveis.length ? visiveis.map(item => `<label class="gerador-notas-item ${selecionadas.has(item.id) ? 'marcado' : ''}">
        <input type="checkbox" data-gn-exigencia="${item.id}" ${selecionadas.has(item.id) ? 'checked' : ''}>
        <span><strong>${escaparHtml(item.rotulo)}</strong><small>${escaparHtml(item.assunto)}${item.revisado ? '' : ' · conferência pendente'}</small></span>
    </label>`).join('') : vazio('Nenhuma pendência encontrada.');
}

function desenharCampos() {
    const itens = catalogo.exigencias.filter(item => selecionadas.has(item.id));
    if (!itens.length) {
        $('campos').innerHTML = vazio('Selecione as pendências ao lado.');
        return;
    }
    $('campos').innerHTML = itens.map(item => `<section class="gerador-notas-grupo">
        <h3>${escaparHtml(item.rotulo)}</h3>
        ${item.campos.length ? item.campos.map(campo => {
            const definicao = catalogo.campos[campo] || {};
            const opcional = !(item.obrigatorios || []).includes(campo);
            const valor = valores.get(`${item.id}|${campo}`) || '';
            const controle = definicao.opcoes
                ? `<select data-gn-campo="${campo}" data-gn-item="${item.id}"><option value="">${opcional ? '— não informar —' : '— escolha —'}</option>${definicao.opcoes.map(opcao => `<option ${opcao === valor ? 'selected' : ''}>${escaparHtml(opcao)}</option>`).join('')}</select>`
                : `<input data-gn-campo="${campo}" data-gn-item="${item.id}" value="${escaparHtml(valor)}" placeholder="${escaparHtml(item.exemplos?.[campo] || definicao.exemplo || '')}">`;
            return `<div class="gerador-notas-campo"><label>${escaparHtml(definicao.rotulo || campo)}${opcional ? ' (opcional)' : ''}</label>${controle}</div>`;
        }).join('') : '<div class="gerador-notas-vazio">Esta pendência não pede dados adicionais.</div>'}
    </section>`).join('');
}

let temporizadorPrevia;
function solicitarPrevia() {
    clearTimeout(temporizadorPrevia);
    temporizadorPrevia = setTimeout(atualizarPrevia, 350);
}

async function atualizarPrevia() {
    if (!selecionadas.size) {
        $('previa').innerHTML = vazio('A nota aparecerá aqui conforme as pendências forem selecionadas.');
        $('previa-aviso').textContent = '';
        return;
    }
    try {
        const resposta = await requisicaoAeri(`${API}/previa`, {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({especie: $('especie').value, titulo: $('titulo').value.trim(), judicial: $('judicial').checked, itens: montarItens()}),
        });
        $('previa').innerHTML = resposta.html || vazio('A prévia ainda não possui conteúdo.');
        $('previa-aviso').textContent = resposta.faltando?.length ? `Falta preencher: ${resposta.faltando.join(', ')}` : '';
    } catch (erro) {
        $('previa').innerHTML = vazio(identificarErro(erro));
    }
}

function baixarDocumento(base64, nome) {
    const bytes = Uint8Array.from(atob(base64), caractere => caractere.charCodeAt(0));
    const url = URL.createObjectURL(new Blob([bytes], {type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'}));
    const link = document.createElement('a');
    link.href = url; link.download = nome;
    document.body.appendChild(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 5000);
}

async function gerar() {
    if (!selecionadas.size) return abrirModal('Nota vazia', '<p>Selecione ao menos uma pendência.</p>');
    if (!$('titulo').value.trim()) return abrirModal('Falta o título', '<p>Informe o título apresentado.</p>');
    $('gerar').disabled = true;
    estado('', 'Gerando o documento…');
    try {
        const resposta = await requisicaoAeri(`${API}/gerar`, {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({especie: $('especie').value, titulo: $('titulo').value.trim(), protocolo: $('protocolo').value.trim(), judicial: $('judicial').checked, itens: montarItens()}),
        });
        baixarDocumento(resposta.conteudo, resposta.arquivo);
        estado('sucesso', `Documento ${resposta.arquivo} gerado com sucesso.`);
        const alerta = resposta.nao_revisadas?.length
            ? `<p><strong>Confira antes de expedir:</strong> ${resposta.nao_revisadas.map(escaparHtml).join(', ')}.</p>` : '';
        abrirModal('Nota gerada', `<p>O arquivo <strong>${escaparHtml(resposta.arquivo)}</strong> foi baixado.</p>${alerta}`);
    } catch (erro) {
        estado('erro', identificarErro(erro));
        abrirModal('Não foi possível gerar', `<p>${escaparHtml(identificarErro(erro))}</p>`);
    } finally { $('gerar').disabled = false; }
}

function renderizarLegislacao() {
    const termo = $('legislacao-filtro').value.trim().toLocaleLowerCase('pt-BR');
    const itens = legislacao.filter(item => `${item.nome} ${item.referencia} ${item.esfera}`.toLocaleLowerCase('pt-BR').includes(termo));
    $('legislacao-lista').innerHTML = itens.length ? itens.map(item => `<article>
        <h3>${escaparHtml(item.nome)}</h3><p>${escaparHtml(item.referencia || 'Referência não informada')}</p>
        <p>${escaparHtml(item.esfera || 'Esfera não informada')} · ${item.artigos} dispositivo(s) indexado(s)</p>
    </article>`).join('') : vazio('Nenhuma norma encontrada.');
}

function renderizarBase() {
    const termo = $('base-filtro').value.trim().toLocaleLowerCase('pt-BR');
    const itens = base.filter(item => `${item.rotulo} ${item.texto}`.replace(/<[^>]+>/g, ' ').toLocaleLowerCase('pt-BR').includes(termo));
    $('base-lista').innerHTML = itens.length ? itens.map(item => `<article class="gerador-notas-base-item">
        <h3>${escaparHtml(item.rotulo)}</h3><p>${item.texto}</p>
        <details><summary>${item.fundamentos.length} fundamento(s) e ${item.precedentes.length} precedente(s)</summary>
            ${item.fundamentos.map(f => `<p><strong>${escaparHtml(f.norma)} · ${escaparHtml(f.artigo)}</strong><br>${escaparHtml(f.texto || '')}</p>`).join('') || '<p>Nenhum fundamento cadastrado.</p>'}
        </details>
    </article>`).join('') : vazio('Nenhum texto encontrado.');
}

async function trocarAba(aba) {
    document.querySelectorAll('[data-gn-aba]').forEach(botao => botao.classList.toggle('ativa', botao.dataset.gnAba === aba));
    ['editor', 'legislacao', 'base'].forEach(nome => $(nome).hidden = nome !== aba);
    try {
        if (aba === 'legislacao' && !legislacao) {
            estado('', 'Carregando legislação…'); legislacao = await requisicaoAeri(`${API}/legislacao`); renderizarLegislacao(); estado('', '');
        }
        if (aba === 'base' && !base) {
            estado('', 'Carregando a base cadastrada…'); base = await requisicaoAeri(`${API}/revisao`); renderizarBase(); estado('', '');
        }
    } catch (erro) { estado('erro', identificarErro(erro)); }
}

async function carregar() {
    if (iniciado || !acessoPermitido) return;
    iniciado = true;
    estado('', 'Carregando o Gerador de Notas…');
    try {
        catalogo = await requisicaoAeri(`${API}/catalogo`);
        $('especie').innerHTML = catalogo.especies.map(item => `<option value="${item.id}">${escaparHtml(item.rotulo)}</option>`).join('');
        desenharLista(); desenharCampos(); atualizarResumo(); atualizarPrevia();
        $('editor').hidden = false; estado('', '');
    } catch (erro) { iniciado = false; estado('erro', identificarErro(erro)); }
}

function carregarSeNecessario() {
    if (document.querySelector('.nav-item.active')?.dataset.page === 'geradornotas') carregar();
}

export function configurarAcessoGeradorNotas(permitido) {
    acessoPermitido = Boolean(permitido);
    carregarSeNecessario();
}

export function iniciarGeradorNotas() {
    window.addEventListener('aeri:pagina-alterada', carregarSeNecessario);
    document.querySelectorAll('[data-gn-aba]').forEach(botao => botao.addEventListener('click', () => trocarAba(botao.dataset.gnAba)));
    $('lista').addEventListener('change', evento => {
        const campo = evento.target.closest('[data-gn-exigencia]');
        if (!campo) return;
        campo.checked ? selecionadas.add(campo.dataset.gnExigencia) : selecionadas.delete(campo.dataset.gnExigencia);
        desenharLista(); desenharCampos(); atualizarResumo(); solicitarPrevia();
    });
    $('campos').addEventListener('input', evento => {
        const campo = evento.target.closest('[data-gn-campo]');
        if (!campo) return;
        valores.set(`${campo.dataset.gnItem}|${campo.dataset.gnCampo}`, campo.value); solicitarPrevia();
    });
    $('campos').addEventListener('change', evento => {
        if (evento.target.matches('select[data-gn-campo]')) evento.target.dispatchEvent(new Event('input', {bubbles: true}));
    });
    $('filtro').addEventListener('input', desenharLista);
    $('apenas-selecionadas').addEventListener('click', () => { apenasSelecionadas = !apenasSelecionadas; desenharLista(); });
    ['especie', 'titulo', 'judicial'].forEach(id => $(id).addEventListener(id === 'judicial' ? 'change' : 'input', solicitarPrevia));
    $('gerar').addEventListener('click', gerar);
    $('legislacao-filtro').addEventListener('input', () => legislacao && renderizarLegislacao());
    $('base-filtro').addEventListener('input', () => base && renderizarBase());
    $('modal-fechar').addEventListener('click', fecharModal);
    $('modal-ok').addEventListener('click', fecharModal);
}
