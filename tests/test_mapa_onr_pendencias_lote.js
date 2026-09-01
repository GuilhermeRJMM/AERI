'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');

function criarElemento(tag) {
  const el = {
    tagName: tag, className: '', id: '', type: '', textContent: '',
    checked: false, indeterminate: false, filhos: [], parentNode: null,
    ouvintes: {},
    classList: { toggle() {}, add() {}, remove() {} },
    appendChild(filho) { filho.parentNode = el; el.filhos.push(filho); return filho; },
    append(...itens) {
      for (const item of itens) el.appendChild(typeof item === 'string' ? { textContent: item, filhos: [] } : item);
    },
    insertBefore(novo) { novo.parentNode = el; el.filhos.push(novo); return novo; },
    addEventListener(tipo, fn) { (el.ouvintes[tipo] = el.ouvintes[tipo] || []).push(fn); },
    disparar(tipo, evento) { for (const fn of el.ouvintes[tipo] || []) fn(evento || {}); },
    scrollIntoView() {},
    remove() {
      const pai = el.parentNode;
      if (pai) pai.filhos = pai.filhos.filter((f) => f !== el);
    },
    descendentes() {
      const saida = [];
      for (const filho of el.filhos) {
        if (!filho || !filho.filhos) continue;
        saida.push(filho, ...(filho.descendentes ? filho.descendentes() : []));
      }
      return saida;
    },
    querySelectorAll(seletor) {
      const [classe, tagFilha] = seletor.split(/\s+/);
      const base = el.descendentes().filter((n) => String(n.className || '').split(/\s+/).includes(classe.slice(1)));
      if (!tagFilha) return base;
      return base.flatMap((n) => (n.descendentes ? n.descendentes() : []))
                 .filter((n) => n.tagName === tagFilha);
    },
    querySelector(seletor) { return el.querySelectorAll(seletor)[0] || null; },
  };
  return el;
}

function montar(quantidadePendencias) {
  const raiz = criarElemento('div');
  const ficha = criarElemento('div');
  ficha.id = 'ficha-imovel';
  raiz.appendChild(ficha);
  const botoes = {};
  for (const id of ['btn-ler', 'btn-exemplo', 'btn-exemplo-urbano', 'btn-gerar']) {
    botoes[id] = criarElemento('button');
    botoes[id].id = id;
  }

  const documento = {
    head: criarElemento('head'),
    createElement: criarElemento,
    createTextNode: (txt) => ({ textContent: txt, filhos: [] }),
    getElementById(id) {
      if (botoes[id]) return botoes[id];
      if (id === 'ficha-imovel') return ficha;
      return raiz.descendentes().find((n) => n.id === id) || null;
    },
  };

  const contexto = {
    document: documento,
    queueMicrotask: (fn) => fn(),
    ONR_EXTRATOR: { extraiConfrontantes: () => null },
    ouvintesGlobais: {},
  };
  contexto.window = contexto;
  contexto.globalThis = contexto;
  contexto.addEventListener = (tipo, fn) => {
    (contexto.ouvintesGlobais[tipo] = contexto.ouvintesGlobais[tipo] || []).push(fn);
  };
  vm.createContext(contexto);
  const arquivo = path.join(__dirname, '../backend/static/js/mapa_onr_hibrido.js');
  vm.runInContext(fs.readFileSync(arquivo, 'utf8'), contexto);

  const confrontantes = [];
  for (let i = 0; i < quantidadePendencias; i += 1) {
    confrontantes.push({
      numero_matricula_confrontante: String(1000 + i),
      descricoes_confrontacao: ['divisa seca'],
      evidencias: ['trecho'],
      pendencia: 'proprietario nao identificado com seguranca',
    });
  }
  for (const fn of contexto.ouvintesGlobais.message || []) {
    fn({ data: { tipo: 'AERI_MAPA_ONR_MATRICULA', contextoAeri: { modo: 'hibrido', confrontantes } } });
  }

  const painel = raiz.descendentes().find((n) => n.id === 'aeri-revisao-confrontantes');
  return { painel, botoes, contexto };
}

test('a caixinha de marcar todas aparece com a contagem das pendencias', () => {
  const { painel } = montar(3);
  const mestre = painel.querySelector('.aeri-revisao-mestre input');
  assert.ok(mestre, 'a caixinha de acao em lote precisa existir');
  const rotulo = painel.querySelectorAll('.aeri-revisao-mestre')[0];
  const texto = rotulo.filhos.map((f) => f.textContent).join('');
  assert.match(texto, /Marcar todas as 3/);
});

test('marcar todas libera a exportacao de uma vez', () => {
  const { painel, botoes } = montar(4);
  const mestre = painel.querySelector('.aeri-revisao-mestre input');

  assert.match(painel.querySelector('.aeri-bloqueio').textContent, /bloqueada até conferir 4/);

  mestre.checked = true;
  mestre.parentNode.filhos[0].disparar('change');

  assert.match(painel.querySelector('.aeri-bloqueio').textContent, /pode ser gerado/);
  for (const caixa of painel.querySelectorAll('.aeri-revisao-item input')) {
    assert.equal(caixa.checked, true, 'as caixas individuais precisam refletir o lote');
  }

  let bloqueou = false;
  botoes['btn-gerar'].disparar('click', {
    preventDefault: () => { bloqueou = true; },
    stopImmediatePropagation: () => {},
  });
  assert.equal(bloqueou, false, 'com tudo marcado o botao Gerar nao pode ser barrado');
});

test('desmarcar o lote volta a bloquear', () => {
  const { painel, botoes } = montar(2);
  const mestre = painel.querySelector('.aeri-revisao-mestre input');
  mestre.checked = true;
  mestre.parentNode.filhos[0].disparar('change');
  mestre.checked = false;
  mestre.parentNode.filhos[0].disparar('change');

  assert.match(painel.querySelector('.aeri-bloqueio').textContent, /bloqueada até conferir 2/);
  let bloqueou = false;
  botoes['btn-gerar'].disparar('click', {
    preventDefault: () => { bloqueou = true; },
    stopImmediatePropagation: () => {},
  });
  assert.equal(bloqueou, true);
});

test('conferir so uma deixa o lote em estado intermediario', () => {
  const { painel } = montar(3);
  const individuais = painel.querySelectorAll('.aeri-revisao-item input');
  individuais[0].checked = true;
  individuais[0].disparar('change');

  const mestre = painel.querySelector('.aeri-revisao-mestre input');
  assert.equal(mestre.checked, false);
  assert.equal(mestre.indeterminate, true, 'parcial nao pode parecer nenhuma nem todas');
});
