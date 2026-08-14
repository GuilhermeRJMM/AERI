/**
 * Montagem do JSON de importacao ONR a partir das fichas de ato.
 *
 * Divisao de responsabilidade:
 *  - validator.js  -> forma (o schema oficial do Anexo II diz o que o sistema aceita)
 *  - builder.js    -> conteudo (as regras condicionais do manual v1.3.0, que o
 *                     schema NAO expressa: "obrigatorio se motivo_envio = 1", etc.)
 *
 * Nada e chutado: cada campo que a regra exige e nao veio preenchido sai como
 * pendencia com o motivo, para decisao humana antes da exportacao.
 */
(function (global) {
  'use strict';

  const VERSAO_SCHEMA_PUBLICADO = '1.2.0'; // const do Anexo II
  const VERSAO_MANUAL = '1.3.0';           // Anexo I + ERRATA 01

  // Campos que so existem a partir do manual 1.3.0 e que o schema publicado
  // (1.2.0) rejeita por additionalProperties: false.
  const CAMPOS_SOMENTE_130 = ['decisao_jud', 'nao_CPF'];

  // ---------------------------------------------------------------- normalizacao

  function soDigitos(v) {
    return v === null || v === undefined ? null : String(v).replace(/\D/g, '');
  }

  /** CPF/CNPJ -> 11 ou 14 digitos. Rejeita padding com espacos (bug real do legado). */
  function limpaCpfCnpj(v) {
    if (v === null || v === undefined) return null;
    const d = soDigitos(v);
    if (d.length === 11 || d.length === 14) return d;
    return { invalido: true, original: String(v), digitos: d.length };
  }

  /** CEP -> 8 digitos (ERRATA 01: mascara oficial 00000-000, sem ponto). */
  function limpaCep(v) {
    const d = soDigitos(v);
    return d && d.length === 8 ? d : null;
  }

  /** CNM -> 000000.0.0000000-00 (aceita entrada com ou sem mascara). */
  function formataCnm(v) {
    if (!v) return null;
    const d = soDigitos(v);
    if (d.length !== 16) return null;
    return d.slice(0, 6) + '.' + d.slice(6, 7) + '.' + d.slice(7, 14) + '-' + d.slice(14);
  }

  function limpaData(v) {
    if (!v) return null;
    const m = /^(\d{1,2})\/(\d{1,2})\/(\d{4})$/.exec(String(v).trim());
    if (!m) return null;
    return String(+m[1]).padStart(2, '0') + '/' + String(+m[2]).padStart(2, '0') + '/' + m[3];
  }

  function numero(v) {
    if (v === null || v === undefined || v === '') return null;
    if (typeof v === 'number') return Number.isFinite(v) ? v : null;
    const n = parseFloat(String(v).replace(/\./g, '').replace(',', '.'));
    return Number.isFinite(n) ? n : null;
  }

  function vazio(v) {
    return v === null || v === undefined || (typeof v === 'string' && v.trim() === '');
  }

  /** Remove chaves nulas/vazias e objetos/arrays que ficariam sem conteudo. */
  function limpaObjeto(obj) {
    if (Array.isArray(obj)) {
      const itens = obj.map(limpaObjeto).filter((x) => x !== undefined);
      return itens.length ? itens : undefined;
    }
    if (obj !== null && typeof obj === 'object') {
      const saida = {};
      for (const k of Object.keys(obj)) {
        const v = limpaObjeto(obj[k]);
        if (v !== undefined) saida[k] = v;
      }
      return Object.keys(saida).length ? saida : undefined;
    }
    return vazio(obj) ? undefined : obj;
  }

  // ------------------------------------------------------------ estado corrente

  /**
   * Percorre os atos em ordem e mantem o estado vigente da matricula.
   * E o que permite processar so o ato 57 tendo lido a matricula inteira:
   * area, CAR, CCIR, CIB e regime de bens de cada pessoa vem do ultimo ato que
   * de fato alterou aquele dado - nunca do estado final aplicado a um ato antigo.
   *
   * @param {Array<{numero:string, tipo:number, campos:object, pessoas?:Array}>} atos
   *        em ordem cronologica de pratica (nao de numeracao).
   */
  function estadoCorrente(atos) {
    const estado = {
      area_terreno_total: null,
      car: null,
      ccir: null,
      cod_sncr: null,
      cib: null,
      nirf: null,
      nome_imovel: null,
      situacao: '1',
      // CPF -> {nome, estado_civil, regime_bens, percentual, relacao_juridica}
      pessoas: new Map(),
      ultimoAto: null,
      historico: [],
    };

    for (const ato of atos || []) {
      const c = ato.campos || {};
      const anota = (campo, valor) => {
        if (vazio(valor)) return;
        if (JSON.stringify(estado[campo]) === JSON.stringify(valor)) return;
        estado.historico.push({ ato: ato.numero, campo, de: estado[campo], para: valor });
        estado[campo] = valor;
      };

      anota('area_terreno_total', c.area_terreno_total);
      anota('car', c.car);
      anota('ccir', c.ccir);
      anota('cod_sncr', c.cod_sncr);
      anota('cib', c.cib);
      anota('nirf', c.nirf);
      anota('nome_imovel', c.nome_imovel);
      if (!vazio(c.situacao)) anota('situacao', String(c.situacao));

      for (const p of ato.pessoas || []) {
        const chave = p.cpf_cnpj || ('nome:' + (p.nome_completo || '').toUpperCase());
        const anterior = estado.pessoas.get(chave) || {};
        estado.pessoas.set(chave, {
          nome_completo: p.nome_completo || anterior.nome_completo || null,
          cpf_cnpj: p.cpf_cnpj || anterior.cpf_cnpj || null,
          // Regime/estado civil sao herdados quando o ato nao os repete.
          estado_civil: p.estado_civil != null ? p.estado_civil : (anterior.estado_civil ?? null),
          regime_bens: p.regime_bens != null ? p.regime_bens : (anterior.regime_bens ?? null),
          relacao_juridica: p.relacao_juridica != null ? p.relacao_juridica : (anterior.relacao_juridica ?? null),
          percentual: p.percentual != null ? p.percentual : (anterior.percentual ?? null),
          visto_em: (anterior.visto_em || []).concat([ato.numero]),
        });
      }
      estado.ultimoAto = ato.numero;
    }
    return estado;
  }

  // ----------------------------------------------------------- regras do manual

  /**
   * Regras condicionais do manual v1.3.0 que o JSON Schema nao cobre.
   * @returns {Array<{campo:string, motivo:string}>} pendencias
   */
  function regrasCondicionais(imovel, opcoes) {
    const rural = (opcoes && opcoes.tipo) !== 'urbano';
    const p = [];
    const falta = (campo, motivo) => { if (vazio(imovel[campo])) p.push({ campo, motivo }); };

    // decisao_jud = true dispensa tudo menos identificacao (manual v1.3.0).
    if (imovel.decisao_jud === true) {
      falta('tipo_imovel', 'sempre obrigatorio');
      if (vazio(imovel.numero_matricula) && vazio(imovel.numero_transcricao)) {
        p.push({ campo: 'numero_matricula', motivo: 'obrigatorio (ou numero_transcricao) mesmo com decisao_jud' });
      }
      return p;
    }

    falta('tipo_imovel', 'sempre obrigatorio');
    falta('motivo_envio', 'sempre obrigatorio');
    falta(rural ? 'contexto_rural' : 'contexto_urbano', 'sempre obrigatorio');
    if (imovel.georreferenciamento === undefined || imovel.georreferenciamento === null) {
      p.push({ campo: 'georreferenciamento', motivo: 'sempre obrigatorio (true/false)' });
    }

    if (imovel.tipo_matricula_transcricao === 1) {
      falta('numero_matricula', 'obrigatorio se tipo_matricula_transcricao = 1');
      falta('data_matricula', 'obrigatorio se tipo_matricula_transcricao = 1');
      falta('cnm', 'obrigatorio se tipo_matricula_transcricao = 1');
      falta('situacao', 'obrigatorio se tipo_matricula_transcricao = 1');
    } else if (imovel.tipo_matricula_transcricao === 2) {
      falta('numero_transcricao', 'obrigatorio se tipo_matricula_transcricao = 2');
      falta('data_transcricao', 'obrigatorio se tipo_matricula_transcricao = 2');
    } else {
      p.push({ campo: 'tipo_matricula_transcricao', motivo: 'sempre obrigatorio (1 matricula / 2 transcricao)' });
    }

    // ato = 2 (abertura de oficio/decisao judicial): so identificacao e exigida.
    if (imovel.ato === 2) return p;

    if (imovel.motivo_envio === 1) {
      falta('tipo_ato', 'obrigatorio se motivo_envio = 1');
      falta('numero_ato', 'obrigatorio se motivo_envio = 1');
      falta('ato', 'obrigatorio se motivo_envio = 1');
      falta('data_ato', 'obrigatorio se motivo_envio = 1');
      falta('area_terreno_total', 'obrigatorio se motivo_envio = 1');
      if (rural) {
        falta('cib', 'obrigatorio se motivo_envio = 1');
        falta('cod_sncr', 'obrigatorio se motivo_envio = 1');
        falta('car', 'obrigatorio se motivo_envio = 1');
      } else {
        falta('cif', 'obrigatorio se motivo_envio = 1. CIF = Cadastro Imobiliario Fiscal, '
          + 'o numero do imovel na Prefeitura (o mesmo do IPTU). Na matricula ele aparece '
          + 'como "CCI n.º ..." nas averbacoes de designacao cadastral');
      }
    }

    if (imovel.ato === 4) {
      falta('alteracao_titularidade', 'obrigatorio se ato = 4');
      falta('valor_transacao', 'obrigatorio se ato = 4');
      if (imovel.valor_imposto === undefined || imovel.valor_imposto === null) {
        p.push({ campo: 'valor_imposto', motivo: 'obrigatorio se ato = 4' });
      }
    }
    if (imovel.ato === 5) falta('alteracao_imovel', 'obrigatorio se ato = 5');

    if (!rural && imovel.contexto_urbano === 2 && imovel.imovel_possui_nome === true) {
      falta('nome_imovel', 'obrigatorio se imovel_possui_nome = true');
    }

    if (rural) {
      if (imovel.certificacao_incra === undefined || imovel.certificacao_incra === null) {
        p.push({ campo: 'certificacao_incra', motivo: 'sempre obrigatorio (true/false)' });
      }
      if (imovel.certificacao_incra === true) falta('codigo_incra', 'obrigatorio se certificacao_incra = true');
      if (imovel.imovel_possui_nome === undefined || imovel.imovel_possui_nome === null) {
        p.push({ campo: 'imovel_possui_nome', motivo: 'sempre obrigatorio (true/false)' });
      }
      if (imovel.imovel_possui_nome === true) falta('nome_imovel', 'obrigatorio se imovel_possui_nome = true');

      if (imovel.contexto_rural === 2) {
        falta('regime_utilizacao', 'obrigatorio no contexto 2 (Uniao)');
        if (imovel.regime_utilizacao === 1 || imovel.regime_utilizacao === 2) {
          falta('cat', 'obrigatorio se regime_utilizacao = 1 (Aforamento) ou 2 (Ocupacao)');
        }
        if (imovel.motivo_envio === 1) falta('area_terreno_uniao', 'obrigatorio se motivo_envio = 1 no contexto Uniao');
      }
      if (imovel.contexto_rural === 3) {
        for (const campo of ['autorizacao_incra', 'faixa_fronteira', 'area_sn']) {
          if (imovel[campo] === undefined || imovel[campo] === null) {
            p.push({ campo, motivo: 'sempre obrigatorio no contexto 3 (Estrangeiros)' });
          }
        }
      }
    }

    if (imovel.valor_imposto !== undefined && imovel.valor_imposto !== null
        && ((rural && imovel.contexto_rural === 2) || (!rural && imovel.contexto_urbano === 2))) {
      falta('base_calculo_itbi', 'obrigatorio se valor_imposto preenchido (contexto Uniao)');
    }

    // dados_imovel: cod_ibge_municipio e uf sao obrigatorios sempre.
    const enderecos = imovel.dados_imovel || [];
    if (!enderecos.length) {
      p.push({ campo: 'dados_imovel', motivo: 'sempre obrigatorio (pelo menos um endereco)' });
    }
    enderecos.forEach((e, i) => {
      if (vazio(e.cod_ibge_municipio)) {
        p.push({ campo: 'dados_imovel[' + i + '].cod_ibge_municipio', motivo: 'sempre obrigatorio (7 digitos)' });
      }
      if (vazio(e.uf)) {
        p.push({ campo: 'dados_imovel[' + i + '].uf', motivo: 'sempre obrigatorio (2 digitos)' });
      }
      // No urbano o schema exige o endereco completo, nao so o municipio.
      if (!rural) {
        for (const campo of ['tipo_logradouro', 'logradouro', 'numero_logradouro', 'cep', 'area_m2']) {
          if (vazio(e[campo])) {
            p.push({ campo: 'dados_imovel[' + i + '].' + campo,
              motivo: 'obrigatorio no imovel urbano (exigido pelo schema)' });
          }
        }
      }
    });

    // dados_pessoa
    const pessoas = imovel.dados_pessoa || [];
    if (!pessoas.length) {
      p.push({ campo: 'dados_pessoa', motivo: 'sempre obrigatorio (pelo menos uma pessoa)' });
    }
    pessoas.forEach((pe, i) => {
      const em = (campo, motivo) => p.push({ campo: 'dados_pessoa[' + i + '].' + campo, motivo });
      if (imovel.motivo_envio === 1) {
        if (vazio(pe.nome_completo)) em('nome_completo', 'obrigatorio se motivo_envio = 1');
        if (vazio(pe.cpf_cnpj) && pe.nao_CPF !== true) {
          em('cpf_cnpj', 'obrigatorio se motivo_envio = 1 (ou marcar nao_CPF = true)');
        }
        if (pe.estrangeiro === undefined || pe.estrangeiro === null) {
          em('estrangeiro', 'obrigatorio se motivo_envio = 1 (true/false)');
        }
        if (pe.percentual === undefined || pe.percentual === null) {
          em('percentual', 'obrigatorio se motivo_envio = 1');
        }
        // Alienante nao precisa de relacao_juridica (v1.2.0+).
        if (vazio(pe.relacao_juridica) && pe.condicao_parte !== 1) {
          em('relacao_juridica', 'obrigatorio se motivo_envio = 1 (exceto alienante)');
        }
      }
      if (vazio(pe.estado_civil)) em('estado_civil', 'sempre obrigatorio');
      if (pe.estado_civil === 2 || pe.estado_civil === 6) {
        if (vazio(pe.regime_bens)) em('regime_bens', 'obrigatorio se estado_civil = 2 (casado) ou 6 (uniao estavel)');
      }
      if (!vazio(pe.relacao_juridica) && vazio(pe.data_inicio_rel_juridica)) {
        em('data_inicio_rel_juridica', 'obrigatorio se relacao_juridica preenchida');
      }
      if (pe.estrangeiro === true && vazio(pe.nacionalidade)) {
        em('nacionalidade', 'obrigatorio se estrangeiro = true (cod IBGE do pais)');
      }
      if (rural && imovel.contexto_rural === 3 && vazio(pe.filhos_brasileiros)) {
        em('filhos_brasileiros', 'obrigatorio no contexto 3 (Estrangeiros)');
      }
    });

    // ato = 4 exige ao menos 1 alienante e 1 adquirente (v1.2.0+).
    if (imovel.motivo_envio === 1 && imovel.ato === 4) {
      const temAlienante = pessoas.some((x) => x.condicao_parte === 1);
      const temAdquirente = pessoas.some((x) => x.condicao_parte === 2);
      if (!temAlienante) p.push({ campo: 'dados_pessoa', motivo: 'ato = 4 exige pelo menos 1 alienante (condicao_parte = 1)' });
      if (!temAdquirente) p.push({ campo: 'dados_pessoa', motivo: 'ato = 4 exige pelo menos 1 adquirente (condicao_parte = 2)' });
    }

    return p;
  }

  /** Checagem de dominio dos enums (o schema oficial nao valida enums). */
  function validaEnums(imovel, opcoes) {
    const E = global.ONR_ENUMS;
    if (!E) return [];
    const rural = (opcoes && opcoes.tipo) !== 'urbano';
    const erros = [];
    const ver = (campo, enumNome, valor, prefixo) => {
      if (vazio(valor)) return;
      const n = typeof valor === 'string' ? parseInt(valor, 10) : valor;
      if (!E.valido(enumNome, n)) {
        erros.push({ campo: (prefixo || '') + campo, motivo: 'valor fora do enum ' + enumNome + ': ' + JSON.stringify(valor) });
      }
    };
    ver('tipo_imovel', 'tipo_imovel', imovel.tipo_imovel);
    ver(rural ? 'contexto_rural' : 'contexto_urbano', rural ? 'contexto_rural' : 'contexto_urbano',
      rural ? imovel.contexto_rural : imovel.contexto_urbano);
    ver('motivo_envio', 'motivo_envio', imovel.motivo_envio);
    ver('tipo_matricula_transcricao', 'tipo_matricula_transcricao', imovel.tipo_matricula_transcricao);
    ver('situacao', 'situacao', imovel.situacao);
    ver('tipo_ato', 'tipo_ato', imovel.tipo_ato);
    ver('ato', 'ato', imovel.ato);
    ver('alteracao_titularidade', 'alteracao_titularidade', imovel.alteracao_titularidade);
    ver('alteracao_imovel', 'alteracao_imovel', imovel.alteracao_imovel);
    ver('regime_utilizacao', 'regime_utilizacao', imovel.regime_utilizacao);
    ver('onerosa_nao_onerosa', 'onerosa_nao_onerosa', imovel.onerosa_nao_onerosa);
    ver('sistema_coordenadas', 'sistema_coordenadas', imovel.sistema_coordenadas);
    ver('fuso_zona', 'fuso_zona', imovel.fuso_zona);
    ver('sistema_referencia', 'sistema_referencia', imovel.sistema_referencia);
    ver('categoria_poligono', 'categoria_poligono', imovel.categoria_poligono);
    if (imovel.area_terreno_total) ver('unidade', 'unidade_area', imovel.area_terreno_total.unidade, 'area_terreno_total.');
    if (imovel.area_terreno_uniao) ver('unidade', 'unidade_area', imovel.area_terreno_uniao.unidade, 'area_terreno_uniao.');
    (imovel.dados_pessoa || []).forEach((pe, i) => {
      const pref = 'dados_pessoa[' + i + '].';
      ver('estado_civil', 'estado_civil', pe.estado_civil, pref);
      ver('regime_bens', 'regime_bens', pe.regime_bens, pref);
      ver('relacao_juridica', 'relacao_juridica', pe.relacao_juridica, pref);
      ver('condicao_parte', 'condicao_parte', pe.condicao_parte, pref);
      ver('genero', 'genero', pe.genero, pref);
      ver('filhos_brasileiros', 'filhos_brasileiros', pe.filhos_brasileiros, pref);
    });
    (imovel.dados_imovel || []).forEach((e, i) => {
      if (!vazio(e.uf) && !E.UF[e.uf]) {
        erros.push({ campo: 'dados_imovel[' + i + '].uf', motivo: 'codigo de UF inexistente: ' + e.uf });
      }
    });
    return erros;
  }

  // -------------------------------------------------------------------- montagem

  /**
   * Monta um item de `imoveis` a partir de uma ficha de ato.
   * A ficha e o resultado do parser + revisao humana; aqui nada e inventado.
   *
   * @param {object} ficha
   * @param {object} [opcoes] {tipo:'rural'|'urbano', versao:'1.2.0'|'1.3.0'}
   * @returns {{imovel:object, pendencias:Array, avisos:Array}}
   */
  function montaImovel(ficha, opcoes) {
    const opt = Object.assign({ tipo: 'rural', versao: VERSAO_SCHEMA_PUBLICADO }, opcoes || {});
    const rural = opt.tipo !== 'urbano';
    const avisos = [];
    const f = ficha || {};

    const dataAto = limpaData(f.data_ato);
    // motivo_envio e recalculado sempre: e data, nao opiniao.
    const motivoCalculado = global.ONR_PARSER ? global.ONR_PARSER.motivoEnvio(dataAto) : null;
    if (motivoCalculado !== null && f.motivo_envio != null && +f.motivo_envio !== motivoCalculado) {
      avisos.push({
        campo: 'motivo_envio',
        motivo: 'recalculado para ' + motivoCalculado + ' a partir de data_ato ' + dataAto
          + ' (valor informado era ' + f.motivo_envio + ')',
      });
    }
    const motivo = motivoCalculado !== null ? motivoCalculado : (f.motivo_envio != null ? +f.motivo_envio : null);

    const pendenciasDoc = [];
    const pessoas = (f.dados_pessoa || []).map((pe, i) => {
      const doc = limpaCpfCnpj(pe.cpf_cnpj);
      if (doc && doc.invalido) {
        avisos.push({
          campo: 'dados_pessoa.cpf_cnpj',
          motivo: 'documento descartado por ser invalido ('
            + JSON.stringify(doc.original) + ' -> ' + doc.digitos + ' digitos; exige 11 ou 14)',
        });
      }
      // Digito verificador: o schema so confere formato, nao a conta.
      const DOC = global.ONR_DOC;
      if (DOC && !vazio(pe.cpf_cnpj)) {
        const r = DOC.confere(pe.cpf_cnpj);
        if (r.situacao === 'dv_invalido' || r.situacao === 'base_incompleta') {
          pendenciasDoc.push({
            campo: 'dados_pessoa[' + i + '].cpf_cnpj',
            motivo: r.mensagem,
            sugestao: r.sugestao || null,
          });
        }
      }
      const saida = {
        condicao_parte: pe.condicao_parte != null ? +pe.condicao_parte : null,
        nome_completo: pe.nome_completo ? String(pe.nome_completo).trim() : null,
        cpf_cnpj: doc && !doc.invalido ? doc : null,
        estrangeiro: pe.estrangeiro === undefined ? null : !!pe.estrangeiro,
        nacionalidade: pe.nacionalidade != null ? +pe.nacionalidade : null,
        estado_civil: pe.estado_civil != null ? +pe.estado_civil : null,
        regime_bens: pe.regime_bens != null ? +pe.regime_bens : null,
        relacao_juridica: pe.relacao_juridica != null ? +pe.relacao_juridica : null,
        data_inicio_rel_juridica: limpaData(pe.data_inicio_rel_juridica),
        data_fim_rel_juridica: limpaData(pe.data_fim_rel_juridica),
        percentual: numero(pe.percentual),
        tipo_logradouro: pe.tipo_logradouro != null ? +pe.tipo_logradouro : null,
        logradouro: pe.logradouro || null,
        numero_logradouro: pe.numero_logradouro || null,
        bairro: pe.bairro || null,
        complemento: pe.complemento || null,
        cep: limpaCep(pe.cep),
        cod_ibge_municipio: pe.cod_ibge_municipio != null ? +pe.cod_ibge_municipio : null,
        uf: pe.uf != null ? +pe.uf : null,
        rnm: pe.rnm || null,
        data_rnm: limpaData(pe.data_rnm),
        emissor_rnm: pe.emissor_rnm || null,
        passaporte: pe.passaporte || null,
        genero: pe.genero != null ? +pe.genero : null,
        filhos_brasileiros: pe.filhos_brasileiros != null ? +pe.filhos_brasileiros : null,
      };
      if (pe.nao_CPF === true) saida.nao_CPF = true;
      return saida;
    });

    // O urbano tem endereco completo (e o schema exige tipo/numero/CEP); o rural
    // aceita so logradouro, complemento e CEP.
    const enderecos = (f.dados_imovel || []).map((e) => {
      const base = {
        logradouro: e.logradouro || null,
        complemento: e.complemento || null,
        cep: limpaCep(e.cep),
        cod_ibge_municipio: e.cod_ibge_municipio != null ? +e.cod_ibge_municipio : null,
        uf: e.uf != null ? +e.uf : null,
      };
      if (rural) return base;
      return Object.assign(base, {
        tipo_logradouro: e.tipo_logradouro != null ? +e.tipo_logradouro : null,
        numero_logradouro: e.numero_logradouro != null ? String(e.numero_logradouro) : null,
        bairro: e.bairro || null,
        area_m2: numero(e.area_m2),
      });
    });

    const confrontantes = (f.dados_confrontantes || [])
      .map((c) => ({
        numero_matricula_confrontante: c.numero_matricula_confrontante
          ? String(c.numero_matricula_confrontante) : null,
        nome_proprietario_confrontante: c.nome_proprietario_confrontante || null,
      }))
      .filter((c) => c.numero_matricula_confrontante || c.nome_proprietario_confrontante);

    const imovel = {
      tipo_imovel: rural ? 2 : 1,
      georreferenciamento: f.georreferenciamento === undefined ? null : !!f.georreferenciamento,
      sistema_coordenadas: f.sistema_coordenadas != null ? +f.sistema_coordenadas : null,
      fuso_zona: f.fuso_zona != null ? +f.fuso_zona : null,
      sistema_referencia: f.sistema_referencia != null ? +f.sistema_referencia : null,
      coordenadas: f.coordenadas || null,
      numero_poligono: f.numero_poligono != null ? +f.numero_poligono : null,
      categoria_poligono: f.categoria_poligono != null ? +f.categoria_poligono : null,
      motivo_envio: motivo,
      protocolo_prenotacao: f.protocolo_prenotacao != null ? +f.protocolo_prenotacao : null,
      data_protocolo_prenotacao: limpaData(f.data_protocolo_prenotacao),
      tipo_matricula_transcricao: f.tipo_matricula_transcricao != null ? +f.tipo_matricula_transcricao : 1,
      numero_matricula: f.numero_matricula != null ? String(f.numero_matricula).replace(/\D/g, '') : null,
      data_matricula: limpaData(f.data_matricula),
      cnm: formataCnm(f.cnm),
      situacao: f.situacao != null ? String(f.situacao) : null,
      numero_transcricao: f.numero_transcricao || null,
      data_transcricao: limpaData(f.data_transcricao),
      livro_transcricao: f.livro_transcricao || null,
      folha_transcricao: f.folha_transcricao || null,
      tipo_ato: f.tipo_ato != null ? +f.tipo_ato : null,
      numero_ato: f.numero_ato != null ? String(f.numero_ato) : null,
      ato: f.ato != null ? +f.ato : null,
      data_ato: dataAto,
      alteracao_titularidade: f.alteracao_titularidade != null ? +f.alteracao_titularidade : null,
      alteracao_imovel: f.alteracao_imovel != null ? +f.alteracao_imovel : null,
      valor_transacao: numero(f.valor_transacao),
      valor_imposto: numero(f.valor_imposto),
      area_terreno_total: f.area_terreno_total
        ? { valor: numero(f.area_terreno_total.valor), unidade: +f.area_terreno_total.unidade }
        : null,
      dados_imovel: enderecos,
      dados_pessoa: pessoas,
      dados_confrontantes: confrontantes,
    };

    if (rural) {
      Object.assign(imovel, {
        contexto_rural: f.contexto_rural != null ? +f.contexto_rural : 1,
        cib: f.cib || null,
        ccir: f.ccir ? soDigitos(f.ccir) : null,
        cod_sncr: f.cod_sncr ? soDigitos(f.cod_sncr) : null,
        certificacao_incra: f.certificacao_incra === undefined ? null : !!f.certificacao_incra,
        codigo_incra: f.codigo_incra || null,
        car: f.car || null,
        imovel_possui_nome: f.imovel_possui_nome === undefined ? null : !!f.imovel_possui_nome,
        nome_imovel: f.nome_imovel || null,
      });
      if (f.contexto_rural === 2) {
        Object.assign(imovel, {
          regime_utilizacao: f.regime_utilizacao != null ? +f.regime_utilizacao : null,
          onerosa_nao_onerosa: f.onerosa_nao_onerosa != null ? +f.onerosa_nao_onerosa : null,
          rip: f.rip || null,
          cat: f.cat || null,
          base_calculo_itbi: numero(f.base_calculo_itbi),
          area_terreno_uniao: f.area_terreno_uniao
            ? { valor: numero(f.area_terreno_uniao.valor), unidade: +f.area_terreno_uniao.unidade }
            : null,
          fracao: numero(f.fracao),
          nome_representante_legal: f.nome_representante_legal || null,
          cpf_representante_legal: f.cpf_representante_legal ? soDigitos(f.cpf_representante_legal) : null,
          data_averbacao: limpaData(f.data_averbacao),
        });
      }
      if (f.contexto_rural === 3) {
        Object.assign(imovel, {
          autorizacao_incra: f.autorizacao_incra === undefined ? null : !!f.autorizacao_incra,
          faixa_fronteira: f.faixa_fronteira === undefined ? null : !!f.faixa_fronteira,
          area_sn: f.area_sn === undefined ? null : !!f.area_sn,
        });
      }
    } else {
      Object.assign(imovel, {
        contexto_urbano: f.contexto_urbano != null ? +f.contexto_urbano : 1,
        cif: f.cif || null,
        cib: f.cib || null,
        certificacao_incra: f.certificacao_incra === undefined ? null : !!f.certificacao_incra,
        livro_matricula: f.livro_matricula || null,
        folha_matricula: f.folha_matricula || null,
      });
      if (f.contexto_urbano === 2) {
        // Atencao: no urbano, `imovel_possui_nome`/`nome_imovel` existem SO no
        // ramo da Uniao do schema. No contexto Padrao eles reprovam o arquivo
        // por additionalProperties: false.
        Object.assign(imovel, {
          imovel_possui_nome: f.imovel_possui_nome === undefined ? null : !!f.imovel_possui_nome,
          nome_imovel: f.nome_imovel || null,
          regime_utilizacao: f.regime_utilizacao != null ? +f.regime_utilizacao : null,
          onerosa_nao_onerosa: f.onerosa_nao_onerosa != null ? +f.onerosa_nao_onerosa : null,
          rip: f.rip || null,
          cat: f.cat || null,
          base_calculo_itbi: numero(f.base_calculo_itbi),
          area_terreno_uniao: f.area_terreno_uniao
            ? { valor: numero(f.area_terreno_uniao.valor), unidade: +f.area_terreno_uniao.unidade }
            : null,
          fracao: numero(f.fracao),
          nome_representante_legal: f.nome_representante_legal || null,
          cpf_representante_legal: f.cpf_representante_legal ? soDigitos(f.cpf_representante_legal) : null,
        });
      }
    }

    if (f.decisao_jud === true) imovel.decisao_jud = true;

    // As pendencias sao avaliadas ANTES da limpeza, sobre a intencao declarada.
    // CNM com digito verificador errado: o schema so confere o formato.
    if (global.ONR_DOC && !vazio(imovel.cnm)) {
      const rc = global.ONR_DOC.confereCnm(imovel.cnm);
      if (rc.situacao === 'dv_invalido') pendenciasDoc.push({ campo: 'cnm', motivo: rc.mensagem });
    }

    // Quando ha diagnostico especifico do documento ("CPF sem os digitos
    // verificadores"), a pendencia generica de campo obrigatorio para o mesmo
    // campo so atrapalha: o dado FOI informado, esta e outra conversa.
    const camposComDiagnostico = new Set(pendenciasDoc.map((p) => p.campo));
    const pendencias = regrasCondicionais(imovel, { tipo: opt.tipo })
      .concat(validaEnums(imovel, { tipo: opt.tipo }))
      .filter((p) => !(camposComDiagnostico.has(p.campo) && /^obrigatorio/.test(p.motivo)))
      .concat(pendenciasDoc);

    let saida = limpaObjeto(imovel) || {};

    if (opt.versao === VERSAO_SCHEMA_PUBLICADO) {
      for (const campo of CAMPOS_SOMENTE_130) {
        if (saida[campo] !== undefined) {
          delete saida[campo];
          avisos.push({
            campo,
            motivo: 'removido: existe no manual ' + VERSAO_MANUAL + ' mas o schema publicado ('
              + VERSAO_SCHEMA_PUBLICADO + ') rejeita campos nao previstos',
          });
        }
      }
      (saida.dados_pessoa || []).forEach((pe) => { delete pe.nao_CPF; });
    }

    return { imovel: saida, pendencias, avisos };
  }

  /** Monta o arquivo completo (raiz + imoveis). */
  function montaArquivo(cns, imoveis, versao) {
    return {
      version: versao || VERSAO_SCHEMA_PUBLICADO,
      cns: soDigitos(cns),
      imoveis: imoveis || [],
    };
  }

  global.ONR_BUILDER = {
    montaImovel,
    montaArquivo,
    estadoCorrente,
    regrasCondicionais,
    validaEnums,
    VERSAO_SCHEMA_PUBLICADO,
    VERSAO_MANUAL,
    _internos: { limpaCpfCnpj, limpaCep, formataCnm, limpaData, numero, limpaObjeto },
  };
})(typeof window !== 'undefined' ? window : globalThis);
