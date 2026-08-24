// Tela da nota devolutiva. Conversa com o servidor local em notadev/servidor.py.
'use strict';

const API = '/api/gerador-notas';
let csrfToken = '';
let CAT = null;                    // catalogo vindo do servidor
const selecionadas = new Set();
let apenasSelecionadas = false;            // filtro: esconder o que ainda não foi selecionado
const valores = new Map();         // "exigencia|campo" -> texto digitado

const $ = (id) => document.getElementById(id);

function escaparHtml(valor) {
  const elemento = document.createElement('span');
  elemento.textContent = String(valor ?? '');
  return elemento.innerHTML;
}

async function requisicao(caminho, opcoes = {}) {
  const metodo = String(opcoes.method || 'GET').toUpperCase();
  const headers = new Headers(opcoes.headers || {});
  if (!['GET', 'HEAD', 'OPTIONS'].includes(metodo)) {
    if (!csrfToken) {
      const sessao = await fetch('/api/sessao', {credentials: 'same-origin'});
      if (!sessao.ok) throw new Error('Sua sessão expirou. Entre novamente no AERI.');
      csrfToken = (await sessao.json()).csrfToken || '';
    }
    headers.set('X-CSRF-Token', csrfToken);
    headers.set('Content-Type', 'application/json');
  }
  const resposta = await fetch(`${API}${caminho}`, {
    ...opcoes,
    method: metodo,
    headers,
    credentials: 'same-origin',
  });
  const dados = await resposta.json().catch(() => ({}));
  if (!resposta.ok) throw new Error(dados.detail || 'Não foi possível concluir a operação.');
  return dados;
}

async function iniciar() {
  CAT = await requisicao('/catalogo');

  for (const e of CAT.especies) {
    const o = document.createElement('option');
    o.value = e.id; o.textContent = e.rotulo;
    $('especie').appendChild(o);
  }
  desenhaLista();
  desenhaCampos();

  $('filtro').addEventListener('input', desenhaLista);
  $('apenas-selecionadas').addEventListener('click', () => {
    apenasSelecionadas = !apenasSelecionadas;
    desenhaLista();
  });
  $('gerar').addEventListener('click', gerar);
  for (const id of ['especie', 'titulo', 'judicial'])
    $(id).addEventListener('input', pedePrevia);
  $('judicial').addEventListener('change', pedePrevia);
  atualizaPrevia();
  $('modal-fechar').addEventListener('click', () => $('modal').hidden = true);
}

function desenhaLista() {
  const termo = $('filtro').value.trim().toLowerCase();
  const lista = $('lista');
  lista.textContent = '';

  const visiveis = CAT.exigencias.filter(e =>
    (!apenasSelecionadas || selecionadas.has(e.id)) &&
    (!termo || (e.rotulo + ' ' + e.assunto + ' ' + e.defeito).toLowerCase().includes(termo)));

  atualizaAlternador();

  if (!visiveis.length) {
    lista.innerHTML = '<div class="vazio">'
      + (apenasSelecionadas && !selecionadas.size ? 'Nenhuma pendência selecionada ainda.'
         : apenasSelecionadas ? 'Nenhuma das selecionadas atende a esse termo.'
         : 'Nenhuma pendência com esse termo.')
      + '</div>';
    return;
  }

  for (const e of visiveis) {
    const div = document.createElement('label');
    div.className = 'item' + (selecionadas.has(e.id) ? ' marcado' : '');

    const cx = document.createElement('input');
    cx.type = 'checkbox';
    cx.checked = selecionadas.has(e.id);
    cx.addEventListener('change', () => {
      cx.checked ? selecionadas.add(e.id) : selecionadas.delete(e.id);
      div.classList.toggle('marcado', cx.checked);
      desenhaCampos();
      atualizaContagem();
      pedePrevia();
      if (apenasSelecionadas && !cx.checked) desenhaLista();
      else atualizaAlternador();
    });

    const texto = document.createElement('div');
    const nome = document.createElement('div');
    nome.className = 'nome';
    nome.textContent = e.rotulo;
    const meta = document.createElement('div');
    meta.className = 'meta';
    if (!e.revisado) {
      const p = document.createElement('span');
      p.className = 'pilula';
      p.textContent = 'não revisada';
      meta.append(p);
    }
    if (!e.fundamentos && !e.precedentes) {
      const p = document.createElement('span');
      p.className = 'pilula';
      p.textContent = 'sem lei citada';
      meta.append(p);
    }
    if (e.impossibilidade) {
      const p = document.createElement('span');
      p.className = 'pilula impossivel';
      p.textContent = 'devolve o título';
      meta.append(p);
    }
    texto.append(nome);
    if (meta.childElementCount) texto.append(meta);
    div.append(cx, texto);
    lista.append(div);
  }
}

