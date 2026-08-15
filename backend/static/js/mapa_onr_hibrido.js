(function integraAnaliseHibrida(global) {
  'use strict';

  const extratorLegado = global.ONR_EXTRATOR;
  if (!extratorLegado || typeof extratorLegado.extraiConfrontantes !== 'function') return;

  const extrairLegado = extratorLegado.extraiConfrontantes.bind(extratorLegado);
  let contexto = null;
  let confirmados = new Set();

  function normalizar(valor) {
    return String(valor || '').replace(/\s+/g, ' ').trim().toLocaleLowerCase('pt-BR');
  }

  function chave(item, indice) {
    return String(item.numero_matricula_confrontante || 'sem-matricula') + ':' + indice;
  }

  function confrontantesDoBloco(texto) {
    if (!contexto || contexto.modo !== 'hibrido') return null;
    const bloco = normalizar(texto);
    const encontrados = (contexto.confrontantes || []).filter((item) =>
      (item.evidencias || []).some((evidencia) => bloco.includes(normalizar(evidencia)))
    );
    if (!encontrados.length) return null;
    return encontrados.map((item) => ({
      numero_matricula_confrontante: item.numero_matricula_confrontante || null,
      nome_proprietario_confrontante:
        item.confianca === 'alta' ? item.nome_proprietario_confrontante || null : null,
      trecho: (item.evidencias || [])[0] || '',
    }));
  }

  extratorLegado.extraiConfrontantes = function extraiConfrontantesAeri(texto) {
    const resultadoAeri = confrontantesDoBloco(texto);
    return resultadoAeri === null ? extrairLegado(texto) : resultadoAeri;
  };

  function pendencias() {
    if (!contexto || contexto.modo !== 'hibrido') return [];
    return (contexto.confrontantes || [])
      .map((item, indice) => ({item, indice, chave: chave(item, indice)}))
      .filter(({item}) => Boolean(item.pendencia));
  }

  function instalarEstilos() {
    if (document.getElementById('aeri-mapa-estilos')) return;
    const estilo = document.createElement('style');
    estilo.id = 'aeri-mapa-estilos';
    estilo.textContent = `
      .aeri-revisao { margin: 16px 0; padding: 16px; border: 1px solid #e5a82e;
        border-radius: 10px; background: #fff9e9; color: #243247; }
      .aeri-revisao.ok { border-color: #49a56d; background: #effaf3; }
      .aeri-revisao h3 { margin: 0 0 6px; font-size: 15px; }
      .aeri-revisao > p { margin: 5px 0 12px; font-size: 13px; }
      .aeri-revisao-item { display: block; margin-top: 9px; padding: 10px;
        border: 1px solid rgba(36,50,71,.16); border-radius: 8px; background: #fff; }
      .aeri-revisao-item strong { display: block; margin-bottom: 4px; }
      .aeri-revisao-item small { display: block; margin: 3px 0; overflow-wrap: anywhere; }
      .aeri-revisao-item label { display: flex; gap: 8px; align-items: flex-start;
        margin-top: 8px; font-weight: 600; cursor: pointer; }
      .aeri-bloqueio { margin-top: 10px; color: #9b3a20; font-weight: 700; }
    `;
    document.head.appendChild(estilo);
  }

  function renderizarRevisao() {
    document.getElementById('aeri-revisao-confrontantes')?.remove();
    const alvo = document.getElementById('ficha-imovel');
    if (!alvo || !contexto || contexto.modo !== 'hibrido') return;

    const itens = pendencias();
    const painel = document.createElement('div');
    painel.id = 'aeri-revisao-confrontantes';
    painel.className = 'aeri-revisao' + (itens.length ? '' : ' ok');

    const titulo = document.createElement('h3');
    titulo.textContent = itens.length
      ? `Conferência de confrontantes (${itens.length})`
      : 'Confrontantes conferidos pelo AERI';
    painel.appendChild(titulo);

    const introducao = document.createElement('p');
    introducao.textContent = itens.length
      ? 'O texto não identifica com segurança o proprietário destes confrontantes. Confira a fonte antes de gerar o JSON.'
      : 'Os proprietários exportados possuem identificação explícita no texto registral.';
    painel.appendChild(introducao);

    for (const {item, chave: id} of itens) {
      const caixa = document.createElement('div');
      caixa.className = 'aeri-revisao-item';

      const cabecalho = document.createElement('strong');
      cabecalho.textContent = item.numero_matricula_confrontante
        ? `Matrícula confrontante ${item.numero_matricula_confrontante}`
        : 'Confrontante sem matrícula identificada';
      caixa.appendChild(cabecalho);

      const descricao = document.createElement('small');
      descricao.textContent = `Descrição: ${(item.descricoes_confrontacao || []).join(' / ') || 'não informada'}`;
      caixa.appendChild(descricao);

      const motivo = document.createElement('small');
      motivo.textContent = `Motivo: ${item.pendencia}`;
      caixa.appendChild(motivo);

      const rotulo = document.createElement('label');
      const check = document.createElement('input');
      check.type = 'checkbox';
      check.checked = confirmados.has(id);
      check.addEventListener('change', () => {
        if (check.checked) confirmados.add(id); else confirmados.delete(id);
        atualizarBloqueio(painel);
      });
      rotulo.append(check, document.createTextNode('Conferi; exportar somente a matrícula, sem atribuir proprietário.'));
      caixa.appendChild(rotulo);
      painel.appendChild(caixa);
    }

    const bloqueio = document.createElement('div');
    bloqueio.className = 'aeri-bloqueio';
    painel.appendChild(bloqueio);
    alvo.parentNode.insertBefore(painel, alvo);
    atualizarBloqueio(painel);
  }

  function atualizarBloqueio(painel) {
    const faltantes = pendencias().filter(({chave: id}) => !confirmados.has(id)).length;
    const aviso = painel.querySelector('.aeri-bloqueio');
    if (aviso) aviso.textContent = faltantes
      ? `A exportação está bloqueada até conferir ${faltantes} item(ns).`
      : 'Conferência concluída. O JSON pode ser gerado.';
    painel.classList.toggle('ok', faltantes === 0);
  }

  function limparContexto() {
    contexto = null;
    confirmados = new Set();
    document.getElementById('aeri-revisao-confrontantes')?.remove();
  }

  instalarEstilos();

  global.addEventListener('message', (evento) => {
    const mensagem = evento.data || {};
    if (mensagem.tipo === 'AERI_MAPA_ONR_LIMPAR') {
      limparContexto();
      return;
    }
    if (mensagem.tipo !== 'AERI_MAPA_ONR_MATRICULA') return;
    contexto = mensagem.contextoAeri || null;
    confirmados = new Set();
    queueMicrotask(renderizarRevisao);
  });

  for (const id of ['btn-ler', 'btn-exemplo', 'btn-exemplo-urbano']) {
    document.getElementById(id)?.addEventListener('click', limparContexto, true);
  }

  document.getElementById('btn-gerar')?.addEventListener('click', (evento) => {
    const faltantes = pendencias().filter(({chave: id}) => !confirmados.has(id));
    if (!faltantes.length) return;
    evento.preventDefault();
    evento.stopImmediatePropagation();
    renderizarRevisao();
    const painel = document.getElementById('aeri-revisao-confrontantes');
    painel?.scrollIntoView({behavior: 'smooth', block: 'center'});
  }, true);

  global.AERI_MAPA_ONR_HIBRIDO = {
    normalizar,
    confrontantesDoBloco,
    limparContexto,
  };
})(typeof window !== 'undefined' ? window : globalThis);
