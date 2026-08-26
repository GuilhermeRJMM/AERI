/**
 * Parser deterministico de matricula (Livro 2) -> lista de atos.
 *
 * Nada aqui depende de IA: e recorte de texto e extracao por padrao, com
 * evidencia (`trecho`) anexada a cada valor para conferencia humana. O que nao
 * for extraido com seguranca vira pendencia, nunca um palpite silencioso.
 *
 * Duas licoes ja pagas em producao, preservadas em tests/:
 *  1) Separar atos SO pelo cabecalho quebra no lugar errado: tabelas internas
 *     de recalculo de titularidade citam "R-30", "R-31" dentro do proprio ato.
 *     Por isso a divisao primaria e pelas linhas de tracos que a matricula usa
 *     entre atos, e o cabecalho apenas confirma/rotula o bloco.
 *  2) O cabecalho aparece em caixa inconsistente no mesmo documento ("AV.38"
 *     e "Av.39"). Todo casamento de cabecalho e case-insensitive.
 */
(function (global) {
  'use strict';

  // "R.30-1.234", "AV.37-1.234", "Av.39", "R-30", "REGISTRO 5", "AVERBACAO 12"
  // A virgula tem de fechar o numero da matricula ("R-1-6.529, Morrinhos"):
  // sem ela na lista de terminadores, o motor voltava atras e casava so "6",
  // e a matricula 6.529 saia no arquivo como numero 6.
  const CABECALHO = /^[\s>*]*(R|AV|AVERBA(?:C|Ç)(?:AO|ÃO)|REGISTRO)\s*[.\-–—]?\s*(\d{1,5})(?:\s*[-–—/]\s*([\d.]+))?\s*(?:[-–—:.,)]|\s|$)/i;

  // Linha divisoria de atos: 5+ tracos/underscores/iguais, sozinha na linha.
  const DIVISORIA = /^[\s]*[-_=–—]{5,}[\s]*$/;

  const DATA_NUM = /\b(\d{2})\/(\d{2})\/(\d{4})\b/;
  const MESES = ['janeiro', 'fevereiro', 'marco', 'abril', 'maio', 'junho', 'julho',
    'agosto', 'setembro', 'outubro', 'novembro', 'dezembro'];

  function semAcento(s) {
    return String(s).normalize('NFD').replace(/[\u0300-\u036f]/g, '');
  }

  /** Data escrita: "aos 11 de agosto de 2010", "11 de agosto de 2010". */
  function dataEscrita(texto) {
    const t = semAcento(texto).toLowerCase();
    // "1.995": nos livros antigos o ano vem com ponto de milhar.
    const re = new RegExp('(\\d{1,2})\\s+de\\s+(' + MESES.join('|') + ')\\s+de\\s+(\\d{1,2}\\.?\\d{3})');
    const m = t.match(re);
    if (!m) return null;
    const dia = String(parseInt(m[1], 10)).padStart(2, '0');
    const mes = String(MESES.indexOf(m[2]) + 1).padStart(2, '0');
    return dia + '/' + mes + '/' + m[3].replace('.', '');
  }

  function achado(valor, trecho) {
    return valor === null || valor === undefined ? null : { valor, trecho: (trecho || '').trim() };
  }

  /** Contexto de +-60 caracteres em volta de um match, para evidencia. */
  function contexto(texto, indice, tamanho) {
    const ini = Math.max(0, indice - 60);
    const fim = Math.min(texto.length, indice + (tamanho || 0) + 60);
    return texto.slice(ini, fim).replace(/\s+/g, ' ');
  }

  function extraiComRegex(texto, re) {
    const m = texto.match(re);
    if (!m) return null;
    return achado(m[1] !== undefined ? m[1] : m[0], contexto(texto, m.index, m[0].length));
  }

  /** Numero brasileiro "139.591,71" -> 139591.71 */
  function numeroBR(s) {
    if (typeof s !== 'string') return null;
    const limpo = s.replace(/\./g, '').replace(',', '.');
    const n = parseFloat(limpo);
    return Number.isFinite(n) ? n : null;
  }

  /**
   * Quebra o texto integral da matricula em blocos de ato.
   * @returns {Array<{indice:number, numero:string, tipo:number, tipoRotulo:string,
   *                  cabecalho:string, texto:string}>}
   */
  function separaAtos(textoIntegral) {
    const texto = String(textoIntegral || '').replace(/\r\n?/g, '\n');
    const linhas = texto.split('\n');

    // 1) Divide pelos separadores proprios do documento.
    const blocosBrutos = [];
    let atual = [];
    for (const linha of linhas) {
      if (DIVISORIA.test(linha)) {
        if (atual.length) blocosBrutos.push(atual.join('\n'));
        atual = [];
      } else {
        atual.push(linha);
      }
    }
    if (atual.length) blocosBrutos.push(atual.join('\n'));

    // 2) Se nao havia divisorias uteis, cai para corte por cabecalho.
    const temCabecalho = (b) => b.split('\n').some((l) => CABECALHO.test(l));
    const comCabecalho = blocosBrutos.filter(temCabecalho);
    let blocos = blocosBrutos;
    if (comCabecalho.length <= 1 && blocosBrutos.length <= 2) {
      blocos = cortaPorCabecalho(linhas);
    }

    // 3) Rotula cada bloco pelo primeiro cabecalho encontrado.
    const atos = [];
    const preambulo = [];
    for (const bloco of blocos) {
      const linhasBloco = bloco.split('\n');
      let cab = null;
      for (const l of linhasBloco) {
        const m = l.match(CABECALHO);
        if (m) { cab = { m, linha: l }; break; }
      }
      if (!cab) {
        // Bloco de abertura: nao e ato, mas carrega area, CCIR, COD_SNCR e
        // descricao do imovel. Descartar isso deixava o estado vigente vazio.
        if (bloco.trim()) preambulo.push(bloco.trim());
        continue;
      }
      const marcador = semAcento(cab.m[1]).toUpperCase();
      const tipo = (marcador === 'R' || marcador === 'REGISTRO') ? 1 : 2;
      atos.push({
        indice: atos.length,
        numero: cab.m[2],
        // Numero da matricula que vem no proprio cabecalho ("R.56-1.234"):
        // e a unica fonte quando a matricula nao tem a linha "MATRICULA N".
        matricula: cab.m[3] ? cab.m[3].replace(/\D/g, '') : null,
        tipo,
        tipoRotulo: tipo === 1 ? 'Registro' : 'Averbacao',
        cabecalho: cab.linha.trim(),
        texto: bloco.trim(),
      });
    }
    atos.preambulo = preambulo.join('\n\n');
    return atos;
  }

  /**
   * A abertura da matricula e, ela mesma, um ato registravel ("ato: 1"): e o
   * primeiro ato do folio real, com data propria. Basta que o preambulo traga o
   * que faz dele uma abertura - a descricao do imovel (ou a titularidade) e uma
   * data. Nos livros antigos nao ha protocolo nem selo escritos, e mesmo assim a
   * abertura e ato; o protocolo so e exigido pelo layout quando motivo_envio = 1.
   *
   * Fica de fora o preambulo que nao descreve nada nem tem data - continuacao de
   * folha, cabecalho solto, texto truncado.
   */
  function aberturaEhAto(preambulo) {
    const t = String(preambulo || '').replace(/\s+/g, ' ');
    if (t.trim().length < 60) return false;
    const descreve = /IM[ÓO]VEL\s*:|PROPRIET[ÁA]RI|T[ÍI]TULO\s+AQUISITIVO/i.test(t);
    const temData = /\d{1,2}\s+de\s+[A-Za-zçãéÀ-ÿ]+\s+de\s+\d{1,2}\.?\d{3}/i.test(t)
      || /\b\d{2}[./]\d{2}[./]\d{4}\b/.test(t);
    return descreve && temData;
  }

  /**
   * Documento completo: preambulo (abertura da matricula) + atos.
   * O preambulo nao vira item de `imoveis`, mas alimenta o estado vigente.
   */
  function separaDocumento(textoIntegral) {
    const atos = separaAtos(textoIntegral);
    const preambulo = atos.preambulo || '';
    const lista = Array.prototype.slice.call(atos);

    // Abertura com data e protocolo entra na lista como o primeiro ato, para
    // poder ser exportada. Fica com numero "0": o ONR nao define numeracao para
    // a abertura, e o campo e editavel na tela.
    if (aberturaEhAto(preambulo)) {
      lista.unshift({
        indice: -1,
        numero: '0',
        matricula: (lista[0] || {}).matricula || null,
        tipo: 1,
        tipoRotulo: 'Registro',
        cabecalho: 'Abertura da matricula',
        texto: preambulo,
        ehAbertura: true,
      });
    }
    return { preambulo, atos: lista };
  }

  function cortaPorCabecalho(linhas) {
    const blocos = [];
    let atual = [];
    for (const linha of linhas) {
      if (CABECALHO.test(linha) && atual.length) {
        blocos.push(atual.join('\n'));
        atual = [linha];
      } else {
        atual.push(linha);
      }
    }
    if (atual.length) blocos.push(atual.join('\n'));
    return blocos;
  }

  /**
   * Extrai do texto de um ato os campos que dao para reconhecer por padrao.
   * Cada campo vem como {valor, trecho} ou null (= pendencia).
   */
  function extraiCampos(textoAto) {
    const t = String(textoAto || '');
    const compacto = t.replace(/\s+/g, ' ');

    const mData = t.match(DATA_NUM);
    const data = mData
      ? achado(mData[0], contexto(t, mData.index, mData[0].length))
      : achado(dataEscrita(t), compacto.slice(0, 160));

    const valorTransacao = (() => {
      const m = t.match(/R\$\s*([\d.]+,\d{2})/);
      if (!m) return null;
      return achado(numeroBR(m[1]), contexto(t, m.index, m[0].length));
    })();

    const area = (() => {
      const m = compacto.match(/([\d.]+,\d+)\s*(hectares?|ha\b|m2|m²|metros quadrados)/i);
      if (!m) return null;
      const unidade = /^h/i.test(m[2]) ? 2 : 1;
      return achado({ valor: numeroBR(m[1]), unidade }, m[0]);
    })();

    const cpfs = [];
    const reCpf = /\b(\d{3}\.\d{3}\.\d{3}-\d{2})\b/g;
    let m;
    while ((m = reCpf.exec(t)) !== null) {
      cpfs.push(achado(m[1].replace(/\D/g, ''), contexto(t, m.index, m[0].length)));
    }
    const cnpjs = [];
    const reCnpj = /\b(\d{2}\.\d{3}\.\d{3}\/\d{4}-\d{2})\b/g;
    while ((m = reCnpj.exec(t)) !== null) {
      cnpjs.push(achado(m[1].replace(/\D/g, ''), contexto(t, m.index, m[0].length)));
    }

    return {
      data_ato: data,
      valor_transacao: valorTransacao,
      area_terreno_total: area,
      // CAR: UF + 40 alfanumericos, com ou sem separadores.
      car: extraiComRegex(compacto, /\b([A-Z]{2}[-\s]?\d{7}[-\s]?[A-Z0-9]{32})\b/),
      ccir: extraiComRegex(compacto, /CCIR[^\d]{0,20}([\d.\-\/]{11,17})/i),
      cod_sncr: extraiComRegex(compacto, /(?:SNCR|cadastro rural)[^\d]{0,20}([\d.\-]{12,17})/i),
      // NIRF nao e CIB: capturado separadamente para nunca ser usado como CIB.
      nirf: extraiComRegex(compacto, /NIRF[^\d]{0,20}([\d.\-]{9,15})/i),
      cib: extraiComRegex(compacto, /CIB[^A-Z0-9]{0,20}([A-Z0-9]{7}-?[A-Z0-9])\b/i),
      cnm: extraiComRegex(compacto, /\b(\d{6}\.\d\.\d{7}-\d{2})\b/),
      protocolo: extraiComRegex(compacto, /(?:protocolo|preno[t]?a[cç][aã]o)[^\d]{0,15}(\d{3,10})/i),
      cpfs,
      cnpjs,
    };
  }

  /**
   * motivo_envio e aritmetica de data, nao julgamento: atos a partir de
   * 02/12/2025 (inicio da obrigatoriedade da ITN 003/2025) sao "1: Novo ato";
   * anteriores sao "2: Acervo".
   */
  const CORTE_ITN = { dia: 2, mes: 12, ano: 2025 };

  function motivoEnvio(dataAtoBR) {
    const m = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(String(dataAtoBR || '').trim());
    if (!m) return null; // sem data confiavel nao se decide: vira pendencia
    const d = { dia: +m[1], mes: +m[2], ano: +m[3] };
    const chave = (x) => x.ano * 10000 + x.mes * 100 + x.dia;
    return chave(d) >= chave(CORTE_ITN) ? 1 : 2;
  }

  global.ONR_PARSER = {
    separaAtos,
    separaDocumento,
    aberturaEhAto,
    extraiCampos,
    motivoEnvio,
    CORTE_ITN,
    _internos: { CABECALHO, DIVISORIA, numeroBR, dataEscrita, semAcento },
  };
})(typeof window !== 'undefined' ? window : globalThis);