function atualizaAlternador() {
  const b = $('apenas-selecionadas');
  b.textContent = selecionadas.size
    ? `Apenas selecionadas (${selecionadas.size})`
    : 'Apenas selecionadas';
  b.classList.toggle('ligado', apenasSelecionadas);
  b.setAttribute('aria-pressed', String(apenasSelecionadas));
}

function desenhaCampos() {
  const alvo = $('campos');
  alvo.textContent = '';

  if (!selecionadas.size) {
    alvo.innerHTML = '<div class="vazio">Selecione as pendências ao lado.</div>';
    return;
  }

  for (const e of CAT.exigencias.filter(x => selecionadas.has(x.id))) {
    const g = document.createElement('div');
    g.className = 'grupo';
    const h = document.createElement('h3');
    h.textContent = e.rotulo;
    g.append(h);

    if (!e.campos.length) {
      const p = document.createElement('div');
      p.className = 'nada';
      p.textContent = 'Não pede nenhum dado.';
      g.append(p);
    }

    for (const c of e.campos) {
      const info = CAT.campos[c] || {};
      const exemplo = (e.exemplos && e.exemplos[c]) || info.exemplo || '';
      const linha = document.createElement('div');
      linha.className = 'linha';

      const lab = document.createElement('label');
      lab.textContent = info.rotulo || c;
      // opcional de dois jeitos: campo com 'padrao', ou usado só dentro de
      // colchetes na exigência — aí o trecho inteiro some se ficar vazio
      const opcional = info.padrao || !(e.obrigatorios || []).includes(c);
      if (opcional) {
        const op = document.createElement('span');
        op.className = 'opcional';
        op.textContent = ' (opcional)';
        lab.append(op);
      }
      // campo com lista fechada vira <select>; os demais, caixa de texto
      const inp = document.createElement(info.opcoes ? 'select' : 'input');
      if (info.opcoes) {
        const vazio = document.createElement('option');
        vazio.value = ''; vazio.textContent = opcional ? '— não informar —' : '— escolha —';
        inp.append(vazio);
        for (const o of info.opcoes) {
          const op = document.createElement('option');
          op.value = o; op.textContent = o;
          inp.append(op);
        }
      } else {
        inp.placeholder = exemplo;
      }
      inp.value = valores.get(e.id + '|' + c) || '';
      inp.title = info.padrao ? `Em branco, a nota diz: "${info.padrao}"`
                              : (opcional ? 'Em branco, o trecho não entra na nota.' : '');
      inp.addEventListener(info.opcoes ? 'change' : 'input', () => {
        valores.set(e.id + '|' + c, inp.value);
        pedePrevia();
      });

      linha.append(lab, inp);
      g.append(linha);
    }
    alvo.append(g);
  }
}

// A prévia é refeita no servidor, que é quem sabe montar a nota. O atraso
// evita uma requisição por tecla digitada.
let relogioPrevia;
function pedePrevia() {
  clearTimeout(relogioPrevia);
  relogioPrevia = setTimeout(atualizaPrevia, 350);
}

function montaItens() {
  return [...selecionadas].map(id => {
    const e = CAT.exigencias.find(x => x.id === id);
    const v = {};
    for (const c of e.campos) v[c] = (valores.get(id + '|' + c) || '').trim();
    return { exigencia: id, valores: v };
  });
}

