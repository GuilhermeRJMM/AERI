// Lista as normas cadastradas e deixa consultar seus artigos.
'use strict';

const API = '/api/gerador-notas';
const $ = (id) => document.getElementById(id);
let NORMAS = [];
let atual = null;

const ESFERA = { federal: 'Federal', estadual: 'Estadual', municipal: 'Municipal' };

async function iniciar() {
  const resposta = await fetch(`${API}/legislacao`, {credentials: 'same-origin'});
  if (!resposta.ok) throw new Error('Não foi possível carregar a legislação.');
  NORMAS = await resposta.json();

  const artigos = NORMAS.reduce((s, n) => s + n.artigos, 0);
  $('contagem').textContent =
    `${NORMAS.length} normas · ${artigos.toLocaleString('pt-BR')} artigos indexados`;
  $('rodape').textContent =
    'Para acrescentar uma norma: salve o PDF em Fundamentações e cadastre-a em dados/normas.json.';

  desenhaNormas();
  $('filtro').addEventListener('input', desenhaNormas);
  $('busca-artigo').addEventListener('input', debounce(buscaArtigos, 250));
}

function debounce(fn, ms) {
  let t;
  return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
}

function desenhaNormas() {
  const termo = $('filtro').value.trim().toLowerCase();
  const alvo = $('normas');
  alvo.textContent = '';

  const visiveis = NORMAS.filter(n =>
    !termo || (n.nome + ' ' + n.referencia + ' ' + n.id).toLowerCase().includes(termo));

  if (!visiveis.length) {
    alvo.innerHTML = '<div class="vazio">Nenhuma norma com esse termo.</div>';
    return;
  }

  for (const n of visiveis) {
    const div = document.createElement('div');
    div.className = 'item norma-item' + (atual === n.id ? ' marcado' : '');
    div.onclick = () => selecionar(n.id);

    const texto = document.createElement('div');
    const nome = document.createElement('div');
    nome.className = 'nome';
    nome.textContent = n.nome;

    const meta = document.createElement('div');
    meta.className = 'meta';
    meta.append(`${ESFERA[n.esfera] || n.esfera} · ${n.artigos} artigos`);
    if (!n.tem_pdf) {
      const p = document.createElement('span');
      p.className = 'pilula';
      p.textContent = 'PDF ausente';
      meta.append(p);
    }
    texto.append(nome, meta);
    div.append(texto);
    alvo.append(div);
  }
}

async function selecionar(id) {
  atual = id;
  desenhaNormas();
  const n = NORMAS.find(x => x.id === id);
  $('titulo-detalhe').textContent = n.nome;
  $('busca-artigo').disabled = false;
  $('busca-artigo').value = '';

  const alvo = $('detalhe');
  alvo.textContent = '';

  const ficha = document.createElement('div');
  ficha.className = 'ficha';
  ficha.innerHTML =
    `<div><span>Referência</span>${n.referencia || '—'}</div>` +
    `<div><span>Arquivo</span>${n.arquivo}</div>` +
    `<div><span>Artigos indexados</span>${n.artigos}</div>`;
  alvo.append(ficha);

  const dica = document.createElement('div');
  dica.className = 'dica';
  dica.textContent = 'Use a busca acima para ver qualquer artigo desta norma — '
                   + 'pelo número (ex.: 176, 440-AQ) ou por assunto.';
  alvo.append(dica);
}

async function buscaArtigos() {
  if (!atual) return;
  const q = $('busca-artigo').value.trim();
  if (!q) return selecionar(atual);

  const r = await fetch(`${API}/artigos?norma=${encodeURIComponent(atual)}&q=${encodeURIComponent(q)}`, {
    credentials: 'same-origin',
  });
  if (!r.ok) throw new Error('Não foi possível consultar os artigos.');
  const achados = await r.json();

  const alvo = $('detalhe');
  alvo.textContent = '';
  if (!achados.length) {
    alvo.innerHTML = '<div class="vazio">Nada encontrado nesta norma.</div>';
    return;
  }
  for (const a of achados) {
    const d = document.createElement('div');
    d.className = 'artigo';
    const t = document.createElement('strong');
    t.textContent = a.artigo + '. ';
    d.append(t, document.createTextNode(a.texto));
    alvo.append(d);
  }
}

iniciar().catch(erro => {
  $('normas').textContent = erro.message;
});
