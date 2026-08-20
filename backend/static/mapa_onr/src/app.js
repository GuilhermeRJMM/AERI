/**
 * Interface do conversor: matricula (texto) -> JSON de importacao ONR.
 *
 * Fluxo: 1) colar a matricula inteira -> 2) escolher os atos a exportar ->
 * 3) revisar dados do imovel e das partes (o que o parser achou vem preenchido,
 * com o trecho de origem) -> 4) validar contra o schema oficial -> 5) exportar.
 *
 * A matricula e sempre lida por inteiro, mesmo quando so um ato sera exportado:
 * e a leitura completa que da area, CAR/CCIR/CIB e regime de bens vigentes.
 */
(function (global) {
  'use strict';

  const P = global.ONR_PARSER;
  const B = global.ONR_BUILDER;
  const V = global.ONR_VALIDATOR;
  const E = global.ONR_ENUMS;

  const estado = {
    atos: [],          // atos separados do texto
    selecionados: new Set(),
    fichaImovel: {},   // dados de nivel imovel (compartilhados)
    fichasAto: {},     // numero do ato -> {campos, pessoas}
    resultado: null,
  };

  const $ = (sel) => document.querySelector(sel);
  const el = (tag, props, filhos) => {
    const n = document.createElement(tag);
    Object.assign(n, props || {});
    for (const f of filhos || []) n.appendChild(typeof f === 'string' ? document.createTextNode(f) : f);
    return n;
  };

  function selectEnum(nome, valor, onChange, permiteVazio) {
    const s = el('select');
    if (permiteVazio !== false) s.appendChild(el('option', { value: '', textContent: '-' }));
    for (const o of E.opcoes(nome)) {
      s.appendChild(el('option', { value: String(o.valor), textContent: o.valor + ' - ' + o.rotulo }));
    }
    s.value = valor === null || valor === undefined ? '' : String(valor);
    s.addEventListener('change', () => onChange(s.value === '' ? null : +s.value));
    return s;
  }

  function campoTexto(valor, onChange, placeholder) {
    const i = el('input', { type: 'text', value: valor == null ? '' : String(valor), placeholder: placeholder || '' });
    i.addEventListener('input', () => onChange(i.value === '' ? null : i.value));
    return i;
  }

  function campoBool(valor, onChange) {
    const s = el('select');
    s.appendChild(el('option', { value: '', textContent: '-' }));
    s.appendChild(el('option', { value: 'true', textContent: 'Sim' }));
    s.appendChild(el('option', { value: 'false', textContent: 'Nao' }));
    s.value = valor === true ? 'true' : valor === false ? 'false' : '';
    s.addEventListener('change', () => onChange(s.value === '' ? null : s.value === 'true'));
    return s;
  }

  function linha(rotulo, controle, dica) {
    const d = el('div', { className: 'campo' }, [el('label', { textContent: rotulo }), controle]);
    if (dica) d.appendChild(el('small', { className: 'evidencia', textContent: dica }));
    return d;
  }

  // ------------------------------------------------------------- etapa 1: ler

  const X = global.ONR_EXTRATOR;

  /**
   * Apura o estado vigente do imovel varrendo o documento inteiro em ordem.
   * Regra: para cada campo vale o valor ROTULADO mais recente. Para a area,
   * vale o candidato de maior prioridade (total/remanescente > area do CAR >
   * area de origem) e, dentro da mesma prioridade, o mais recente.
   */
  /** 'rural' ou 'urbano', conforme o seletor da tela. */
  function tipoAtual() {
    const s = $('#tipo-imovel');
    return s && s.value === 'urbano' ? 'urbano' : 'rural';
  }

  function apuraVigente(blocos, municipioServentia) {
    const urbano = tipoAtual() === 'urbano';
    const vigente = { campos: {}, areaEscolhida: null, candidatosArea: [], confrontantes: [],
      historico: [], endereco: {}, pessoas: {}, proprietarios: [], fonteTitularidade: null,
      // Retrato da titularidade DEPOIS de cada bloco. Um ato antigo tem de
      // receber quem era dono na epoca dele, nao quem e dono hoje: numa
      // matricula onde a ultima transmissao e um inventario, o obito averbado
      // antes dela estava sendo vinculado aos herdeiros, que so viraram donos
      // depois. A chave e o rotulo do bloco ('abertura', 'AV.01', ...).
      snapshots: {}, urbano };
    const anota = (campo, achado, origem) => {
      if (!achado) return;
      vigente.campos[campo] = { valor: achado.valor, trecho: achado.trecho, rotulo: achado.rotulo, ato: origem };
      vigente.historico.push({ ato: origem, campo, valor: achado.valor, rotulo: achado.rotulo });
    };

    for (const b of blocos) {
      const cad = X.extraiCadastros(b.texto);
      const campos = urbano
        ? ['cib', 'cif', 'cep', 'nome_imovel']
        // "codigo_incra_incompleto" e "car_suspeito" nao viram valor de campo:
        // sao achados que a tela mostra para conferencia.
        : ['car', 'cib', 'nirf', 'ccir', 'cod_sncr', 'codigo_incra', 'cep', 'nome_imovel',
          'codigo_incra_incompleto', 'car_suspeito'];
      for (const k of campos) anota(k, cad[k], b.rotulo);

      const geo = X.extraiGeo(b.texto);
      for (const k of ['georreferenciamento', 'certificacao_incra', 'sistema_referencia',
        'sistema_coordenadas', 'centroide']) anota(k, geo[k], b.rotulo);

      // Endereco, quadra/lote e area construida SO valem da abertura ou de ato
      // que altera o imovel. Num ato de transmissao, "Quadra 03, Lote 16" e o
      // endereco RESIDENCIAL das partes, nao a descricao do imovel.
      const descreveImovel = b.rotulo === 'abertura'
        || (X.classificaAto(b.texto).ato || {}).valor === 5;

      // Area: no urbano vale a area do terreno em m2 (a construida fica de fora).
      const areas = urbano ? X.candidatosAreaUrbana(b.texto)
        : X.candidatosArea(b.texto, { descricao: descreveImovel });
      for (const cand of areas) {
        vigente.candidatosArea.push(Object.assign({ ato: b.rotulo }, cand));
      }
      if (urbano && descreveImovel) {
        anota('area_construida', X.extraiAreaConstruida(b.texto), b.rotulo);
        const end = X.extraiEndereco(b.texto);
        for (const k of ['tipo_logradouro', 'logradouro', 'numero_logradouro', 'bairro', 'complemento']) {
          if (end[k]) {
            vigente.endereco[k] = end[k].valor;
            anota('endereco_' + k, end[k], b.rotulo);
          }
        }
      }

      // Averbacao de mudanca de nome de rua: "o logradouro publico que ate entao
      // denominava-se 'Avenida H' [...] passou a denominar-se 'Avenida Tenente
      // Santana'". Vale o nome NOVO - o da abertura ja nao existe.
      if (urbano) {
        const novo = X.extraiNovoLogradouro(b.texto);
        if (novo) {
          vigente.endereco.logradouro = novo.valor;
          anota('endereco_logradouro', novo, b.rotulo);
          const tipo = X.tipoDeLogradouro(novo.valor);
          if (tipo) {
            vigente.endereco.tipo_logradouro = tipo.valor;
            anota('endereco_tipo_logradouro', tipo, b.rotulo);
          }
        }
      }

      const confs = X.extraiConfrontantes(b.texto);
      if (confs.length) vigente.confrontantes = confs.map((c) => Object.assign({ ato: b.rotulo }, c));

      // --------------------------------------------- titularidade vigente
      // Duas fontes, em ordem de autoridade:
      //  1) tabela de indicacao de titularidade (retrato ex-officio) - SUBSTITUI
      //  2) adquirentes de um ato de transmissao - somam/atualizam
      const dataBloco = (X.extraiDataAto(b.texto) || {}).valor || null;

      // A abertura declara "PROPRIETARIO(S): ..." - e a titularidade inicial.
      // Sem isto, matricula aberta por desmembramento (que so tem averbacoes
      // cadastrais depois) ficava sem dono nenhum.
      if (b.rotulo === 'abertura') {
        const donosIniciais = X.extraiPessoas(b.texto)
          .filter((p) => p.cpf_cnpj && !p.representante_legal
            && (p.relacao_juridica === 1 || /propriet/i.test(p.papel || '')));
        if (donosIniciais.length) {
          vigente.proprietarios = donosIniciais.map((p) => ({
            nome_completo: p.nome_completo,
            cpf_cnpj: p.cpf_cnpj,
            percentual: p.percentual,
            desde: dataBloco,
            fonte: 'abertura (PROPRIETARIO)',
            trecho: p.evidencia,
          }));
          vigente.fonteTitularidade = 'abertura (PROPRIETARIO)';
        }
      }

      const tabela = X.extraiTitularidade(b.texto);
      if (tabela.length) {
        vigente.proprietarios = tabela.map((t) => ({
          nome_completo: t.nome_completo,
          cpf_cnpj: null, // casado com os CPF do documento no final
          percentual: t.percentual,
          desde: dataBloco,
          fonte: b.rotulo + ' (tabela de titularidade)',
          trecho: t.trecho,
        }));
        vigente.fonteTitularidade = b.rotulo + ' (tabela de titularidade)';
      } else if ((X.classificaAto(b.texto).ato || {}).valor === 4) {
        const adquirentes = X.extraiPessoas(b.texto)
          .filter((p) => p.condicao_parte === 2 && !p.representante_legal);
        if (adquirentes.length) {
          const alienantes = new Set(X.extraiPessoas(b.texto)
            .filter((p) => p.condicao_parte === 1).map((p) => p.cpf_cnpj));
          // "coube EXCLUSIVAMENTE aos condominos: X e Y" - o ato diz, com essa
          // palavra, que dali em diante os donos sao so esses. Sem isto o
          // condomino que saiu ficava na titularidade para sempre, porque a
          // divisao amigavel o cita sem repetir o CPF ("acima qualificados") e
          // ele nunca entrava na lista de alienantes.
          const exclusivo = /coube\s+exclusivamente/i.test(b.texto);
          const lista = (exclusivo ? [] : (vigente.proprietarios || []))
            .filter((p) => !alienantes.has(p.cpf_cnpj))
            .concat(adquirentes.map((p) => ({
              nome_completo: p.nome_completo,
              cpf_cnpj: p.cpf_cnpj,
              percentual: p.percentual,
              desde: dataBloco,
              fonte: b.rotulo + ' (adquirente)',
              trecho: p.evidencia,
            })));
          // Quem adquire em mais de um ato aparecia uma vez por ato, com o
          // percentual de cada um deles ("Vera Lucia 20%, 80% e 50%", mesmo CPF).
          // Vale a entrada mais recente: e ela que retrata a titularidade de hoje.
          const vistosCpf = new Set();
          const semRepetir = [];
          for (let i = lista.length - 1; i >= 0; i--) {
            const p = lista[i];
            if (p.cpf_cnpj) {
              if (vistosCpf.has(p.cpf_cnpj)) continue;
              vistosCpf.add(p.cpf_cnpj);
            }
            semRepetir.unshift(p);
          }
          vigente.proprietarios = semRepetir;
          vigente.fonteTitularidade = b.rotulo
            + (exclusivo ? ' (coube exclusivamente a)' : ' (adquirente)');
        }
      }

      // Estado civil e regime de bens por pessoa: o ato mais recente que DIZ
      // vence, e quem nao repete herda. E o que permite completar um ato que so
      // escreve "casado" sem dizer o regime.
      for (const p of X.extraiPessoas(b.texto)) {
        if (!p.cpf_cnpj) continue;
        const anterior = vigente.pessoas[p.cpf_cnpj] || {};
        // So entra no historico o regime DECLARADO. Regime presumido pela lei
        // da epoca nao pode virar "o que a matricula diz" para os outros atos.
        const declarou = p.regime_bens != null && !p.regime_presumido;
        vigente.pessoas[p.cpf_cnpj] = {
          nome_completo: p.nome_completo || anterior.nome_completo || null,
          estado_civil: p.estado_civil != null ? p.estado_civil : (anterior.estado_civil ?? null),
          regime_bens: declarou ? p.regime_bens : (anterior.regime_bens ?? null),
          ato_regime: declarou ? b.rotulo : (anterior.ato_regime || null),
          // O regime PRESUMIDO fica guardado a parte: nao vale como "o que a
          // matricula diz", mas serve de ultimo recurso para o ato cadastral
          // que so recebeu o proprietario vigente - senao ele sai sem regime e
          // o arquivo e recusado por um dado que o documento ate sugere.
          regime_presumido_bens: p.regime_bens != null && p.regime_presumido
            ? p.regime_bens : (anterior.regime_presumido_bens ?? null),
          ato_regime_presumido: p.regime_bens != null && p.regime_presumido
            ? b.rotulo : (anterior.ato_regime_presumido || null),
          ato_estado_civil: p.estado_civil != null ? b.rotulo : (anterior.ato_estado_civil || null),
        };
      }

      // Averbacao de casamento: o proprietario continua "solteiro" no historico,
      // porque o ato o nomeia sem requalificar (nem repete o CPF). O proprio ato
      // diz que ele se casou - e e disso que os atos seguintes precisam.
      if (/CASAMENTO|casou-se/i.test(b.texto)) {
        const rb = X._internos.regimeBensDe(b.texto, dataBloco) || {};
        for (const cpf of Object.keys(vigente.pessoas)) {
          const p = vigente.pessoas[cpf];
          if (!p.nome_completo) continue;
          if (b.texto.indexOf(p.nome_completo) < 0) continue;
          p.estado_civil = 2;
          p.ato_estado_civil = b.rotulo + ' (casamento averbado)';
          if (rb.regime_bens != null && !rb.presumido) {
            p.regime_bens = rb.regime_bens;
            p.ato_regime = b.rotulo + ' (casamento averbado)';
          }
        }
      }

      vigente.snapshots[b.rotulo] = {
        proprietarios: (vigente.proprietarios || []).slice(),
        fonte: vigente.fonteTitularidade,
      };
    }

    // Ordem dos blocos ja e cronologica: o ultimo de maior peso ganha.
    let melhor = null;
    for (const cand of vigente.candidatosArea) {
      if (!melhor || cand.peso >= melhor.peso) melhor = cand;
    }
    vigente.areaEscolhida = melhor;

    // CPF antigo de 9 digitos: se o MESMO numero aparece completo em outro ato,
    // vale o completo. E o caso do 004.307.301 da abertura, que so ganha os
    // digitos verificadores (-87) nos atos posteriores.
    vigente.completaCpf = {};
    const bases = {};
    for (const cpf of Object.keys(vigente.pessoas)) {
      if (cpf.length === 11) bases[cpf.slice(0, 9)] = cpf;
    }
    for (const cpf of Object.keys(vigente.pessoas)) {
      if (cpf.length === 9 && bases[cpf]) vigente.completaCpf[cpf] = bases[cpf];
    }

    // A tabela de titularidade nao traz CPF: casa pelo nome com as pessoas que
    // aparecem qualificadas em algum ato, e traz junto estado civil e regime.
    const porNome = {};
    for (const cpf of Object.keys(vigente.pessoas)) {
      const p = vigente.pessoas[cpf];
      if (p.nome_completo) porNome[X.chaveNome(p.nome_completo)] = Object.assign({ cpf_cnpj: cpf }, p);
    }
    const casaPeloNome = (lista) => (lista || []).map((prop) => {
      if (prop.cpf_cnpj) return prop;
      const achado = porNome[X.chaveNome(prop.nome_completo)];
      if (!achado) return prop;
      return Object.assign({}, prop, {
        cpf_cnpj: achado.cpf_cnpj,
        estado_civil: achado.estado_civil,
        regime_bens: achado.regime_bens,
        casadoPeloNome: true,
      });
    });
    vigente.proprietarios = casaPeloNome(vigente.proprietarios);
    // Os retratos por ato passam pelo mesmo casamento nome -> CPF: eles sao
    // copias feitas antes desta etapa.
    for (const rotulo of Object.keys(vigente.snapshots)) {
      vigente.snapshots[rotulo].proprietarios = casaPeloNome(vigente.snapshots[rotulo].proprietarios);
    }

    const mun = X.extraiMunicipio(blocos.map((b) => b.texto).join(' '), municipioServentia);
    if (mun) vigente.municipio = mun.valor;
    return vigente;
  }

  /**
   * Atos cadastrais (CAR, CEP, CCIR/CIB, obito, clausulas...) nao tem parte
   * propria no texto, mas o layout do ONR exige `dados_pessoa`. Quem responde
   * por eles e o PROPRIETARIO vigente - e e isso que entra aqui, com a origem
   * declarada, em vez de o ato ser recusado por falta de pessoa.
   */
  function proprietariosComoPartes(vigente, dataAto, rotuloAto) {
    // Titularidade COMO ESTAVA quando o ato foi praticado, e nao a de hoje.
    const retrato = rotuloAto && vigente.snapshots ? vigente.snapshots[rotuloAto] : null;
    const donos = retrato ? retrato.proprietarios : vigente.proprietarios;
    return (donos || []).map((prop) => {
      // Estado civil e regime vem do historico da propria pessoa, apurado em
      // qualquer ato do documento - o ato cadastral nunca qualifica ninguem.
      const hist = (vigente.pessoas || {})[prop.cpf_cnpj] || {};
      const ehPJ = prop.cpf_cnpj && prop.cpf_cnpj.length === 14;
      const regimeDito = prop.regime_bens != null ? prop.regime_bens
        : (hist.regime_bens != null ? hist.regime_bens : null);
      const usaPresumido = regimeDito == null && hist.regime_presumido_bens != null;
      return {
      nome_completo: prop.nome_completo,
      cpf_cnpj: prop.cpf_cnpj,
      condicao_parte: null,        // nao e alienante nem adquirente neste ato
      relacao_juridica: 1,         // proprietario
      estado_civil: prop.estado_civil != null ? prop.estado_civil
        : (hist.estado_civil != null ? hist.estado_civil : (ehPJ ? 7 : null)),
      regime_bens: usaPresumido ? hist.regime_presumido_bens : regimeDito,
      regime_presumido: usaPresumido,
      evidencia_regime: usaPresumido
        ? 'regime presumido no ato ' + (hist.ato_regime_presumido || '?')
        : (hist.ato_regime ? 'regime declarado no ato ' + hist.ato_regime : null),
      percentual: prop.percentual,
      estrangeiro: false,
      data_inicio_rel_juridica: prop.desde || dataAto,
      papel: 'proprietario vigente',
      vinculadoAutomaticamente: true,
      evidencia: 'titularidade apurada em ' + (prop.fonte || '?')
        + (prop.trecho ? ' - ' + prop.trecho : ''),
      };
    });
  }

  function lerMatricula() {
    const texto = $('#texto').value;
    // Ler uma matricula recomeca do zero: a ficha anterior e de OUTRO imovel, e
    // dado remanescente (nome do imovel, CAR, area) vazaria para o novo arquivo.
    estado.fichaImovel = {};
    estado.geoAssumido = false;
    estado.cnmCalculado = null;
    estado.numeroAssumido = false;
    estado.tipoLogradouroAssumido = false;
    estado.situacaoEncerrada = null;
    estado.certAssumida = false;
    estado.cifAssumido = false;
    estado.cortados = [];
    const doc = P.separaDocumento(texto);
    estado.atos = doc.atos;
    estado.preambulo = doc.preambulo;
    estado.selecionados = new Set(estado.atos.map((a) => a.numero));
    estado.fichasAto = {};
    estado.resultado = null;

    // Estado vigente: varre TODOS os atos (nao apenas os escolhidos), comecando
    // pela abertura - area, CCIR e COD_SNCR costumam existir so ali.
    const blocos = [];
    if (doc.preambulo) blocos.push({ rotulo: 'abertura', texto: doc.preambulo });
    for (const a of estado.atos) {
      // A abertura ja entrou como bloco: nao contar duas vezes.
      if (a.ehAbertura) continue;
      blocos.push({ rotulo: (a.tipo === 1 ? 'R.' : 'AV.') + a.numero, texto: a.texto });
    }
    const vigente = apuraVigente(blocos, $('#municipio').value);
    estado.vigente = vigente;
    estado.geoAssumido = false;

    // ------------------------------------------- ficha do imovel, preenchida
    const f = estado.fichaImovel;
    const v = (campo) => (vigente.campos[campo] ? vigente.campos[campo].valor : null);
    const abertura = X.extraiAbertura(doc.preambulo || (estado.atos[0] || {}).texto || '');

    const urbano = tipoAtual() === 'urbano';
    f.tipo_matricula_transcricao = f.tipo_matricula_transcricao ?? 1;
    if (urbano) f.contexto_urbano = f.contexto_urbano ?? 1;
    else f.contexto_rural = f.contexto_rural ?? 1;
    // Matricula encerrada (desmembramento total, unificacao, transporte) diz isso
    // no proprio ato: "Fica desta forma ENCERRADA A PRESENTE MATRICULA". Sem ler
    // essa frase o arquivo sai declarando "1 - Ativa" um imovel que nao existe
    // mais, e o erro nao aparece em lugar nenhum.
    const textoTodo = (doc.preambulo || '') + ' ' + estado.atos.map((a) => a.texto).join(' ');
    const mEncerrada = textoTodo.match(/ENCERRADA?\s+(?:a\s+)?(?:presente|esta)\s+MATR[ÍI]CULA|MATR[ÍI]CULA\s+(?:fica\s+)?ENCERRADA/i);
    if (f.situacao == null && mEncerrada) {
      f.situacao = '4';
      estado.situacaoEncerrada = mEncerrada[0];
    }
    f.situacao = f.situacao ?? '1';
    if (abertura.numero_matricula) {
      f.numero_matricula = abertura.numero_matricula.valor;
    } else {
      // Matriculas abertas por desmembramento comecam direto em "IMOVEL:", sem a
      // linha "MATRICULA N" - o numero fica so no cabecalho dos atos ("AV.01-12.345").
      const doCabecalho = (estado.atos.find((a) => a.matricula) || {}).matricula;
      if (doCabecalho) {
        f.numero_matricula = doCabecalho;
        estado.matriculaDoCabecalho = true;
      } else if (estado.numeroConsultado && texto.trim() === (estado.textoConsultado || '').trim()) {
        // Recem-aberta por desmembramento: comeca em "IMOVEL:" e tem so o ato
        // de abertura, entao nao ha "MATRICULA N" nem cabecalho "AV.01-N" de
        // onde tirar o numero. Quando o texto na tela ainda e o que veio da
        // consulta feita no AERI, o numero pedido a Tri7 e a fonte certa.
        f.numero_matricula = estado.numeroConsultado;
        estado.matriculaDaConsulta = true;
      }
    }
    if (abertura.data_matricula) f.data_matricula = abertura.data_matricula.valor;

    // CNM: nao consta na matricula, mas e deduzivel do CNS + numero (ISO 7064
    // MOD 97-10). Calculado aqui e conferido na tela ao lado do campo.
    const DOC = global.ONR_DOC;
    if (DOC && f.numero_matricula) {
      const calculado = DOC.montaCnm($('#cns').value, f.numero_matricula, 2);
      if (calculado) {
        f.cnm = f.cnm || calculado;
        estado.cnmCalculado = calculado;
      }
    }
    // codigo_incra: o numero da certificacao do INCRA, exigido pela regra sempre
    // que certificacao_incra = true. Vem da abertura ("certificacao n.º <uuid>")
    // e vale para o documento inteiro, como os demais cadastros.
    for (const k of urbano ? ['cif', 'cib', 'nome_imovel']
      : ['car', 'ccir', 'cod_sncr', 'codigo_incra', 'cib', 'nome_imovel']) {
      if (v(k)) f[k] = v(k);
    }
    // Imovel urbano sem designacao cadastral na Prefeitura: o CIF e exigido nos
    // atos a partir de 02/12/2025 e nao ha o que ler. Decisao da serventia
    // (17/08/2026): vai "0". Fica dito na tela, para o caso de o numero existir
    // no cadastro da Prefeitura e ainda nao ter sido averbado.
    if (urbano && !f.cif) {
      f.cif = '0';
      estado.cifAssumido = true;
    }
    if (v('nome_imovel')) f.imovel_possui_nome = true;
    if (v('georreferenciamento') !== null) {
      f.georreferenciamento = v('georreferenciamento');
    } else if (f.georreferenciamento == null) {
      // O campo e sempre obrigatorio. Sem nenhuma descricao georreferenciada no
      // documento inteiro, `false` e a leitura honesta - e fica dito na tela que
      // foi assumido, para conferencia.
      f.georreferenciamento = false;
      estado.geoAssumido = true;
    }
    if (v('certificacao_incra') !== null) {
      f.certificacao_incra = v('certificacao_incra');
    } else if (f.certificacao_incra == null) {
      // Campo sempre obrigatorio no rural. Nenhum ato do documento afirma
      // certificacao do INCRA - e "false" e a leitura honesta, dita na tela.
      f.certificacao_incra = false;
      estado.certAssumida = true;
    }
    if (v('sistema_referencia')) f.sistema_referencia = v('sistema_referencia');
    if (v('sistema_coordenadas')) f.sistema_coordenadas = v('sistema_coordenadas');
    if (vigente.areaEscolhida) f.area_terreno_total = vigente.areaEscolhida.valor;

    const end = (f.dados_imovel && f.dados_imovel[0]) || {};
    if (v('cep')) end.cep = v('cep');
    if (vigente.municipio) {
      end.cod_ibge_municipio = end.cod_ibge_municipio || vigente.municipio.cod_ibge_municipio;
      end.uf = end.uf || vigente.municipio.uf;
    }
    if (urbano) {
      // O schema urbano exige o endereco completo, nao so o municipio.
      for (const k of ['tipo_logradouro', 'logradouro', 'numero_logradouro', 'bairro', 'complemento']) {
        if (vigente.endereco[k] != null) end[k] = vigente.endereco[k];
      }
      if (vigente.areaEscolhida) end.area_m2 = vigente.areaEscolhida.valor.valor;

      // Terreno sem numero na rua e comum (lote ainda sem edificacao). O schema
      // exige o campo, e a convencao registral para isso e "S/N".
      if (end.logradouro && !end.numero_logradouro) {
        end.numero_logradouro = 'S/N';
        estado.numeroAssumido = true;
      }
      // Limite de tamanho do schema: um caractere a mais reprova o arquivo
      // inteiro. Corta na ultima palavra que couber, e diz na tela que cortou -
      // um nome de bairro cortado ainda identifica o lugar; vazio, nao.
      estado.cortados = [];
      for (const [k, limite] of [['logradouro', 150], ['bairro', 50], ['complemento', 100]]) {
        if (typeof end[k] === 'string' && end[k].length > limite) {
          const antes = end[k];
          end[k] = X.cortaEm(antes, limite);
          estado.cortados.push({ campo: k, limite, antes, depois: end[k] });
        }
      }

      // O tipo do logradouro pode nao estar no glossario ("Rua 06" esta; "Quadra
      // 11" nao). Sem ele o arquivo e reprovado - 177 e "Nao Especificado".
      if (end.logradouro && end.tipo_logradouro == null) {
        end.tipo_logradouro = 177;
        estado.tipoLogradouroAssumido = true;
      }
    }
    f.dados_imovel = [end];
    f.dados_confrontantes = vigente.confrontantes.map((c) => ({
      numero_matricula_confrontante: c.numero_matricula_confrontante,
      nome_proprietario_confrontante: c.nome_proprietario_confrontante,
    }));

    // -------------------------------------------------- ficha de cada ato
    estado.correcoes = [];
    for (const a of estado.atos) {
      const e = X.extraiAto(a.texto);
      const pega = (x) => (x ? x.valor : null);
      const rotuloAto = a.ehAbertura ? 'Abertura' : (a.tipo === 1 ? 'R.' : 'AV.') + a.numero;
      estado.fichasAto[a.numero] = {
        ehAbertura: !!a.ehAbertura,
        numero_ato: a.numero,
        tipo_ato: a.tipo,
        // Na abertura a data nao esta no cabecalho e sim no fecho ("Morrinhos-GO,
        // 12 de agosto de 2026") ou no protocolo - a mesma regra da abertura da
        // matricula.
        data_ato: pega(e.data_ato)
          || (a.ehAbertura ? pega(X.extraiAbertura(a.texto).data_matricula) : null),
        // A abertura e sempre "1: Abertura de matricula", independentemente do
        // que o texto da descricao mencione.
        ato: a.ehAbertura ? 1 : pega(e.ato),
        alteracao_titularidade: a.ehAbertura ? null : pega(e.alteracao_titularidade),
        alteracao_imovel: a.ehAbertura ? null : pega(e.alteracao_imovel),
        valor_transacao: pega(e.valor_transacao),
        valor_imposto: pega(e.valor_imposto),
        base_calculo_itbi: pega(e.base_calculo_itbi),
        protocolo_prenotacao: pega(e.protocolo_prenotacao),
        data_protocolo_prenotacao: pega(e.data_protocolo_prenotacao),
        // Quem apenas representa a PJ nao e parte: vai para representante legal.
        representantes: e.pessoas.filter((p) => p.representante_legal),
        pessoas: e.pessoas.filter((p) => !p.representante_legal).map((p) => {
          // Completa com o que outros atos disseram sobre a mesma pessoa.
          const hist = (vigente.pessoas || {})[p.cpf_cnpj] || {};
          // Regime declarado em qualquer ato vence o presumido pela lei da epoca:
          // o casal proprietario e "comunhao universal" pelos R-12/R-32/R-40, mesmo
          // que o R-15 e o R-26 digam apenas "casados".
          const herdouRegime = (p.regime_bens == null || p.regime_presumido) && hist.regime_bens != null;
          const herdouEstado = p.estado_civil == null && hist.estado_civil != null;
          return {
          nome_completo: p.nome_completo,
          cpf_cnpj: p.cpf_cnpj,
          condicao_parte: p.condicao_parte,
          relacao_juridica: p.relacao_juridica,
          estado_civil: herdouEstado ? hist.estado_civil : p.estado_civil,
          regime_bens: herdouRegime ? hist.regime_bens : p.regime_bens,
          herdado: (herdouRegime ? 'regime de bens do ato ' + hist.ato_regime : '')
            + (herdouRegime && herdouEstado ? '; ' : '')
            + (herdouEstado ? 'estado civil do ato ' + hist.ato_estado_civil : ''),
          regime_ambiguo: p.regime_ambiguo && !herdouRegime,
          regime_presumido: p.regime_presumido && !herdouRegime,
          evidencia_regime: p.evidencia_regime,
          percentual: p.percentual,
          estrangeiro: p.estrangeiro,
          // A data de inicio da relacao juridica e a data do proprio ato.
          data_inicio_rel_juridica: p.condicao_parte === 2 || p.relacao_juridica ? pega(e.data_ato) : null,
          papel: p.papel,
          conjuge: p.conjuge,
          evidencia: p.evidencia,
          };
        }),
        evidencias: e,
      };

      // ---------------------------------------- auto-correcoes por ato
      const fa = estado.fichasAto[a.numero];
      const anotaCorrecao = (campo, motivo) => estado.correcoes.push({ ato: rotuloAto, campo, motivo });

      // 1) Ato sem nenhuma parte: vincula o proprietario vigente. E o caso de
      //    CAR, CEP, CCIR/CIB, obito, clausulas restritivas e afins.
      //    Vale tambem quando o ato CITA alguem mas nao lhe da papel algum - a
      //    averbacao de casamento nomeia o conjuge, e quem responde pelo imovel
      //    continua sendo o dono. Nesses casos o dono e somado, nao substitui.
      const semPapel = fa.pessoas.every((pe) => !pe.condicao_parte && !pe.relacao_juridica);
      if (semPapel) {
        const jaCitados = new Set(fa.pessoas.map((pe) => pe.cpf_cnpj).filter(Boolean));
        const donos = proprietariosComoPartes(vigente, fa.data_ato, rotuloAto)
          .filter((d) => !jaCitados.has(d.cpf_cnpj));
        if (donos.length) {
          const fonte = ((vigente.snapshots || {})[rotuloAto] || {}).fonte
            || vigente.fonteTitularidade || 'abertura';
          fa.pessoas = fa.pessoas.concat(donos);
          anotaCorrecao('dados_pessoa', donos.length + ' proprietario(s) vigente(s) vinculado(s) - '
            + 'o ato nao lhes da papel proprio (titularidade na data do ato, fonte: ' + fonte + ')');
        }
      }

      // 1b) Ato de transmissao sem imposto citado: o layout exige valor_imposto
      //     quando ato = 4. Nas partilhas antigas do acervo nao ha ITBI no
      //     texto - entra 0, dito na tela, em vez de travar o arquivo.
      if (fa.ato === 4 && (fa.valor_imposto === null || fa.valor_imposto === undefined)) {
        fa.valor_imposto = 0;
        anotaCorrecao('valor_imposto', 'nenhum imposto citado no ato -> 0 (obrigatorio quando ato = 4)');
      }

      // 1c) Pessoa citada no ato sem papel nenhum (averbacao de qualificacao
      //     pessoal, por exemplo) que E proprietaria: entra como proprietaria,
      //     com o percentual da titularidade apurada.
      fa.pessoas.forEach((pe, i) => {
        if (pe.condicao_parte || pe.relacao_juridica || !pe.cpf_cnpj) return;
        const dono = (vigente.proprietarios || []).find((d) => d.cpf_cnpj === pe.cpf_cnpj);
        if (!dono) return;
        pe.relacao_juridica = 1;
        if (pe.percentual == null) pe.percentual = dono.percentual;
        if (!pe.data_inicio_rel_juridica) pe.data_inicio_rel_juridica = dono.desde || fa.data_ato;
        anotaCorrecao('dados_pessoa[' + i + '].relacao_juridica',
          'consta como proprietaria na titularidade apurada (' + (dono.fonte || '?') + ')');
      });

      // 1e) Averbacao de CASAMENTO sob comunhao universal: o conjuge nomeado
      //     passa a ser co-proprietario, e e por isso que a averbacao existe.
      //     So vale com o regime DECLARADO no ato e so na comunhao universal -
      //     na parcial o bem anterior ao casamento nao se comunica, e ali a
      //     pendencia continua de pe, para o oficial decidir.
      if (/CASAMENTO|casou-se/i.test(a.texto)) {
        fa.pessoas.forEach((pe, i) => {
          if (pe.condicao_parte || pe.relacao_juridica) return;
          if (pe.regime_bens !== 2 || pe.regime_presumido) return;
          pe.relacao_juridica = 1;
          if (!pe.data_inicio_rel_juridica) pe.data_inicio_rel_juridica = fa.data_ato;
          anotaCorrecao('dados_pessoa[' + i + '].relacao_juridica',
            'averbacao de casamento sob comunhao universal declarada no ato -> proprietario');
        });
      }

      // 1d) CPF antigo de 9 digitos completado pelo mesmo numero que aparece
      //     inteiro em ato posterior (o mais recente e o correto).
      fa.pessoas.forEach((pe, i) => {
        const completo = pe.cpf_cnpj && (vigente.completaCpf || {})[pe.cpf_cnpj];
        if (!completo) return;
        anotaCorrecao('dados_pessoa[' + i + '].cpf_cnpj',
          'CPF ' + pe.cpf_cnpj + ' (9 digitos) completado para ' + completo
          + ', como consta em ato posterior');
        pe.cpf_cnpj = completo;
      });

      // 2) Um unico titular e nenhum percentual: 100%.
      if (fa.pessoas.length === 1 && fa.pessoas[0].percentual == null && fa.pessoas[0].relacao_juridica) {
        fa.pessoas[0].percentual = 100;
        anotaCorrecao('dados_pessoa[0].percentual', 'unico titular no ato -> 100%');
      }

      // 2b) Quem nao tem percentual proprio (credor, avalista, anuente) entra
      //     com 0: o layout exige o campo quando motivo_envio = 1.
      fa.pessoas.forEach((pe, i) => {
        if (pe.percentual == null) {
          pe.percentual = 0;
          anotaCorrecao('dados_pessoa[' + i + '].percentual',
            'sem percentual proprio no ato -> 0');
        }
      });

      // 2c) Regime presumido pelo regime legal da epoca (Lei 6.515/77).
      fa.pessoas.forEach((pe, i) => {
        if (pe.regime_presumido && pe.regime_bens) {
          anotaCorrecao('dados_pessoa[' + i + '].regime_bens',
            'presumido: ' + (pe.evidencia_regime || 'regime legal da epoca do ato')
            + ' - a matricula nao declara o regime');
        }
      });

      // 3) Relacao juridica preenchida exige a data de inicio: usa a do ato.
      fa.pessoas.forEach((pe, i) => {
        if (pe.relacao_juridica && !pe.data_inicio_rel_juridica && fa.data_ato) {
          pe.data_inicio_rel_juridica = fa.data_ato;
          anotaCorrecao('dados_pessoa[' + i + '].data_inicio_rel_juridica', 'data do proprio ato');
        }
        if (pe.estrangeiro === null || pe.estrangeiro === undefined) {
          pe.estrangeiro = false;
          anotaCorrecao('dados_pessoa[' + i + '].estrangeiro',
            'nenhuma mencao a estrangeiro no ato -> false');
        }
      });
    }
    render();
  }

  // ------------------------------------------------------- etapa 2/3: revisao

  function renderListaAtos() {
    const alvo = $('#lista-atos');
    alvo.textContent = '';
    if (!estado.atos.length) {
      alvo.appendChild(el('p', { className: 'vazio', textContent: 'Nenhum ato reconhecido ainda.' }));
      return;
    }
    const cab = el('div', { className: 'barra-atos' }, [
      el('strong', { textContent: estado.atos.length + ' ato(s) reconhecido(s)' }),
      el('button', { className: 'ligado', textContent: 'Marcar todos', onclick: () => {
        estado.atos.forEach((a) => estado.selecionados.add(a.numero)); render();
      } }),
      el('button', { textContent: 'Desmarcar todos', onclick: () => { estado.selecionados.clear(); render(); } }),
    ]);
    alvo.appendChild(cab);

    const tabela = el('table', { className: 'tabela' });
    tabela.appendChild(el('thead', {}, [el('tr', {}, ['', 'Ato', 'Tipo', 'Data', 'motivo_envio', 'Inicio do texto']
      .map((t) => el('th', { textContent: t })))]));
    const corpo = el('tbody');
    for (const a of estado.atos) {
      const ficha = estado.fichasAto[a.numero] || {};
      const motivo = P.motivoEnvio(ficha.data_ato);
      const chk = el('input', { type: 'checkbox', checked: estado.selecionados.has(a.numero) });
      chk.addEventListener('change', () => {
        if (chk.checked) estado.selecionados.add(a.numero); else estado.selecionados.delete(a.numero);
        renderResumoSelecao();
      });
      corpo.appendChild(el('tr', {}, [
        el('td', {}, [chk]),
        el('td', { textContent: a.ehAbertura ? 'Abertura' : (a.tipo === 1 ? 'R.' : 'AV.') + a.numero }),
        el('td', { textContent: a.ehAbertura ? 'Abertura de matricula' : a.tipoRotulo }),
        el('td', { textContent: ficha.data_ato || '(pendente)', className: ficha.data_ato ? '' : 'alerta' }),
        el('td', { textContent: motivo === null ? '(sem data)' : motivo + ' - ' + E.rotulo('motivo_envio', motivo),
          className: motivo === null ? 'alerta' : '' }),
        el('td', { className: 'trecho', textContent: a.texto.replace(/\s+/g, ' ').slice(0, 110) }),
      ]));
    }
    tabela.appendChild(corpo);
    alvo.appendChild(tabela);
  }

  function renderEstadoVigente() {
    const alvo = $('#estado-vigente');
    alvo.textContent = '';
    const v = estado.vigente;
    if (!v || !v.campos) return;
    const c = v.campos;
    alvo.appendChild(el('h3', { textContent: 'Estado vigente apurado na leitura completa' }));

    const ul = el('ul', { className: 'vigente' });
    const linhaV = (rotulo, campo) => {
      if (!c[campo]) return;
      ul.appendChild(el('li', {}, [
        el('b', { textContent: rotulo + ': ' }),
        String(c[campo].valor),
        el('small', { className: 'evidencia', textContent: '  [' + c[campo].ato + ' - ' + (c[campo].rotulo || '') + ']' }),
      ]));
    };
    if (v.areaEscolhida) {
      ul.appendChild(el('li', {}, [
        el('b', { textContent: 'Area do imovel: ' }),
        v.areaEscolhida.valor.valor + ' ' + E.rotulo('unidade_area', v.areaEscolhida.valor.unidade),
        el('small', { className: 'evidencia', textContent: '  [' + v.areaEscolhida.ato + ' - ' + v.areaEscolhida.rotulo + ']' }),
      ]));
    }
    linhaV('Nome do imovel', 'nome_imovel');
    linhaV('CAR', 'car');
    linhaV('CCIR', 'ccir');
    linhaV('COD_SNCR', 'cod_sncr');
    linhaV('CIB', 'cib');
    linhaV('NIRF (nao e CIB)', 'nirf');
    linhaV('CEP', 'cep');
    linhaV('Georreferenciado', 'georreferenciamento');
    linhaV('Certificacao INCRA', 'certificacao_incra');
    linhaV('Codigo INCRA (certificacao)', 'codigo_incra');
    linhaV('Centroide (CAR)', 'centroide');
    alvo.appendChild(ul);

    // Areas concorrentes: a escolha e explicita e trocavel.
    if (v.candidatosArea.length > 1) {
      const det = el('details');
      det.appendChild(el('summary', { textContent: 'Outras areas encontradas no documento ('
        + (v.candidatosArea.length - 1) + ') - clique para trocar' }));
      const ulA = el('ul', { className: 'vigente' });
      for (const cand of v.candidatosArea) {
        const usada = v.areaEscolhida === cand;
        const li = el('li', {}, [
          el('b', { textContent: cand.valor.valor + ' ha ' }),
          '[' + cand.ato + ' - ' + cand.rotulo + '] ',
        ]);
        if (!usada) {
          li.appendChild(el('button', { textContent: 'usar esta', onclick: () => {
            estado.vigente.areaEscolhida = cand;
            estado.fichaImovel.area_terreno_total = cand.valor;
            render();
          } }));
        } else {
          li.appendChild(el('small', { className: 'evidencia', textContent: '(em uso)' }));
        }
        ulA.appendChild(li);
      }
      det.appendChild(ulA);
      alvo.appendChild(det);
    }

    // Titularidade vigente: quem responde pelos atos que nao qualificam ninguem.
    if (v.proprietarios && v.proprietarios.length) {
      const det = el('details', { open: true });
      det.appendChild(el('summary', { textContent: 'Titularidade vigente ('
        + v.proprietarios.length + ') - fonte: ' + (v.fonteTitularidade || 'abertura') }));
      const ulP = el('ul', { className: 'vigente' });
      for (const p of v.proprietarios) {
          const li = el('li', {}, [
          el('b', { textContent: (p.nome_completo || '(sem nome)') + ' ' }),
          (p.percentual != null ? p.percentual + '% ' : ''),
          el('code', { textContent: p.cpf_cnpj || 'CPF nao localizado' }),
        ]);
        if (!p.cpf_cnpj) {
          li.appendChild(el('small', { className: 'aviso-item', textContent:
            '  o nome da tabela nao casou com nenhum CPF do documento - informe o CPF' }));
        } else if (p.casadoPeloNome) {
          li.appendChild(el('small', { className: 'evidencia', textContent: '  (CPF casado pelo nome)' }));
        }
        ulP.appendChild(li);
      }
      det.appendChild(ulP);

      // A soma dos percentuais e o teste mais simples de sanidade da apuracao:
      // o retrato da tabela pode ser anterior a atos posteriores de transmissao.
      const soma = v.proprietarios.reduce((s, p) => s + (p.percentual || 0), 0);
      if (v.proprietarios.some((p) => p.percentual != null) && Math.abs(soma - 100) > 0.5) {
        det.appendChild(el('p', { className: 'aviso', textContent:
          'A soma dos percentuais da ' + soma.toFixed(2) + '%, nao 100%. A titularidade '
          + 'apurada mistura o retrato da tabela com atos posteriores - confira quem '
          + 'realmente e dono hoje antes de exportar.' }));
      }
      alvo.appendChild(det);
    }

    if (v.confrontantes.length) {
      const det = el('details');
      det.appendChild(el('summary', { textContent: 'Confrontantes detectados (' + v.confrontantes.length + ')' }));
      const ulC = el('ul', { className: 'vigente' });
      for (const cf of v.confrontantes) {
        ulC.appendChild(el('li', { textContent: (cf.nome_proprietario_confrontante || '(sem nome)')
          + (cf.numero_matricula_confrontante ? ' - Mat. ' + cf.numero_matricula_confrontante : '')
          + '  [' + cf.ato + ']' }));
      }
      det.appendChild(ulC);
      alvo.appendChild(det);
    }

    if (c.nirf && !c.cib) {
      alvo.appendChild(el('p', { className: 'aviso', textContent:
        'Foi encontrado NIRF e nenhum CIB. Sao cadastros diferentes - nao use o NIRF no campo cib.' }));
    }
    if (v.historico.length) {
      const det = el('details');
      det.appendChild(el('summary', { textContent: 'De onde veio cada valor (' + v.historico.length + ')' }));
      const ol = el('ol');
      for (const h of v.historico) {
        ol.appendChild(el('li', { textContent: h.ato + ': ' + h.campo + ' = ' + JSON.stringify(h.valor)
          + (h.rotulo ? ' (' + h.rotulo + ')' : '') }));
      }
      det.appendChild(ol);
      alvo.appendChild(det);
    }
  }

  /** Diagnostico do CNM: calculado, confere, ou divergente do esperado. */
  function provaCnm(f) {
    const DOC = global.ONR_DOC;
    if (!DOC || !f.cnm) return 'calculado do CNS + numero da matricula (ISO 7064 MOD 97-10)';
    const r = DOC.confereCnm(f.cnm);
    if (r.situacao === 'ok') {
      return estado.cnmCalculado === f.cnm
        ? 'calculado e conferido (digito ' + r.esperado + ')'
        : 'digito verificador confere';
    }
    return 'ATENCAO: ' + r.mensagem;
  }

  function renderFichaImovel() {
    const alvo = $('#ficha-imovel');
    alvo.textContent = '';
    if (!estado.atos.length) return;
    const f = estado.fichaImovel;
    const set = (k) => (v) => { f[k] = v; };
    alvo.appendChild(el('h3', { textContent: 'Dados do imovel (valem para todos os atos exportados)' }));

    const urbano = tipoAtual() === 'urbano';
    const comuns = [
      linha('numero_matricula', campoTexto(f.numero_matricula, set('numero_matricula'), 'ex: 1118')),
      linha('data_matricula', campoTexto(f.data_matricula, set('data_matricula'), 'DD/MM/AAAA')),
      linha('cnm', campoTexto(f.cnm, (v) => { f.cnm = v; render(); }, '000000.0.0000000-00'), provaCnm(f)),
      linha('situacao', selectEnum('situacao', f.situacao, set('situacao')),
        estado.situacaoEncerrada
          ? '4 - Encerrada, pelo texto do ato: "' + estado.situacaoEncerrada + '"'
          : null),
    ];
    const especificos = urbano ? [
      linha('contexto_urbano', selectEnum('contexto_urbano', f.contexto_urbano, set('contexto_urbano'), false)),
      linha('cif', campoTexto(f.cif, set('cif'), 'cadastro na Prefeitura'),
        estado.cifAssumido
          ? 'assumido "0": a matricula nao traz a designacao cadastral da Prefeitura'
          : provaVigente('cif')),
      linha('cib', campoTexto(f.cib, set('cib'), 'A0A0A0A-0')),
      linha('georreferenciamento', campoBool(f.georreferenciamento, set('georreferenciamento')), provaGeo()),
      linha('livro_matricula', campoTexto(f.livro_matricula, set('livro_matricula'))),
      linha('folha_matricula', campoTexto(f.folha_matricula, set('folha_matricula'))),
    ] : [
      linha('contexto_rural', selectEnum('contexto_rural', f.contexto_rural, set('contexto_rural'), false)),
      linha('georreferenciamento', campoBool(f.georreferenciamento, set('georreferenciamento')), provaGeo()),
      linha('certificacao_incra', campoBool(f.certificacao_incra, set('certificacao_incra')),
        estado.certAssumida
          ? 'assumido false: nenhum ato declara certificacao do INCRA - confirme'
          : provaVigente('certificacao_incra')),
      linha('codigo_incra', campoTexto(f.codigo_incra, set('codigo_incra')),
        f.codigo_incra ? provaVigente('codigo_incra') : provaVigente('codigo_incra_incompleto')),
      linha('cib', campoTexto(f.cib, set('cib'), 'A0A0A0A-0'), provaVigente('cib')),
      linha('ccir', campoTexto(f.ccir, set('ccir'), '11 digitos'), provaVigente('ccir')),
      linha('cod_sncr', campoTexto(f.cod_sncr, set('cod_sncr'), '13 digitos'), provaVigente('cod_sncr')),
      linha('car', campoTexto(f.car, set('car'), '41 caracteres'),
        (estado.vigente && estado.vigente.campos.car_suspeito)
          ? provaVigente('car_suspeito') : provaVigente('car')),
    ];
    const finais = [
      linha('imovel_possui_nome', campoBool(f.imovel_possui_nome, set('imovel_possui_nome'))),
      linha('nome_imovel', campoTexto(f.nome_imovel, set('nome_imovel'))),
      linha('area (valor)', campoTexto(f.area_terreno_total ? f.area_terreno_total.valor : null, (v) => {
        f.area_terreno_total = Object.assign({}, f.area_terreno_total, { valor: v });
      }, urbano ? 'ex: 246.50' : 'ex: 307.87')),
      linha('area (unidade)', selectEnum('unidade_area', f.area_terreno_total ? f.area_terreno_total.unidade : null, (v) => {
        f.area_terreno_total = Object.assign({}, f.area_terreno_total, { unidade: v });
      })),
    ];
    alvo.appendChild(el('div', { className: 'grade' }, comuns.concat(especificos, finais)));

    const end = (f.dados_imovel && f.dados_imovel[0]) || {};
    f.dados_imovel = [end];
    alvo.appendChild(el('h4', { textContent: 'Endereco do imovel (dados_imovel)' }));
    const campoEnd = [];
    if (urbano) {
      campoEnd.push(linha('tipo_logradouro', campoTexto(end.tipo_logradouro, (v) => { end.tipo_logradouro = v; },
        'enum 1..311'), estado.tipoLogradouroAssumido
          ? 'assumido 177 (Nao Especificado): a palavra do logradouro nao esta no glossario'
          : provaVigente('endereco_tipo_logradouro')));
    }
    campoEnd.push(linha('logradouro', campoTexto(end.logradouro, (v) => { end.logradouro = v; }),
      provaVigente('endereco_logradouro')));
    if (urbano) {
      campoEnd.push(linha('numero_logradouro', campoTexto(end.numero_logradouro, (v) => { end.numero_logradouro = v; }),
        estado.numeroAssumido ? 'assumido "S/N": a descricao nao traz numero na via'
          : provaVigente('endereco_numero_logradouro')));
      const corteBairro = (estado.cortados || []).find((c) => c.campo === 'bairro');
      campoEnd.push(linha('bairro', campoTexto(end.bairro, (v) => { end.bairro = v; }),
        corteBairro
          ? 'cortado em ' + corteBairro.limite + ' caracteres (o schema nao aceita mais): "'
            + corteBairro.antes + '"'
          : provaVigente('endereco_bairro')));
    }
    campoEnd.push(linha('complemento', campoTexto(end.complemento, (v) => { end.complemento = v; }),
      provaVigente('endereco_complemento')));
    campoEnd.push(linha('cep', campoTexto(end.cep, (v) => { end.cep = v; }, '8 digitos'), provaVigente('cep')));
    campoEnd.push(linha('cod_ibge_municipio', campoTexto(end.cod_ibge_municipio, (v) => { end.cod_ibge_municipio = v; }, '7 digitos')));
    campoEnd.push(linha('uf', campoTexto(end.uf, (v) => { end.uf = v; }, 'ex: 52')));
    if (urbano) {
      campoEnd.push(linha('area_m2', campoTexto(end.area_m2, (v) => { end.area_m2 = v; })));
    }
    alvo.appendChild(el('div', { className: 'grade' }, campoEnd));

    if (urbano && estado.vigente && estado.vigente.campos.area_construida) {
      alvo.appendChild(el('p', { className: 'evidencia', textContent:
        'Area construida detectada: ' + estado.vigente.campos.area_construida.valor
        + ' m2 - nao entra em area_terreno_total (o layout nao tem campo para ela).' }));
    }
  }

  function provaGeo() {
    if (estado.geoAssumido) {
      return 'assumido false: nenhuma descricao georreferenciada no documento - confirme';
    }
    return provaVigente('georreferenciamento');
  }

  /** Evidencia de um campo apurado no estado vigente. */
  /**
   * Alguns campos ficam vazios nao porque o dado falta na matricula, e sim porque
   * o que esta escrito nao serve como esta: a certificacao do INCRA com 31
   * caracteres em vez de 32, por exemplo. "Campo obrigatorio ausente" e verdade
   * do arquivo, mas esconde isso - e a diferenca muda o que o oficial faz
   * (conferir um numero, em vez de ir buscar um dado que nao existe).
   */
  const CAMPOS_COM_ACHADO_PARCIAL = { codigo_incra: 'codigo_incra_incompleto' };

  function explicaAusente(caminho) {
    if (!caminho) return '';
    const campo = String(caminho).split('.').pop();
    const chave = CAMPOS_COM_ACHADO_PARCIAL[campo];
    if (!chave) return '';
    const achado = estado.vigente && estado.vigente.campos[chave];
    if (!achado) return '';
    const frase = achado.rotulo.charAt(0).toUpperCase() + achado.rotulo.slice(1);
    return '. ' + frase + ': "' + achado.valor + '" - confira no SIGEF';
  }

  function provaVigente(campo) {
    const c = estado.vigente && estado.vigente.campos[campo];
    if (!c) return '';
    return '[' + c.ato + ' - ' + (c.rotulo || '') + '] ' + (c.trecho || '');
  }

  /** Texto de evidencia de um campo extraido automaticamente. */
  function prova(fa, campo) {
    const e = fa.evidencias && fa.evidencias[campo];
    if (!e) return 'nao encontrado no texto - preencher a mao';
    return (e.rotulo ? '[' + e.rotulo + '] ' : '') + (e.trecho || '');
  }

  function renderFichasAtos() {
    const alvo = $('#fichas-atos');
    alvo.textContent = '';
    const escolhidos = estado.atos.filter((a) => estado.selecionados.has(a.numero));
    if (!escolhidos.length) return;
    alvo.appendChild(el('h3', { textContent: 'Atos selecionados para exportacao (' + escolhidos.length + ')' }));

    for (const a of escolhidos) {
      const fa = estado.fichasAto[a.numero];
      const set = (k) => (v) => { fa[k] = v; render(); };
      const setSemRender = (k) => (v) => { fa[k] = v; };
      const bloco = el('details', { className: 'ato', open: escolhidos.length <= 3 });
      const motivo = P.motivoEnvio(fa.data_ato);
      bloco.appendChild(el('summary', {}, [
        el('b', { textContent: a.ehAbertura ? 'Abertura da matricula' : (a.tipo === 1 ? 'R.' : 'AV.') + a.numero }),
        ' - ' + (fa.data_ato || 'sem data') + ' - motivo_envio '
        + (motivo === null ? '?' : motivo) + (fa.ato ? ' - ato ' + fa.ato : ' - ato nao classificado'),
      ]));

      bloco.appendChild(el('div', { className: 'grade' }, [
        linha('tipo_ato', selectEnum('tipo_ato', fa.tipo_ato, setSemRender('tipo_ato'), false)),
        linha('numero_ato', campoTexto(fa.numero_ato, setSemRender('numero_ato'))),
        linha('data_ato', campoTexto(fa.data_ato, set('data_ato'), 'DD/MM/AAAA'), prova(fa, 'data_ato')),
        linha('ato', selectEnum('ato', fa.ato, set('ato')), prova(fa, 'ato')),
        linha('alteracao_titularidade', selectEnum('alteracao_titularidade', fa.alteracao_titularidade, setSemRender('alteracao_titularidade')),
          prova(fa, 'alteracao_titularidade')),
        linha('alteracao_imovel', selectEnum('alteracao_imovel', fa.alteracao_imovel, setSemRender('alteracao_imovel')),
          prova(fa, 'alteracao_imovel')),
        linha('valor_transacao', campoTexto(fa.valor_transacao, setSemRender('valor_transacao')), prova(fa, 'valor_transacao')),
        linha('valor_imposto', campoTexto(fa.valor_imposto, setSemRender('valor_imposto')), prova(fa, 'valor_imposto')),
        linha('protocolo_prenotacao', campoTexto(fa.protocolo_prenotacao, setSemRender('protocolo_prenotacao')),
          prova(fa, 'protocolo_prenotacao')),
        linha('data_protocolo_prenotacao', campoTexto(fa.data_protocolo_prenotacao, setSemRender('data_protocolo_prenotacao'), 'DD/MM/AAAA'),
          prova(fa, 'data_protocolo_prenotacao')),
      ]));

      bloco.appendChild(el('h4', { textContent: 'Partes (dados_pessoa)' }));
      if (fa.representantes && fa.representantes.length) {
        bloco.appendChild(el('p', { className: 'evidencia', textContent:
          'Representante(s) legal(is) identificado(s) e mantido(s) fora das partes: '
          + fa.representantes.map((r) => (r.nome_completo || '?') + ' (' + r.cpf_cnpj + ')').join('; ') }));
      }
      const tab = el('table', { className: 'tabela pessoas' });
      tab.appendChild(el('thead', {}, [el('tr', {}, ['nome_completo', 'cpf_cnpj', 'condicao', 'est. civil',
        'regime', 'relacao', '% ', 'inicio rel.', ''].map((t) => el('th', { textContent: t })))]));
      const corpo = el('tbody');
      fa.pessoas.forEach((pe, i) => {
        const tr = el('tr', {}, [
          el('td', {}, [campoTexto(pe.nome_completo, (v) => { pe.nome_completo = v; })]),
          el('td', {}, [campoTexto(pe.cpf_cnpj, (v) => { pe.cpf_cnpj = v; render(); })]),
          el('td', {}, [selectEnum('condicao_parte', pe.condicao_parte, (v) => { pe.condicao_parte = v; })]),
          el('td', {}, [selectEnum('estado_civil', pe.estado_civil, (v) => { pe.estado_civil = v; render(); })]),
          el('td', {}, [selectEnum('regime_bens', pe.regime_bens, (v) => { pe.regime_bens = v; })]),
          el('td', {}, [selectEnum('relacao_juridica', pe.relacao_juridica, (v) => { pe.relacao_juridica = v; })]),
          el('td', {}, [campoTexto(pe.percentual, (v) => { pe.percentual = v; })]),
          el('td', {}, [campoTexto(pe.data_inicio_rel_juridica, (v) => { pe.data_inicio_rel_juridica = v; }, 'DD/MM/AAAA')]),
          el('td', {}, [el('button', { textContent: 'x', title: 'remover', onclick: () => {
            fa.pessoas.splice(i, 1); render();
          } })]),
        ]);
        corpo.appendChild(tr);

        // Regime "comunhao de bens" sem qualificar: a extracao nao decide.
        if (pe.regime_ambiguo && !pe.regime_bens) {
          corpo.appendChild(el('tr', { className: 'linha-evidencia' }, [
            el('td', { colSpan: 9 }, [
              el('small', { className: 'aviso-item', textContent:
                'O ato diz "regime da comunhao de bens" sem dizer se universal ou parcial - escolha o regime. ' }),
              el('button', { textContent: 'universal (2)', onclick: () => { pe.regime_bens = 2; render(); } }),
              el('button', { textContent: 'parcial (1)', onclick: () => { pe.regime_bens = 1; render(); } }),
            ]),
          ]));
        }
        if (pe.vinculadoAutomaticamente) {
          corpo.appendChild(el('tr', { className: 'linha-evidencia' }, [
            el('td', { colSpan: 9 }, [el('small', { className: 'aviso-item', textContent:
              'vinculado automaticamente: este ato nao qualifica ninguem, entrou o proprietario vigente' })]),
          ]));
        }
        if (pe.papel || pe.herdado) {
          corpo.appendChild(el('tr', { className: 'linha-evidencia' }, [
            el('td', { colSpan: 9 }, [el('small', { className: 'evidencia',
              textContent: (pe.papel ? 'papel detectado: ' + pe.papel : '')
                + (pe.herdado ? '  |  herdado de outro ato: ' + pe.herdado : '') })]),
          ]));
        }

        // Conferencia de digito verificador, com sugestao quando falta o DV.
        const DOC = global.ONR_DOC;
        if (DOC && pe.cpf_cnpj) {
          const r = DOC.confere(pe.cpf_cnpj);
          if (r.situacao !== 'ok') {
            const celula = el('td', { colSpan: 9 });
            const marca = el('small', { className: r.situacao === 'base_incompleta' ? 'aviso-item' : 'alerta',
              textContent: r.mensagem + ' ' });
            celula.appendChild(marca);
            if (r.sugestao) {
              celula.appendChild(el('button', { textContent: 'usar ' + DOC.mascaraCpf(r.sugestao),
                title: 'aplica a sugestao neste campo - confira no documento antes',
                onclick: () => { pe.cpf_cnpj = r.sugestao; render(); } }));
            }
            corpo.appendChild(el('tr', { className: 'linha-evidencia' }, [celula]));
          }
        }

        if (pe.evidencia) {
          corpo.appendChild(el('tr', { className: 'linha-evidencia' }, [
            el('td', { colSpan: 9 }, [el('small', { className: 'evidencia', textContent: pe.evidencia.slice(0, 160) })]),
          ]));
        }
      });
      tab.appendChild(corpo);
      bloco.appendChild(tab);
      bloco.appendChild(el('button', { textContent: '+ parte', onclick: () => {
        fa.pessoas.push({ nome_completo: null, cpf_cnpj: null, estrangeiro: false });
        render();
      } }));

      const det = el('details', { className: 'texto-ato' });
      det.appendChild(el('summary', { textContent: 'Texto integral do ato' }));
      det.appendChild(el('pre', { textContent: a.texto }));
      bloco.appendChild(det);

      alvo.appendChild(bloco);
    }
  }

  /** Painel do que a ferramenta preencheu sozinha, com o motivo de cada item. */
  function renderCorrecoes() {
    const alvo = $('#correcoes');
    if (!alvo) return;
    alvo.textContent = '';
    const cs = (estado.correcoes || []).filter((c) => estado.selecionados.has(
      String(c.ato).replace(/^(R\.|AV\.)/, '')));
    if (!cs.length) return;
    const det = el('details', { open: true });
    det.appendChild(el('summary', { textContent: 'Preenchido automaticamente nos atos marcados ('
      + cs.length + ') - confira antes de exportar' }));
    const ul = el('ul', { className: 'erros' });
    for (const c of cs) {
      ul.appendChild(el('li', {}, [
        el('b', { textContent: c.ato + ' ' }),
        el('code', { textContent: c.campo }),
        ' - ' + c.motivo,
      ]));
    }
    det.appendChild(ul);
    alvo.appendChild(det);
  }

  function renderResumoSelecao() {
    $('#contagem').textContent = estado.selecionados.size + ' de ' + estado.atos.length + ' ato(s) marcado(s)';
    renderFichasAtos();
    renderCorrecoes();
  }

  // ------------------------------------------------------ etapa 4: gerar JSON

  function gerar() {
    const versao = $('#versao').value;
    const cns = $('#cns').value;
    const imoveis = [];
    const relatorio = [];

    for (const a of estado.atos) {
      if (!estado.selecionados.has(a.numero)) continue;
      const fa = estado.fichasAto[a.numero];
      const ficha = Object.assign({}, estado.fichaImovel, {
        tipo_ato: fa.tipo_ato,
        numero_ato: fa.numero_ato,
        ato: fa.ato,
        data_ato: fa.data_ato,
        alteracao_titularidade: fa.alteracao_titularidade,
        alteracao_imovel: fa.alteracao_imovel,
        valor_transacao: fa.valor_transacao,
        valor_imposto: fa.valor_imposto,
        protocolo_prenotacao: fa.protocolo_prenotacao,
        data_protocolo_prenotacao: fa.data_protocolo_prenotacao,
        dados_pessoa: fa.pessoas,
      });
      const r = B.montaImovel(ficha, { tipo: tipoAtual(), versao });
      imoveis.push(r.imovel);
      relatorio.push({ ato: a.ehAbertura ? 'Abertura' : (a.tipo === 1 ? 'R.' : 'AV.') + a.numero,
        pendencias: r.pendencias, avisos: r.avisos });
    }

    const arquivo = B.montaArquivo(cns, imoveis, versao);
    const schema = tipoAtual() === 'urbano' ? global.ONR_SCHEMA_URBANO : global.ONR_SCHEMA_RURAL;
    const v = V.valida(schema, arquivo);
    estado.resultado = { arquivo, relatorio, validacao: v, versao };
    renderResultado();
    $('#resultado').scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  // ------------------------------------------- mensagens em portugues de gente

  /**
   * Nome de cada campo como o oficial o conhece. O nome tecnico continua ao
   * lado, porque e ele que aparece no formulario e no arquivo enviado - mas quem
   * le a pendencia nao deveria precisar dele para entender o que fazer.
   */
  const NOME_DO_CAMPO = {
    numero_matricula: 'numero da matricula', data_matricula: 'data de abertura da matricula',
    numero_transcricao: 'numero da transcricao', data_transcricao: 'data da transcricao',
    cnm: 'CNM (codigo nacional de matricula)', situacao: 'situacao da matricula',
    tipo_imovel: 'tipo do imovel (rural ou urbano)',
    tipo_matricula_transcricao: 'matricula ou transcricao',
    contexto_urbano: 'contexto do imovel urbano', contexto_rural: 'contexto do imovel rural',
    regime_utilizacao: 'regime de utilizacao', georreferenciamento: 'imovel georreferenciado',
    certificacao_incra: 'imovel certificado pelo INCRA',
    codigo_incra: 'codigo da certificacao do INCRA',
    sistema_referencia: 'sistema de referencia (DATUM)',
    sistema_coordenadas: 'sistema de coordenadas', fuso_zona: 'fuso / zona',
    centroide: 'centroide', cib: 'CIB (cadastro na Receita Federal)',
    cif: 'CIF / CCI (cadastro na Prefeitura)', ccir: 'CCIR (certificado do INCRA)',
    cod_sncr: 'codigo do imovel rural no INCRA', car: 'CAR (cadastro ambiental rural)',
    nirf: 'NIRF', imovel_possui_nome: 'o imovel tem nome', nome_imovel: 'nome do imovel',
    area_terreno_total: 'area total do imovel', area_construida: 'area construida',
    area_m2: 'area do terreno em m2', livro_matricula: 'livro', folha_matricula: 'folha',
    dados_imovel: 'endereco do imovel', tipo_logradouro: 'tipo do logradouro',
    logradouro: 'logradouro', numero_logradouro: 'numero na via',
    complemento: 'complemento', bairro: 'bairro', cep: 'CEP',
    cod_ibge_municipio: 'codigo IBGE do municipio', uf: 'UF',
    motivo_envio: 'motivo do envio', tipo_ato: 'registro ou averbacao',
    numero_ato: 'numero do ato', ato: 'natureza do ato', data_ato: 'data do ato',
    protocolo_prenotacao: 'numero do protocolo',
    data_protocolo_prenotacao: 'data do protocolo',
    alteracao_titularidade: 'forma de transmissao', alteracao_imovel: 'forma de alteracao',
    valor_transacao: 'valor do negocio', valor_imposto: 'imposto recolhido',
    base_calculo_itbi: 'base de calculo do ITBI', dados_pessoa: 'partes do ato',
    nome_completo: 'nome', cpf_cnpj: 'CPF/CNPJ', percentual: 'percentual',
    estado_civil: 'estado civil', regime_bens: 'regime de bens',
    relacao_juridica: 'relacao juridica', condicao_parte: 'condicao da parte',
    data_inicio_rel_juridica: 'data de inicio da relacao juridica',
    estrangeiro: 'estrangeiro', decisao_jud: 'decisao judicial',
  };

  /**
   * Traduz o motivo tecnico para uma frase de cartorio. As condicoes do manual
   * vem escritas como "obrigatorio se motivo_envio = 1"; quem le precisa saber
   * o que isso quer dizer, nao o numero do enum.
   */
  const MOTIVOS_LEGIVEIS = [
    [/^campo obrigatorio ausente$/, 'falta preencher'],
    [/^sempre obrigatorio \(true\/false\)$/, 'e sempre exigido - responda Sim ou Nao'],
    [/^sempre obrigatorio \(1 matricula \/ 2 transcricao\)$/,
      'e sempre exigido - diga se o folio e matricula ou transcricao'],
    [/^sempre obrigatorio \(pelo menos um endereco\)$/, 'e sempre exigido: o imovel precisa de endereco'],
    [/^sempre obrigatorio \(7 digitos\)$/, 'e sempre exigido (7 digitos)'],
    [/^sempre obrigatorio \(2 digitos\)$/, 'e sempre exigido (2 digitos)'],
    [/^sempre obrigatorio$/, 'e sempre exigido'],
    [/^obrigatorio se motivo_envio = 1$/,
      'e exigido nos atos praticados a partir de 02/12/2025 (os anteriores vao como acervo)'],
    [/^obrigatorio se certificacao_incra = true$/,
      'e exigido porque a matricula declara o imovel certificado pelo INCRA'],
    [/^obrigatorio se imovel_possui_nome = true$/, 'e exigido porque o imovel tem nome'],
    [/^obrigatorio se tipo_matricula_transcricao = 1$/, 'e exigido quando o folio e matricula'],
    [/^obrigatorio se tipo_matricula_transcricao = 2$/, 'e exigido quando o folio e transcricao'],
    [/^obrigatorio se ato = 4$/, 'e exigido em ato de transmissao'],
    [/^obrigatorio se ato = 5$/, 'e exigido em ato que altera o imovel'],
    [/^obrigatorio no imovel urbano \(exigido pelo schema\)$/, 'e exigido em imovel urbano'],
    [/^obrigatorio se estado_civil = 2 \(casado\) ou 6 \(uniao estavel\)$/,
      'e exigido porque a parte e casada ou vive em uniao estavel'],
    [/^ato = 4 exige pelo menos 1 alienante \(condicao_parte = 1\)$/,
      'todo ato de transmissao precisa de quem transmite'],
    [/^ato = 4 exige pelo menos 1 adquirente \(condicao_parte = 2\)$/,
      'todo ato de transmissao precisa de quem adquire'],
    [/^obrigatorio se motivo_envio = 1 \(exceto alienante\)$/,
      'e exigido de quem nao e alienante, nos atos a partir de 02/12/2025'],
    [/^sempre obrigatorio \(pelo menos uma pessoa\)$/,
      'todo ato precisa de ao menos uma pessoa vinculada'],
    [/excede (\d+) caracteres \(tem (\d+)\)/, 'passou do limite de $1 caracteres (tem $2)'],
    [/^precisa de pelo menos (\d+) item\(ns\)$/, 'precisa de ao menos $1 item'],
  ];

  function motivoLegivel(motivo) {
    let t = String(motivo || '');
    for (const [re, troca] of MOTIVOS_LEGIVEIS) {
      if (re.test(t)) { t = t.replace(re, troca); break; }
    }
    // Sobras tecnicas que aparecem no meio de mensagens compostas.
    return t.replace(/\bmotivo_envio = 1\b/g, 'ato novo (a partir de 02/12/2025)')
      .replace(/\bcertificacao_incra = true\b/g, 'imovel certificado pelo INCRA')
      .replace(/\bimovel_possui_nome = true\b/g, 'imovel com nome')
      .replace(/\bato = 4\b/g, 'ato de transmissao')
      .replace(/\bato = 5\b/g, 'ato que altera o imovel')
      // Motivos compostos (a condicao mais uma explicacao) nao casam os padroes
      // inteiros acima: aqui so o "obrigatorio" e trocado, e o resto da frase
      // segue como o manual escreveu.
      .replace(/\bobrigatorio se\b/g, 'e exigido em')
      .replace(/\bobrigatorio\b/g, 'exigido');
  }

  /** "codigo_incra" -> "codigo da certificacao do INCRA". */
  function nomeLegivel(campo) {
    const nome = campoDoCaminho(campo);
    return NOME_DO_CAMPO[nome] || nome;
  }

  /**
   * Linha de pendencia como o oficial le: o nome do campo em portugues, o nome
   * tecnico ao lado (e o que esta no formulario) e a frase do porque.
   */
  function linhaPendencia(campo, motivo, complemento, classe) {
    const tecnico = campoDoCaminho(campo);
    const nome = nomeLegivel(campo);
    const partes = [el('b', { textContent: nome.charAt(0).toUpperCase() + nome.slice(1) }), ' '];
    if (nome !== tecnico) partes.push(el('code', { textContent: tecnico }), ' ');
    partes.push('- ' + motivoLegivel(motivo) + (complemento || ''));
    return el('li', classe ? { className: classe } : {}, partes);
  }

  /**
   * Campos que descrevem o IMOVEL e por isso se repetem em todos os atos do
   * arquivo. Um erro em qualquer um deles se resolve uma vez, na ficha do
   * imovel. O que nao esta aqui e proprio do ato (partes, valores, protocolo,
   * data, tipo) e continua apontado ato a ato.
   */
  const CAMPOS_DO_IMOVEL = new Set(['numero_matricula', 'data_matricula', 'numero_transcricao',
    'data_transcricao', 'cnm', 'situacao', 'tipo_imovel', 'tipo_matricula_transcricao',
    'contexto_urbano', 'contexto_rural', 'regime_utilizacao', 'georreferenciamento',
    'certificacao_incra', 'codigo_incra', 'sistema_referencia', 'sistema_coordenadas',
    'fuso_zona', 'centroide', 'cib', 'cif', 'ccir', 'cod_sncr', 'car', 'nirf',
    'imovel_possui_nome', 'nome_imovel', 'area_terreno_total', 'area_construida',
    'livro_matricula', 'folha_matricula', 'dados_imovel', 'tipo_logradouro', 'logradouro',
    'numero_logradouro', 'complemento', 'bairro', 'cep', 'cod_ibge_municipio', 'uf', 'area_m2']);

  /** Nome do campo no fim de um caminho ("imoveis[0].dados_imovel[0].cep" -> "cep"). */
  function campoDoCaminho(caminho) {
    return String(caminho || '').replace(/\[\d+\]/g, '').split('.').pop();
  }

  function ehCampoDoImovel(campo) {
    return CAMPOS_DO_IMOVEL.has(campoDoCaminho(campo));
  }

  /**
   * Reune, numa linha por campo, o que se repete em todos os atos; devolve o
   * resto intacto. Nao muda a validacao - so a forma de apontar.
   */
  function agrupaPorCampoDoImovel(erros, relatorio) {
    // Uma linha por CAMPO, nao por mensagem: o mesmo codigo_incra aparece como
    // pendencia da regra ("obrigatorio se certificacao_incra = true") e como
    // erro do schema ("campo obrigatorio ausente"), e para quem corrige e um
    // campo so. Os dois motivos ficam na mesma linha.
    const imovel = new Map();
    const somaImovel = (campo, motivo, ondeSchema, ondeRegra) => {
      const nome = campoDoCaminho(campo);
      const g = imovel.get(nome)
        || { campo: nome, motivos: [], atosSchema: new Set(), atosRegra: new Set() };
      // Cada motivo e traduzido ANTES de juntar: unidos, nenhuma das frases
      // casaria o padrao e "campo obrigatorio ausente" ficava cru na tela.
      const frase = motivoLegivel(motivo);
      if (frase && g.motivos.indexOf(frase) < 0) g.motivos.push(frase);
      if (ondeSchema) g.atosSchema.add(ondeSchema);
      if (ondeRegra) g.atosRegra.add(ondeRegra);
      imovel.set(nome, g);
    };

    const errosAto = (erros || []).filter((e) => {
      if (!ehCampoDoImovel(e.path)) return true;
      const item = (String(e.path || '').match(/^imoveis\[(\d+)\]/) || [])[1];
      somaImovel(e.path, e.message, item != null ? item : '?', null);
      return false;
    });

    const porAto = (relatorio || []).map((item) => Object.assign({}, item, {
      pendencias: item.pendencias.filter((p) => {
        if (!ehCampoDoImovel(p.campo)) return true;
        somaImovel(p.campo, p.motivo, null, item.ato);
        return false;
      }),
    }));

    const lista = Array.from(imovel.values()).map((g) => ({
      campo: g.campo,
      motivo: g.motivos.join(' - '),
      atos: Math.max(g.atosSchema.size, g.atosRegra.size),
    }));
    return { imovel: lista, errosAto, porAto };
  }

  function renderResultado() {
    const alvo = $('#resultado');
    alvo.textContent = '';
    const r = estado.resultado;
    if (!r) return;

    const erros = r.validacao.erros;
    // O layout repete os dados do imovel dentro de CADA ato, entao um campo
    // errado na ficha do imovel viraria uma linha por ato (nove atos, nove
    // vezes a mesma coisa). A validacao continua ato a ato; aqui as ocorrencias
    // do mesmo campo do imovel sao reunidas numa linha, dizendo quantos atos
    // ela afeta e onde se corrige. O que e proprio do ato continua no ato.
    const doImovel = agrupaPorCampoDoImovel(erros, r.relatorio);

    const errosAto = doImovel.errosAto.length;

    const pendAto = doImovel.porAto.reduce((s, x) => s + x.pendencias.length, 0);
    const partes = [];
    if (doImovel.imovel.length) partes.push(doImovel.imovel.length + ' campo(s) na ficha do imovel');
    if (pendAto) partes.push(pendAto + ' pendencia(s) em ato(s)');
    if (errosAto) partes.push(errosAto + ' erro(s) de schema em ato(s)');

    const status = el('div', { className: 'status ' + (partes.length ? 'bad' : 'ok') });
    const lista = partes.length > 1
      ? partes.slice(0, -1).join(', ') + ' e ' + partes[partes.length - 1]
      : partes[0];
    status.textContent = partes.length
      ? r.arquivo.imoveis.length + ' ato(s) - ' + lista + ' a resolver.'
      : 'Pronto para envio: ' + r.arquivo.imoveis.length + ' ato(s), 0 pendencia, 0 erro de schema.';
    alvo.appendChild(status);

    if (doImovel.imovel.length) {
      const d = el('details', { open: true });
      d.appendChild(el('summary', { textContent: 'Dados do imovel - ' + doImovel.imovel.length
        + ' campo(s) a resolver (valem para todos os atos)' }));
      const ul = el('ul', { className: 'erros' });
      for (const g of doImovel.imovel) {
        ul.appendChild(linhaPendencia(g.campo, g.motivo, explicaAusente(g.campo)
          + '. Corrija uma vez em "Dados do imovel": vale para os ' + g.atos + ' atos.'));
      }
      d.appendChild(ul);
      alvo.appendChild(d);
    }

    if (doImovel.errosAto.length) {
      const d = el('details', { open: true });
      d.appendChild(el('summary', { textContent: 'Erros de schema nos atos ('
        + doImovel.errosAto.length + ')' }));
      const ul = el('ul', { className: 'erros' });
      for (const e of doImovel.errosAto.slice(0, 200)) {
        const li = linhaPendencia(e.path, e.message, explicaAusente(e.path));
        li.appendChild(el('small', { className: 'evidencia', textContent: ' (em ' + e.path + ')' }));
        ul.appendChild(li);
      }
      if (doImovel.errosAto.length > 200) {
        ul.appendChild(el('li', { textContent: '... e mais ' + (doImovel.errosAto.length - 200) }));
      }
      d.appendChild(ul);
      alvo.appendChild(d);
    }

    for (const item of doImovel.porAto) {
      if (!item.pendencias.length && !item.avisos.length) continue;
      const d = el('details', { open: item.pendencias.length > 0 });
      d.appendChild(el('summary', { textContent: item.ato + ' - ' + item.pendencias.length
        + ' pendencia(s), ' + item.avisos.length + ' aviso(s)' }));
      const ul = el('ul', { className: 'erros' });
      for (const p of item.pendencias) {
        ul.appendChild(linhaPendencia(p.campo, p.motivo, explicaAusente(p.campo)));
      }
      for (const av of item.avisos) {
        ul.appendChild(linhaPendencia(av.campo, av.motivo, '', 'aviso-item'));
      }
      d.appendChild(ul);
      alvo.appendChild(d);
    }

    const json = JSON.stringify(r.arquivo, null, 2);
    alvo.appendChild(el('div', { className: 'acoes' }, [
      el('button', { className: 'ligado', textContent: 'Copiar JSON', onclick: () => {
        navigator.clipboard.writeText(json).then(() => alert('JSON copiado.'),
          () => alert('Nao foi possivel copiar; use o botao de baixar.'));
      } }),
      el('button', { textContent: 'Baixar JSON', onclick: () => {
        const nome = 'onr_' + (r.arquivo.cns || 'cns') + '_'
          + (estado.fichaImovel.numero_matricula || 'matricula') + '_v' + r.versao + '.json';
        const a = el('a', { href: URL.createObjectURL(new Blob([json], { type: 'application/json' })), download: nome });
        document.body.appendChild(a); a.click(); a.remove();
      } }),
    ]));
    alvo.appendChild(el('pre', { className: 'json', textContent: json }));
  }

  // ------------------------------------------- aba: validar um JSON existente

  function validarArquivoExterno(texto) {
    const alvo = $('#saida-validador');
    alvo.textContent = '';
    let dados;
    try {
      dados = JSON.parse(texto);
    } catch (e) {
      alvo.appendChild(el('div', { className: 'status bad', textContent: 'JSON invalido: ' + e.message }));
      return;
    }
    const urbano = (dados.imoveis || []).some((i) => i.tipo_imovel === 1 || i.contexto_urbano !== undefined);
    const schema = urbano ? global.ONR_SCHEMA_URBANO : global.ONR_SCHEMA_RURAL;
    const v = V.valida(schema, dados);

    const resumo = {};
    for (const e of v.erros) {
      const k = e.path.replace(/\[\d+\]/g, '[]') + ' (' + e.keyword + ')';
      resumo[k] = (resumo[k] || 0) + 1;
    }
    alvo.appendChild(el('div', { className: 'status ' + (v.valido ? 'ok' : 'bad'), textContent:
      (urbano ? 'Schema urbano' : 'Schema rural') + ' - ' + (dados.imoveis || []).length + ' imovel(is) - '
      + (v.valido ? 'valido' : v.erros.length + ' erro(s)') }));
    if (!v.valido) {
      const ul = el('ul', { className: 'erros' });
      for (const k of Object.keys(resumo).sort((a, b) => resumo[b] - resumo[a])) {
        ul.appendChild(el('li', {}, [el('b', { textContent: resumo[k] + 'x ' }), el('code', { textContent: k })]));
      }
      alvo.appendChild(ul);
      const d = el('details');
      d.appendChild(el('summary', { textContent: 'Lista completa' }));
      const ul2 = el('ul', { className: 'erros' });
      for (const e of v.erros.slice(0, 400)) {
        ul2.appendChild(el('li', {}, [el('code', { textContent: e.path }), ' - ' + e.message]));
      }
      d.appendChild(ul2);
      alvo.appendChild(d);
    }

    // Auditoria de documentos: o que o schema aceita mas esta errado no merito.
    const DOC = global.ONR_DOC;
    if (DOC) {
      const achados = DOC.auditaArquivo(dados);
      if (achados.length) {
        const det = el('details', { open: true });
        det.appendChild(el('summary', { textContent: 'CPF/CNPJ com problema de conteudo ('
          + achados.length + ') - nao detectado pelo schema' }));
        const ul = el('ul', { className: 'erros' });
        for (const a of achados) {
          const li = el('li', {}, [
            el('code', { textContent: a.path }),
            (a.ato ? ' [ato ' + a.ato + ']' : '') + (a.nome ? ' ' + a.nome : '') + ' - ' + a.message,
          ]);
          if (a.situacao === 'base_incompleta') li.className = 'aviso-item';
          ul.appendChild(li);
        }
        det.appendChild(ul);
        alvo.appendChild(det);
      } else {
        alvo.appendChild(el('p', { className: 'vazio',
          textContent: 'Todos os CPF/CNPJ conferem no digito verificador.' }));
      }
    }
  }

  // ----------------------------------------------------------------- render

  function render() {
    renderListaAtos();
    renderEstadoVigente();
    renderFichaImovel();
    renderResumoSelecao();
    renderResultado();
  }

  function informarAlturaAoAeri() {
    if (global.parent === global) return;
    const conteudo = document.querySelector('main') || document.body;
    global.parent.postMessage({
      tipo: 'AERI_MAPA_ONR_ALTURA',
      altura: Math.ceil(conteudo.getBoundingClientRect().bottom + 12),
    }, '*');
  }

  function configurarIntegracaoAeri() {
    const incorporado = global.parent !== global
      && new URLSearchParams(global.location.search).get('embedded') === '1';
    if (!incorporado) return;

    document.body.classList.add('aeri-embedded');
    const origem = $('#origem-aeri');
    origem.hidden = false;

    global.addEventListener('message', (evento) => {
      if (evento.source !== global.parent || !evento.data) return;
      const mensagem = evento.data;

      if (mensagem.tipo === 'AERI_MAPA_ONR_PING') {
        global.parent.postMessage({ tipo: 'AERI_MAPA_ONR_CARREGADO' }, '*');
        return;
      }
      if (mensagem.tipo === 'AERI_MAPA_ONR_LIMPAR') {
        $('#texto').value = '';
        origem.className = 'status ok';
        origem.textContent = 'Aguardando uma consulta do AERI.';
        lerMatricula();
        informarAlturaAoAeri();
        return;
      }
      if (mensagem.tipo !== 'AERI_MAPA_ONR_MATRICULA') return;

      try {
        const texto = String(mensagem.texto || '').trim();
        if (!texto) throw new Error('A Tri7 retornou a matricula sem texto.');
        if (mensagem.tipoImovel === 'rural' || mensagem.tipoImovel === 'urbano') {
          $('#tipo-imovel').value = mensagem.tipoImovel;
        }
        $('#texto').value = texto;
        origem.className = 'status ok';
        origem.textContent = 'Matricula ' + mensagem.numeroMatricula
          + ' recebida diretamente da Tri7. Confira os atos antes de exportar.';
        // Guardado antes da leitura: e o numero consultado no AERI, usado
        // quando o texto nao traz nenhum de onde extrair. Guarda tambem o
        // texto recebido, para o numero nao vazar caso o operador cole outra
        // matricula por cima depois.
        estado.numeroConsultado = String(mensagem.numeroMatricula || '').trim() || null;
        estado.textoConsultado = texto;
        lerMatricula();
        global.parent.postMessage({
          tipo: 'AERI_MAPA_ONR_PROCESSADO',
          numeroMatricula: mensagem.numeroMatricula,
          totalAtos: estado.atos.length,
        }, '*');
      } catch (erro) {
        origem.className = 'status bad';
        origem.textContent = erro.message || 'Nao foi possivel converter a matricula.';
        global.parent.postMessage({
          tipo: 'AERI_MAPA_ONR_ERRO',
          mensagem: origem.textContent,
        }, '*');
      }
      informarAlturaAoAeri();
    });

    if (global.ResizeObserver) {
      new ResizeObserver(() => informarAlturaAoAeri()).observe(document.querySelector('main'));
    }
    global.parent.postMessage({ tipo: 'AERI_MAPA_ONR_CARREGADO' }, '*');
  }

  function iniciar() {
    configurarIntegracaoAeri();
    $('#btn-ler').addEventListener('click', lerMatricula);
    $('#btn-gerar').addEventListener('click', gerar);
    $('#btn-exemplo').addEventListener('click', () => {
      $('#tipo-imovel').value = 'rural';
      $('#texto').value = global.EXEMPLO_RURAL || global.FIXTURE_1118 || '';
      lerMatricula();
    });
    $('#btn-exemplo-urbano').addEventListener('click', () => {
      $('#tipo-imovel').value = 'urbano';
      $('#texto').value = global.EXEMPLO_URBANO || global.FIXTURE_24098 || '';
      lerMatricula();
    });
    // Trocar o tipo relê a matricula: os campos e o schema mudam.
    $('#tipo-imovel').addEventListener('change', () => {
      estado.fichaImovel = {};
      if ($('#texto').value.trim()) lerMatricula(); else render();
    });
    $('#btn-validar').addEventListener('click', () => validarArquivoExterno($('#json-externo').value));
    $('#arquivo-externo').addEventListener('change', (ev) => {
      const arq = ev.target.files && ev.target.files[0];
      if (!arq) return;
      const fr = new FileReader();
      fr.onload = () => { $('#json-externo').value = String(fr.result); validarArquivoExterno(String(fr.result)); };
      fr.readAsText(arq, 'utf-8');
    });
    for (const b of document.querySelectorAll('[data-aba]')) {
      b.addEventListener('click', () => {
        const alvo = b.getAttribute('data-aba');
        for (const s of document.querySelectorAll('section[data-painel]')) {
          s.hidden = s.getAttribute('data-painel') !== alvo;
        }
        for (const o of document.querySelectorAll('[data-aba]')) o.classList.toggle('ligado', o === b);
      });
    }
    // Os exemplos sao opcionais: quem clonar o projeto sem a pasta `exemplos`
    // simplesmente nao ve os botoes, em vez de clicar num botao que nao faz nada.
    if (!global.EXEMPLO_RURAL && !global.FIXTURE_1118) $('#btn-exemplo').hidden = true;
    if (!global.EXEMPLO_URBANO && !global.FIXTURE_24098) $('#btn-exemplo-urbano').hidden = true;

    const faltando = ['ONR_SCHEMA_RURAL', 'ONR_SCHEMA_URBANO'].filter((k) => !global[k]);
    if (faltando.length) {
      $('#alerta-carga').hidden = false;
      $('#alerta-carga').textContent = 'Schemas nao carregados (' + faltando.join(', ')
        + '). Abra o arquivo index.html a partir da pasta do projeto, sem mover os arquivos.';
    }
    render();
  }

  document.addEventListener('DOMContentLoaded', iniciar);
})(typeof window !== 'undefined' ? window : globalThis);