async function atualizaPrevia() {
  const alvo = $('previa');
  if (!selecionadas.size) {
    alvo.innerHTML = '<div class="vazio">A nota aparece aqui conforme você seleciona as pendências.</div>';
    $('previa-aviso').textContent = '';
    return;
  }
  try {
    const res = await requisicao('/previa', {
    method: 'POST',
    body: JSON.stringify({
      especie: $('especie').value,
      titulo: $('titulo').value.trim(),
      judicial: $('judicial').checked,
      itens: montaItens(),
    }),
    });
    alvo.innerHTML = res.html || '<div class="vazio">A prévia ainda não possui conteúdo.</div>';
    $('previa-aviso').textContent = res.faltando && res.faltando.length
      ? `falta preencher: ${res.faltando.join(', ')}`
      : '';
  } catch (erro) {
    alvo.innerHTML = `<div class="vazio">${escaparHtml(erro.message)}</div>`;
    $('previa-aviso').textContent = '';
  }
}

function atualizaContagem() {
  const n = selecionadas.size;
  const naoRevisadas = CAT.exigencias.filter(e => selecionadas.has(e.id) && !e.revisado).length;
  $('contagem').textContent = n
    ? `${n} pendência${n > 1 ? 's' : ''} selecionada${n > 1 ? 's' : ''}`
    : 'nenhuma pendência selecionada';
  $('aviso').textContent = naoRevisadas
    ? `${naoRevisadas} com fundamentação ainda não revisada por registrador`
    : '';
}

function baixa(base64, nome) {
  const bytes = Uint8Array.from(atob(base64), c => c.charCodeAt(0));
  const url = URL.createObjectURL(new Blob([bytes],
    { type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' }));
  const a = document.createElement('a');
  a.href = url; a.download = nome;
  document.body.append(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
}

function avisa(titulo, html, caminho) {
  $('modal-titulo').textContent = titulo;
  $('modal-corpo').innerHTML = html;
  const b = $('modal-pasta');
  b.hidden = !caminho;
  b.onclick = null;
  $('modal').hidden = false;
}

async function gerar() {
  if (!selecionadas.size) return avisa('Nota vazia', '<p>Selecione ao menos uma pendência.</p>');
  if (!$('titulo').value.trim())
    return avisa('Falta o título', '<p>Informe o título apresentado — ele entra no preâmbulo.</p>');

  const itens = montaItens();

  $('gerar').disabled = true;
  try {
    const res = await requisicao('/gerar', {
      method: 'POST',
      body: JSON.stringify({
        especie: $('especie').value,
        titulo: $('titulo').value.trim(),
        protocolo: $('protocolo').value.trim(),
        judicial: $('judicial').checked,
        itens,
      }),
    });

    let html;
    if (res.conteudo) {
      // servidor sem disco: a nota volta embutida e o navegador a salva
      baixa(res.conteudo, res.arquivo);
      html = `<p>Nota gerada e baixada:</p><div class="caminho">${escaparHtml(res.arquivo)}</div>`;
    } else {
      html = `<p>Nota gravada em:</p><div class="caminho">${escaparHtml(res.caminho)}</div>`;
    }
    if (res.nao_revisadas.length) {
      html += '<p><strong>Fundamentação ainda não revisada por registrador:</strong></p><ul>'
            + res.nao_revisadas.map(x => `<li>${escaparHtml(x)}</li>`).join('') + '</ul>'
            + '<p>Confira os artigos citados antes de expedir.</p>';
    }
    avisa('Nota gerada', html, res.caminho);
  } catch (erro) {
    avisa('Não foi possível gerar', `<p>${escaparHtml(erro.message)}</p>`);
  } finally {
    $('gerar').disabled = false;
  }
}

iniciar().catch(erro => {
  $('lista').innerHTML = `<div class="vazio">${escaparHtml(erro.message)}</div>`;
  $('gerar').disabled = true;
});
