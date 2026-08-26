// Tela de revisão: mostra o texto que cada exigência produz e os artigos que
// cita, com um botão para o registrador validar ou desfazer a validação.
'use strict';

const API = '/api/gerador-notas';
const $ = (id) => document.getElementById(id);
let DADOS = [];

let SOMENTE_LEITURA = false;

async function iniciar() {
  const respostaCatalogo = await fetch(`${API}/catalogo`, {credentials: 'same-origin'});
  if (!respostaCatalogo.ok) throw new Error('Não foi possível carregar o catálogo.');
  const cat = await respostaCatalogo.json();
  SOMENTE_LEITURA = !!cat.somente_leitura;
  const respostaRevisao = await fetch(`${API}/revisao`, {credentials: 'same-origin'});
  if (!respostaRevisao.ok) throw new Error('Não foi possível carregar a revisão.');
  DADOS = await respostaRevisao.json();
  desenha();
}

function desenha() {
  const lista = $('lista');
  lista.textContent = '';

  for (const e of DADOS) {
    const cx = document.createElement('section');
    cx.className = 'cartao revisao-item' + (e.revisado ? ' validada' : '');

    const cab = document.createElement('div');
    cab.className = 'cabeca';
    const h = document.createElement('h2');
    h.textContent = e.rotulo;
    const b = document.createElement('button');
    b.className = e.revisado ? 'secundario' : 'primario';
    b.textContent = e.revisado ? 'Validada — desfazer' : 'Validar fundamentação';
    if (SOMENTE_LEITURA) {
      b.disabled = true;
      b.title = 'A validação grava no catálogo e só funciona na instalação do cartório.';
    } else {
      b.onclick = () => alterna(e.id, !e.revisado, b);
    }
    cab.append(h, b);

    const corpo = document.createElement('div');
    corpo.className = 'revisao-corpo';

    const p = document.createElement('p');
    p.className = 'texto-exigencia';
    p.innerHTML = e.texto;
    corpo.append(p);

    if (!e.fundamentos.length) {
      const s = document.createElement('div');
      s.className = 'sem-lei';
      s.textContent = e.pendente || 'Sem lei citada.';
      corpo.append(s);
    }

    let normaAtual = null;
    for (const f of e.fundamentos) {
      if (f.norma !== normaAtual) {
        const n = document.createElement('div');
        n.className = 'norma';
        n.textContent = f.norma;
        corpo.append(n);
        normaAtual = f.norma;
      }
      const a = document.createElement('div');
      a.className = 'artigo';
      const t = document.createElement('strong');
      t.textContent = f.artigo + '. ';
      a.append(t, document.createTextNode(f.texto));
      corpo.append(a);
    }

    if (e.precedentes && e.precedentes.length) {
      const h = document.createElement('div');
      h.className = 'norma';
      h.textContent = 'Jurisprudência';
      corpo.append(h);
      for (const j of e.precedentes) {
        const a = document.createElement('div');
        a.className = 'artigo precedente';
        const t = document.createElement('strong');
        t.textContent = j.identificacao + ' — ';
        const f = document.createElement('div');
        f.className = 'fonte';
        f.textContent = 'Origem da transcrição: ' + j.fonte;
        a.append(t, document.createTextNode('“' + j.texto + '”'), f);
        corpo.append(a);
      }
    }

    cx.append(cab, corpo);
    lista.append(cx);
  }
  contar();
}

function contar() {
  const n = DADOS.filter(e => e.revisado).length;
  $('contagem').textContent = `${n} de ${DADOS.length} validadas`;
}

function recado(botao, texto) {
  const cx = botao.closest('.revisao-item') || botao.parentElement;
  let aviso = cx.querySelector('.aviso-revisao');
  if (!aviso) {
    aviso = document.createElement('p');
    aviso.className = 'aviso-revisao';
    cx.append(aviso);
  }
  aviso.textContent = texto;      // textContent: nada do servidor vira marcacao
  aviso.hidden = !texto;
}

async function alterna(id, revisado, botao) {
  botao.disabled = true;
  recado(botao, '');
  let res;
  try {
    const r = await fetch('api/revisar', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id, revisado }),
    });
    const texto = await r.text();
    res = texto ? JSON.parse(texto) : {};
  } catch (erro) {
    // Sem este catch o botao ficava desabilitado para sempre: a funcao morria
    // antes de reabilita-lo, e o registrador so recuperava recarregando a
    // pagina - sem nada na tela dizendo o que houve.
    recado(botao, 'Não foi possível falar com o servidor. Recarregue a página e tente de novo.');
    botao.disabled = false;
    return;
  } finally {
    botao.disabled = false;
  }

  if (!res.ok) {
    // O servidor recusa com status 200 e explica no campo 'erro' (invariante
    // 7-B). Descartar a explicacao fazia o clique parecer sem efeito.
    recado(botao, res.erro || 'A validação não foi gravada.');
    return;
  }

  const e = DADOS.find(x => x.id === id);
  e.revisado = revisado;
  botao.textContent = revisado ? 'Validada — desfazer' : 'Validar fundamentação';
  botao.className = revisado ? 'secundario' : 'primario';
  botao.closest('.revisao-item').classList.toggle('validada', revisado);
  contar();
}

iniciar().catch(erro => {
  $('lista').textContent = erro.message;
});
