/**
 * Validador JSON Schema - subconjunto exato usado pelos schemas oficiais do ONR.
 *
 * Palavras-chave presentes nos dois schemas do Anexo II (levantadas por
 * contagem sobre os arquivos): type, const, anyOf, allOf, properties, required,
 * additionalProperties, pattern, maxLength, minLength, minimum, maximum,
 * minItems, items, description. Nao ha $ref, enum, if/then nem oneOf, o que
 * permite um validador pequeno e auditavel em vez de uma dependencia externa
 * (o projeto roda sem Node/npm - ver README).
 *
 * O ONR expressa condicionais como anyOf de ramos com `const`. Um erro dentro
 * de um anyOf que falha inteiro produz uma cascata inutil de mensagens, entao
 * usamos "branch scoring": reportamos apenas o ramo que chegou mais perto.
 */
(function (global) {
  'use strict';

  function tipoDe(v) {
    if (v === null) return 'null';
    if (Array.isArray(v)) return 'array';
    return typeof v; // string | number | boolean | object | undefined
  }

  function tipoConfere(esperado, v) {
    switch (esperado) {
      case 'string': return typeof v === 'string';
      case 'number': return typeof v === 'number' && Number.isFinite(v);
      case 'integer': return typeof v === 'number' && Number.isInteger(v);
      case 'boolean': return typeof v === 'boolean';
      case 'null': return v === null;
      case 'array': return Array.isArray(v);
      case 'object': return v !== null && typeof v === 'object' && !Array.isArray(v);
      default: return true;
    }
  }

  /**
   * Traducao dos patterns do schema para a mascara do manual (secao "Validacao
   * de caracteres"). Sem isso a mensagem de erro cospe a regex inteira, que e
   * ilegivel para quem esta conferindo uma matricula.
   */
  const FORMATOS = {
    cnm: '000000.0.0000000-00 (16 digitos)',
    cep: '00000-000 (8 digitos)',
    cod_sncr: '12 ou 13 digitos',
    ccir: '11 digitos',
    codigo_incra: '000000000000-00 ou UUID de 32 caracteres',
    cib: 'A0A0A0A-0 (8 caracteres)',
    car: 'UF-0000000-... (41 caracteres)',
    cpf_cnpj: 'CPF com 11 ou CNPJ com 14 caracteres, sem espacos',
    cpf_representante_legal: 'CPF com 11 digitos',
    cns: '6 digitos',
    rip: '13 digitos',
  };

  function formatoEsperado(caminho, pattern) {
    const campo = String(caminho || '').split('.').pop().replace(/\[\d+\]$/, '');
    return FORMATOS[campo] || pattern;
  }

  function juntaCaminho(base, chave) {
    if (typeof chave === 'number') return base + '[' + chave + ']';
    return base ? base + '.' + chave : chave;
  }

  /**
   * Peso de um conjunto de erros, para escolher o ramo anyOf mais proximo.
   *
   * O criterio nao pode ser "menos erros ganha": os schemas do ONR envolvem
   * quase todo campo em `anyOf: [<regra real>, {type: "null"}]`. O ramo `null`
   * falha com UM unico erro ("tipo deve ser null"), enquanto o ramo correto
   * falha com N erros profundos e uteis - e o ramo inutil venceria, escondendo
   * a causa real. Por isso um ramo que discorda do TIPO do dado na propria raiz
   * (ou de um `const` na raiz) e tratado como "ramo errado", nao como "quase".
   */
  function pontua(erros, caminhoRaiz) {
    let p = 0;
    for (const e of erros) {
      const naRaiz = (e.path || '') === (caminhoRaiz || '');
      if (naRaiz && (e.keyword === 'type' || e.keyword === 'const')) {
        p += 1000; // ramo de outro tipo/caso: nunca preferir ao ramo pretendido
      } else if (e.esperaNull) {
        // "deveria ser null" com dado presente: e o ramo vazio do anyOf. Sem
        // este peso ele vence por ter 1 erro so e esconde o erro de verdade
        // (era assim que "dados_pessoa: tipo deve ser null" mascarava um
        // estado_civil faltando dentro do array).
        p += 500;
      } else {
        p += e.keyword === 'const' ? 4 : 1;
        p += (e.path || '').split('.').length * 0.01; // erro mais raso = mais relevante
      }
    }
    return p;
  }

  function validaNo(schema, dados, caminho, erros) {
    if (schema === true || schema === undefined) return;
    if (schema === false) {
      erros.push({ path: caminho, keyword: 'false', message: 'schema proibe qualquer valor' });
      return;
    }

    if (Object.prototype.hasOwnProperty.call(schema, 'const')) {
      if (dados !== schema.const) {
        erros.push({
          path: caminho,
          keyword: 'const',
          message: 'deve ser ' + JSON.stringify(schema.const) + ' (recebido ' + JSON.stringify(dados) + ')',
        });
      }
    }

    if (schema.type !== undefined) {
      const tipos = Array.isArray(schema.type) ? schema.type : [schema.type];
      if (!tipos.some((t) => tipoConfere(t, dados))) {
        erros.push({
          path: caminho,
          keyword: 'type',
          message: 'tipo deve ser ' + tipos.join(' ou ') + ' (recebido ' + tipoDe(dados) + ')',
          // "deveria ser null" quase sempre significa que este e o ramo de
          // fallback do anyOf, nao o ramo pretendido - ver pontua().
          esperaNull: tipos.length === 1 && tipos[0] === 'null',
        });
        return; // demais checagens desse no nao fazem sentido
      }
    }

    if (typeof dados === 'string') {
      if (schema.pattern !== undefined && !new RegExp(schema.pattern).test(dados)) {
        erros.push({
          path: caminho,
          keyword: 'pattern',
          message: 'formato invalido: ' + JSON.stringify(dados) + ' - esperado ' + formatoEsperado(caminho, schema.pattern),
          pattern: schema.pattern,
        });
      }
      if (schema.maxLength !== undefined && dados.length > schema.maxLength) {
        erros.push({
          path: caminho,
          keyword: 'maxLength',
          message: 'excede ' + schema.maxLength + ' caracteres (tem ' + dados.length + ')',
        });
      }
      if (schema.minLength !== undefined && dados.length < schema.minLength) {
        erros.push({
          path: caminho,
          keyword: 'minLength',
          message: 'precisa de pelo menos ' + schema.minLength + ' caractere(s)',
        });
      }
    }

    if (typeof dados === 'number') {
      if (schema.minimum !== undefined && dados < schema.minimum) {
        erros.push({ path: caminho, keyword: 'minimum', message: 'deve ser >= ' + schema.minimum });
      }
      if (schema.maximum !== undefined && dados > schema.maximum) {
        erros.push({ path: caminho, keyword: 'maximum', message: 'deve ser <= ' + schema.maximum });
      }
    }

    if (Array.isArray(dados)) {
      if (schema.minItems !== undefined && dados.length < schema.minItems) {
        erros.push({
          path: caminho,
          keyword: 'minItems',
          message: 'precisa de pelo menos ' + schema.minItems + ' item(ns)',
        });
      }
      if (schema.items) {
        dados.forEach((item, i) => validaNo(schema.items, item, juntaCaminho(caminho, i), erros));
      }
    }

    if (dados !== null && typeof dados === 'object' && !Array.isArray(dados)) {
      if (Array.isArray(schema.required)) {
        for (const chave of schema.required) {
          if (dados[chave] === undefined) {
            erros.push({
              path: juntaCaminho(caminho, chave),
              keyword: 'required',
              message: 'campo obrigatorio ausente',
            });
          }
        }
      }
      if (schema.properties) {
        for (const chave of Object.keys(schema.properties)) {
          if (dados[chave] !== undefined) {
            validaNo(schema.properties[chave], dados[chave], juntaCaminho(caminho, chave), erros);
          }
        }
      }
      if (schema.additionalProperties === false) {
        const conhecidas = schema.properties ? Object.keys(schema.properties) : [];
        for (const chave of Object.keys(dados)) {
          if (conhecidas.indexOf(chave) === -1) {
            erros.push({
              path: juntaCaminho(caminho, chave),
              keyword: 'additionalProperties',
              message: 'campo nao previsto no schema',
            });
          }
        }
      } else if (schema.additionalProperties && typeof schema.additionalProperties === 'object') {
        const conhecidas = schema.properties ? Object.keys(schema.properties) : [];
        for (const chave of Object.keys(dados)) {
          if (conhecidas.indexOf(chave) === -1) {
            validaNo(schema.additionalProperties, dados[chave], juntaCaminho(caminho, chave), erros);
          }
        }
      }
    }

    if (Array.isArray(schema.allOf)) {
      for (const sub of schema.allOf) validaNo(sub, dados, caminho, erros);
    }

    if (Array.isArray(schema.anyOf)) {
      let melhor = null;
      for (const sub of schema.anyOf) {
        const errosRamo = [];
        validaNo(sub, dados, caminho, errosRamo);
        if (errosRamo.length === 0) return; // um ramo passou: anyOf satisfeito
        const p = pontua(errosRamo, caminho);
        if (melhor === null || p < melhor.pontos) melhor = { pontos: p, erros: errosRamo };
      }
      if (melhor) {
        for (const e of melhor.erros) erros.push(e);
      }
    }
  }

  /**
   * Valida `dados` contra `schema`.
   * @returns {{valido: boolean, erros: Array<{path:string,keyword:string,message:string}>}}
   */
  function valida(schema, dados) {
    const erros = [];
    validaNo(schema, dados, '', erros);
    // Deduplica (o branch scoring pode repetir o mesmo erro por caminhos irmaos).
    const vistos = new Set();
    const unicos = [];
    for (const e of erros) {
      const k = e.path + '|' + e.keyword + '|' + e.message;
      if (!vistos.has(k)) {
        vistos.add(k);
        unicos.push(e);
      }
    }
    return { valido: unicos.length === 0, erros: unicos };
  }

  global.ONR_VALIDATOR = { valida };
})(typeof window !== 'undefined' ? window : globalThis);
