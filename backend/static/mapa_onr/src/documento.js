/**
 * Digito verificador de CPF e CNPJ.
 *
 * Por que isso existe: nem o JSON Schema nem o manual do ONR conferem o digito
 * verificador - o `pattern` so olha o formato. Um CPF com um digito trocado tem
 * 11 caracteres, passa na validacao oficial e entra na base do ONR como o
 * documento de outra pessoa. Aqui a conta e feita.
 *
 * O CNPJ alfanumerico (IN RFB 2.229/2024, em vigor desde 2026) usa o mesmo
 * calculo, tratando cada caractere pelo seu codigo ASCII menos 48 - por isso
 * '0'..'9' seguem valendo 0..9 e 'A'..'Z' valem 17..42.
 */
(function (global) {
  'use strict';

  function limpa(v) {
    return String(v === null || v === undefined ? '' : v).replace(/[.\-/\s]/g, '').toUpperCase();
  }

  function valorDe(caractere) {
    return caractere.charCodeAt(0) - 48;
  }

  /** Digitos verificadores de um CPF a partir da base de 9 digitos. */
  function dvCpf(base9) {
    const base = String(base9).replace(/\D/g, '');
    if (base.length !== 9) return null;
    let soma = 0;
    for (let i = 0; i < 9; i++) soma += (+base[i]) * (10 - i);
    let d1 = (soma * 10) % 11;
    if (d1 === 10) d1 = 0;
    const comD1 = base + d1;
    soma = 0;
    for (let i = 0; i < 10; i++) soma += (+comD1[i]) * (11 - i);
    let d2 = (soma * 10) % 11;
    if (d2 === 10) d2 = 0;
    return String(d1) + String(d2);
  }

  /** Digitos verificadores de um CNPJ a partir da base de 12 caracteres. */
  function dvCnpj(base12) {
    const base = limpa(base12);
    if (base.length !== 12 || !/^[0-9A-Z]{12}$/.test(base)) return null;
    const calcula = (pesos, valores) => {
      let soma = 0;
      for (let i = 0; i < pesos.length; i++) soma += valores[i] * pesos[i];
      const resto = soma % 11;
      return resto < 2 ? 0 : 11 - resto;
    };
    const valores = base.split('').map(valorDe);
    const d1 = calcula([5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2], valores);
    const d2 = calcula([6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2], valores.concat([d1]));
    return String(d1) + String(d2);
  }

  function cpfValido(v) {
    const d = limpa(v);
    if (!/^\d{11}$/.test(d)) return false;
    if (/^(\d)\1{10}$/.test(d)) return false; // 00000000000, 11111111111...
    return dvCpf(d.slice(0, 9)) === d.slice(9);
  }

  function cnpjValido(v) {
    const d = limpa(v);
    if (!/^[0-9A-Z]{14}$/.test(d)) return false;
    if (/^(.)\1{13}$/.test(d)) return false;
    return dvCnpj(d.slice(0, 12)) === d.slice(12);
  }

  /**
   * Confere um CPF/CNPJ e, quando o dado tem apenas a base (9 digitos de CPF ou
   * 12 de CNPJ, formato antigo das escrituras), devolve a sugestao completa.
   *
   * A sugestao NAO e aplicada automaticamente: o calculo produz um documento
   * valido na forma mesmo se os digitos da base estiverem transcritos errado,
   * e nesse caso seria o documento de outra pessoa.
   *
   * @returns {{situacao:string, documento:string|null, tipo:string|null,
   *            sugestao:string|null, mensagem:string}}
   */
  function confere(valor) {
    const bruto = String(valor === null || valor === undefined ? '' : valor);
    const limpo = limpa(bruto);

    if (limpo === '') {
      return { situacao: 'ausente', documento: null, tipo: null, sugestao: null,
        mensagem: bruto.length ? 'campo preenchido apenas com espacos' : 'nao informado' };
    }
    if (/^\d{11}$/.test(limpo)) {
      return cpfValido(limpo)
        ? { situacao: 'ok', documento: limpo, tipo: 'CPF', sugestao: null, mensagem: 'CPF valido' }
        : { situacao: 'dv_invalido', documento: limpo, tipo: 'CPF', sugestao: null,
            mensagem: 'CPF com digito verificador invalido (esperado '
              + dvCpf(limpo.slice(0, 9)) + ' para a base ' + limpo.slice(0, 9) + ')' };
    }
    if (/^[0-9A-Z]{14}$/.test(limpo)) {
      return cnpjValido(limpo)
        ? { situacao: 'ok', documento: limpo, tipo: 'CNPJ', sugestao: null, mensagem: 'CNPJ valido' }
        : { situacao: 'dv_invalido', documento: limpo, tipo: 'CNPJ', sugestao: null,
            mensagem: 'CNPJ com digito verificador invalido (esperado '
              + dvCnpj(limpo.slice(0, 12)) + ' para a base ' + limpo.slice(0, 12) + ')' };
    }
    if (/^\d{9}$/.test(limpo)) {
      const dv = dvCpf(limpo);
      return { situacao: 'base_incompleta', documento: null, tipo: 'CPF', sugestao: limpo + dv,
        mensagem: 'CPF sem os digitos verificadores (formato antigo). Base ' + limpo
          + ' -> unico completo possivel: ' + mascaraCpf(limpo + dv) + '. Confira no documento antes de usar.' };
    }
    if (/^[0-9A-Z]{12}$/.test(limpo)) {
      const dv = dvCnpj(limpo);
      return { situacao: 'base_incompleta', documento: null, tipo: 'CNPJ', sugestao: limpo + dv,
        mensagem: 'CNPJ sem os digitos verificadores. Base ' + limpo
          + ' -> unico completo possivel: ' + limpo + dv + '. Confira antes de usar.' };
    }
    return { situacao: 'formato_invalido', documento: null, tipo: null, sugestao: null,
      mensagem: 'nao e CPF nem CNPJ: ' + JSON.stringify(bruto) + ' (' + limpo.length
        + ' caractere(s) uteis; esperado 11 ou 14)' };
  }

  // ------------------------------------------------------------------- CNM

  /**
   * Digito verificador do Codigo Nacional de Matricula.
   *
   * Algoritmo: ISO 7064 MOD 97-10 (o mesmo do IBAN) - acrescenta "00" a base de
   * 14 digitos, tira o modulo 97 e faz 98 menos o resto.
   *
   * Deduzido de 7 CNM reais da serventia, com numeros bem espacados e
   * inclusive pares vizinhos, com acerto em 7/7 - ver os testes
   * em run-tests.html, grupo "CNM". O manual do ONR nao publica esse calculo.
   */
  function dvCnm(base14) {
    const base = String(base14 == null ? '' : base14).replace(/\D/g, '');
    if (base.length !== 14) return null;
    let resto = 0;
    for (const c of base + '00') resto = (resto * 10 + (+c)) % 97;
    return String(98 - resto).padStart(2, '0');
  }

  /**
   * Monta o CNM completo a partir do CNS e do numero da matricula.
   * @param {string|number} cns 6 digitos
   * @param {string|number} numeroMatricula
   * @param {number} [livro] 2 = Livro 2 (Registro Geral), o padrao
   * @returns {string|null} 000000.0.0000000-00
   */
  function montaCnm(cns, numeroMatricula, livro) {
    const c = String(cns == null ? '' : cns).replace(/\D/g, '');
    const n = String(numeroMatricula == null ? '' : numeroMatricula).replace(/\D/g, '');
    if (c.length !== 6 || !n || n.length > 7) return null;
    const base = c + String(livro == null ? 2 : livro) + n.padStart(7, '0');
    const dv = dvCnm(base);
    if (!dv) return null;
    return base.slice(0, 6) + '.' + base.slice(6, 7) + '.' + base.slice(7, 14) + '-' + dv;
  }

  /** Confere um CNM informado: formato + digito verificador. */
  function confereCnm(cnm) {
    const d = String(cnm == null ? '' : cnm).replace(/\D/g, '');
    if (d.length !== 16) {
      return { situacao: 'formato_invalido', esperado: null,
        mensagem: 'CNM deve ter 16 digitos (000000.0.0000000-00); recebido ' + d.length };
    }
    const esperado = dvCnm(d.slice(0, 14));
    if (esperado !== d.slice(14)) {
      return { situacao: 'dv_invalido', esperado,
        mensagem: 'CNM com digito verificador invalido: esperado ' + esperado
          + ' para a base ' + d.slice(0, 14) + ', informado ' + d.slice(14) };
    }
    return { situacao: 'ok', esperado, mensagem: 'CNM valido' };
  }

  function mascaraCpf(d) {
    const s = String(d).replace(/\D/g, '');
    if (s.length !== 11) return String(d);
    return s.slice(0, 3) + '.' + s.slice(3, 6) + '.' + s.slice(6, 9) + '-' + s.slice(9);
  }

  /**
   * Auditoria de documentos de um arquivo de remessa inteiro.
   * Complementa a validacao de schema: aponta o que o `pattern` deixa passar.
   */
  function auditaArquivo(dados) {
    const achados = [];
    const imoveis = (dados && dados.imoveis) || [];
    imoveis.forEach((im, i) => {
      (im.dados_pessoa || []).forEach((pe, j) => {
        const r = confere(pe.cpf_cnpj);
        if (r.situacao === 'ok') return;
        if (r.situacao === 'ausente' && pe.nao_CPF === true) return; // dispensado na v1.3.0
        achados.push({
          path: 'imoveis[' + i + '].dados_pessoa[' + j + '].cpf_cnpj',
          ato: im.numero_ato || null,
          nome: pe.nome_completo || null,
          situacao: r.situacao,
          sugestao: r.sugestao,
          message: r.mensagem,
        });
      });
      if (im.cpf_representante_legal) {
        const r = confere(im.cpf_representante_legal);
        if (r.situacao !== 'ok') {
          achados.push({ path: 'imoveis[' + i + '].cpf_representante_legal', ato: im.numero_ato || null,
            nome: im.nome_representante_legal || null, situacao: r.situacao, sugestao: r.sugestao, message: r.mensagem });
        }
      }
    });
    return achados;
  }

  global.ONR_DOC = { confere, auditaArquivo, cpfValido, cnpjValido, dvCpf, dvCnpj,
    dvCnm, montaCnm, confereCnm, mascaraCpf, limpa };
})(typeof window !== 'undefined' ? window : globalThis);
