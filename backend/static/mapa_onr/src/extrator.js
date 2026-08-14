/**
 * Extracao automatica dos campos da matricula, calibrada sobre o texto real do
 * acervo de Morrinhos (ver tests/fixtures/matricula_1118_real.js).
 *
 * Toda coisa extraida vem como {valor, trecho, rotulo} - o `trecho` e a prova,
 * exibida na tela ao lado do campo. Onde ha ambiguidade real (varias areas no
 * mesmo ato, regime "comunhao de bens" sem qualificar), a funcao devolve os
 * CANDIDATOS em vez de escolher no escuro.
 *
 * Regras que vieram de erro observado em producao:
 *  - Area: "10,67% do imovel ... equivalente a 32,8504ha" e area PARCIAL do
 *    negocio, nao do imovel. So conta area rotulada como total/remanescente.
 *  - Valor: "Cotacao do ato: emolumentos", "taxa judiciaria", "ITBI",
 *    "valor da causa", "Valor Cr$" de cedula rural NAO sao valor_transacao.
 *  - Data: vale a data do CABECALHO do ato ("Data: 10.03.2026", "Morrinhos, 19
 *    de maio de 1977"), nunca a primeira data que aparecer no corpo.
 *  - CIB/NIRF/CAR: sempre o valor rotulado mais recente; CAR vem com hifens no
 *    meio ("GO-0000000-AAAA-BBBB-...") e precisa ser normalizado para 41.
 */
(function (global) {
  'use strict';

  const MESES = ['janeiro', 'fevereiro', 'marco', 'abril', 'maio', 'junho', 'julho',
    'agosto', 'setembro', 'outubro', 'novembro', 'dezembro'];

  function semAcento(s) {
    return String(s == null ? '' : s).normalize('NFD').replace(/[\u0300-\u036f]/g, '');
  }
  function chave(s) { return semAcento(s).toLowerCase(); }
  function compacta(s) { return String(s == null ? '' : s).replace(/\s+/g, ' ').trim(); }

  function achado(valor, trecho, rotulo) {
    if (valor === null || valor === undefined || valor === '') return null;
    return { valor, trecho: compacta(trecho).slice(0, 180), rotulo: rotulo || null };
  }

  function numeroBR(s) {
    if (s === null || s === undefined) return null;
    const limpo = String(s).replace(/\./g, '').replace(',', '.');
    const n = parseFloat(limpo);
    return Number.isFinite(n) ? n : null;
  }

  function dataDeTexto(t) {
    const s = String(t || '');
    let m = s.match(/\b(\d{2})[./](\d{2})[./](\d{4})\b/);
    if (m) return m[1] + '/' + m[2] + '/' + m[3];
    const k = chave(s);
    const re = new RegExp('(\\d{1,2})\\s+de\\s+(' + MESES.join('|') + ')\\s+de\\s+(\\d{4})');
    m = k.match(re);
    if (m) {
      return String(+m[1]).padStart(2, '0') + '/'
        + String(MESES.indexOf(m[2]) + 1).padStart(2, '0') + '/' + m[3];
    }
    return null;
  }

  // ------------------------------------------------------- data e protocolo

  /** Data do ato: procurada no cabecalho (inicio do bloco), nao no corpo. */
  function extraiDataAto(textoAto) {
    const t = compacta(textoAto);
    const cabecalho = t.slice(0, 260);
    let m = cabecalho.match(/(?:Data|Em)\s*:?\s*(\d{2}[./]\d{2}[./]\d{4})/i);
    if (m) return achado(dataDeTexto(m[1]), m[0], 'Data:');
    // O dia PRECISA ter fronteira a esquerda: sem isso, o numero da matricula no cabecalho
    // faz "11 de Agosto" ser lido como "1 de Agosto" (erro real observado).
    m = cabecalho.match(/(?:^|[^\d])(\d{1,2})\s+de\s+([A-Za-zçÀ-ÿ]+)\s+de\s+(\d{4})/i);
    if (m) return achado(dataDeTexto(m[1] + ' de ' + m[2] + ' de ' + m[3]), m[0], 'cabecalho');
    const d = dataDeTexto(cabecalho);
    if (d) return achado(d, cabecalho.slice(0, 90), 'cabecalho');
    return null;
  }

  /** "Protocolo n.º 183.167, de 05.05.2026" / "Protocolo: 134.055." */
  function extraiProtocolo(textoAto) {
    const t = compacta(textoAto);
    const m = t.match(/Protocolo\s*(?:n\.?º|n[ºo°]|:)?\s*([\d.]{3,12})(?:\s*,?\s*de\s*(\d{2}[./]\d{2}[./]\d{4}))?/i);
    if (!m) return { numero: null, data: null };
    const numero = m[1].replace(/\D/g, '');
    return {
      numero: numero ? achado(parseInt(numero, 10), m[0], 'Protocolo') : null,
      data: m[2] ? achado(dataDeTexto(m[2]), m[0], 'Protocolo ... de') : null,
    };
  }

  // ------------------------------------------------- classificacao do ato

  /**
   * Regras de classificacao, em ordem: a PRIMEIRA que casar decide.
   * `re` roda sobre o texto sem acento e em minusculas.
   */
  const REGRAS_ATO = [
    { re: /abertura de matricula/, ato: 1 },
    // Usufruto e servidao antes das regras de transmissao: a escritura de
    // "Instituicao Gratuita de Usufruto Com Doacao" e citada nos DOIS atos
    // (R.11 institui o usufruto, R.12 doa a nua propriedade). Quem decide e o
    // titulo do ato, nao a mencao a escritura.
    { re: /(instituicao de usufruto|usufruto vitalicio|reserva de usufruto)/,
      ato: 3, rotulo: 'instituicao de usufruto' },
    { re: /(cancelamento do usufruto|extincao do usufruto|fica extinto o usufruto)/,
      ato: 3, rotulo: 'cancelamento de usufruto' },
    { re: /(servidao)/, ato: 3, rotulo: 'servidao' },
    { re: /(desapropriacao)/, ato: 4, alteracao_titularidade: 17, rotulo: 'desapropriacao' },
    { re: /(venda e compra|compra e venda|compra a venda|adquiriu por compra)/,
      ato: 4, alteracao_titularidade: 1, rotulo: 'compra e venda' },
    { re: /(inventario\/partilha|formal de partilha|adjudicacao|arrolamento dos bens)/,
      ato: 4, alteracao_titularidade: 9, rotulo: 'partilha/adjudicacao por obito' },
    // Divisao amigavel e transmissao SO quando atribui a alguem ("coube
    // exclusivamente aos condominos: X e Y"): ali o quinhao dos outros muda de
    // mao, e o enum nao tem item proprio - 16 e "outras nao onerosas".
    // A divisao que apenas parte o imovel em glebas e encerra a matricula
    // (AV.51 da 1.999, "DIVISAO AMIGAVEL/DESMEMBRAMENTO") nao transmite nada:
    // cai na regra de desmembramento, ato 5, e nao pede valor_transacao.
    { re: /divisao amigavel[\s\S]{0,3000}?(coube|couberam|cabendo)/,
      ato: 4, alteracao_titularidade: 16,
      rotulo: 'divisao amigavel com atribuicao de quinhao' },
    { re: /partilha por divorcio/, ato: 4, alteracao_titularidade: 10 },
    { re: /dissolucao de uniao estavel/, ato: 4, alteracao_titularidade: 11 },
    { re: /(doacao|escritura publica de doacao)/, ato: 4, alteracao_titularidade: 6 },
    // "Permuta de bens VINCULADOS" e troca da garantia hipotecaria, nao do
    // imovel - nao ha transmissao nenhuma. Precisa vir antes da permuta comum.
    { re: /(permuta|substituicao) de bens vinculados|substituicao de bens/,
      ato: 3, rotulo: 'troca de bem dado em garantia' },
    { re: /permuta/, ato: 4, alteracao_titularidade: 14 },
    { re: /(arrematacao|carta de arrematacao)/, ato: 4, alteracao_titularidade: 2 },
    { re: /(dacao em pagamento)/, ato: 4, alteracao_titularidade: 5 },
    { re: /usucapiao/, ato: 4, alteracao_titularidade: 18 },
    { re: /(estremacao|localizacao de parcela)/, ato: 5, alteracao_imovel: 6, rotulo: 'estremacao' },
    { re: /(desmembramento)/, ato: 5, alteracao_imovel: 4 },
    { re: /(desdobro)/, ato: 5, alteracao_imovel: 3 },
    { re: /(unificacao)/, ato: 5, alteracao_imovel: 11 },
    { re: /(loteamento)/, ato: 5, alteracao_imovel: 8 },
    { re: /(retificacao (de|e) (area|demarcacao|indicacao de confront)|fica retificada a area|atualizacao de confrontacao)/,
      ato: 5, alteracao_imovel: 10, rotulo: 'retificacao de area' },
    { re: /(regularizacao fundiaria)/, ato: 5, alteracao_imovel: 9 },
    // Edificacao/construcao muda o imovel, mas o enum nao tem item proprio: 12 (Outro).
    { re: /(edificacao|foi edificado|edificado no imovel|construcao averbada)/,
      ato: 5, alteracao_imovel: 12, rotulo: 'edificacao' },
    { re: /(hipoteca|cedula rural|alienacao fiduciaria|penhor cedular|usufruto)/,
      ato: 3, rotulo: 'garantia / relacao juridica' },
    { re: /(indicacao (de )?(relacao )?titularidade)/, ato: 3, rotulo: 'indicacao de titularidade' },
    // Atos cadastrais e acessorios: por ultimo, para nao roubar dos anteriores.
    // Precisam existir como REGRA (e nao so no fallback) para que o TITULO possa
    // vencer o corpo: "CLAUSULAS RESTRITIVAS" cita "a liberalidade da doacao
    // registrada no R.12" e era classificada como doacao.
    { re: /(clausulas? restritivas?|impenhorabilidade|incomunicabilidade|inalienabilidade|obito|casamento|pacto antenupcial|traslado|reserva legal|declaracao de utilidade publica|codigo de enderecamento|designacao cadastral|atualizacao do cadastro|atualizacao do certificado|atualizacao de confrontacao|inscricao no car|qualificacao pessoal|premonitoria|encargos financeiros|substituicao de bens|alteracao de area|cancelamento)/,
      ato: 6, rotulo: 'ato cadastral/acessorio' },
  ];

  /**
   * Classifica o ato. Sempre devolve o trecho que motivou a escolha; quando
   * nada casa, devolve ato 6 (Outro) como sugestao explicita.
   */
  /**
   * Titulo do ato: o rotulo em CAIXA que vem depois do cabecalho/protocolo e
   * antes do "Nos termos..." - "VENDA E COMPRA", "INSTITUICAO DE USUFRUTO",
   * "CLAUSULAS RESTRITIVAS". E a melhor evidencia de qual ato e.
   */
  function tituloDoAto(textoAto) {
    const t = compacta(textoAto);
    const semCabecalho = t.replace(/^[^.]{0,60}\.\s*/, '')
      .replace(/^(?:Data\s*:?\s*[\d./]+\.?\s*)?(?:Protocolo[^.]{0,60}\.\s*)?/i, '');
    const m = semCabecalho.match(/^([A-ZÀ-Ý0-9ÇÃÕÊÉÓÍÚÂ\s\/\-.,()º]{6,120}?)(?:\s*[-–.]\s*(?:Nos termos|Procede|Procedo|Certific|A requerimento)|\.\s|$)/);
    if (m && /[A-ZÀ-Ý]{3}/.test(m[1])) return compacta(m[1]);
    return semCabecalho.slice(0, 120);
  }

  function classificaAto(textoAto) {
    const titulo = tituloDoAto(textoAto);
    // Duas passadas: primeiro o titulo (decisivo), depois o corpo.
    for (const escopo of [{ txt: titulo, onde: 'titulo do ato' }, { txt: textoAto, onde: 'corpo do ato' }]) {
      const k = chave(escopo.txt);
      for (const regra of REGRAS_ATO) {
        const m = k.match(regra.re);
        if (!m) continue;
        const evidencia = escopo.onde === 'titulo do ato'
          ? titulo
          : compacta(textoAto).slice(Math.max(0, m.index - 40), m.index + 90);
        const rotulo = (regra.rotulo || m[0]) + ' [' + escopo.onde + ']';
        return {
          ato: achado(regra.ato, evidencia, rotulo),
          alteracao_titularidade: regra.alteracao_titularidade
            ? achado(regra.alteracao_titularidade, evidencia, rotulo) : null,
          alteracao_imovel: regra.alteracao_imovel
            ? achado(regra.alteracao_imovel, evidencia, rotulo) : null,
          titulo,
        };
      }
    }
    // Averbacoes cadastrais e demais: "Outro".
    const k = chave(textoAto);
    const cadastral = k.match(/(inscricao no car|codigo de enderecamento postal|atualizacao do certificado|atualizacao do cadastro|designacao cadastral|obito|casamento|pacto antenupcial|premonitoria|qualificacao pessoal|clausulas restritivas|impenhorabilidade|incomunicabilidade|inalienabilidade|traslado|reserva legal|declaracao de utilidade publica|cancelamento)/);
    return {
      ato: achado(6, cadastral ? cadastral[0] : titulo,
        cadastral ? 'ato cadastral/acessorio' : 'nao classificado automaticamente'),
      alteracao_titularidade: null,
      alteracao_imovel: null,
      titulo,
    };
  }

  // ------------------------------------------------------------------ valores

  const CONTEXTO_PROIBIDO = /(cotacao do ato|emolumento|taxa judiciaria|issqn|fundesp|funemp|funcomp|funproge|fundepeg|oab\/dativos|prenotacao: r\$|busca: r\$|selo|valor da causa|atribuido a causa|itbi|itcd|base de calculo|valor recolhido|valor tributavel|valor total dos bens|valor total a recolher|multa|juros|prestac|vencimento|parcela)/;

  function valoresRotulados(textoAto) {
    const t = compacta(textoAto);
    const k = chave(t);
    const achados = [];
    // Moedas do acervo: real, cruzeiro, cruzado novo, cruzado. O valor antigo so
    // conta quando vem rotulado ("pelo preco de NCz$22.000,00"): "Valor Cr$" solto
    // e o credito de uma cedula rural, que nao e transacao.
    const re = /(R|Cr|NCz|Cz|CR)\$\s*([\d.]+,\d{2})/g;
    let m;
    while ((m = re.exec(t)) !== null) {
      const ini = Math.max(0, m.index - 90);
      const contexto = k.slice(ini, m.index + 20);
      if (CONTEXTO_PROIBIDO.test(contexto)) continue;
      const moeda = m[1].toUpperCase() === 'R' ? 'R$' : m[1] + '$';
      // Rotulos reais do acervo: "VALOR:", "VALOR TOTAL:", "VALOR DECLARADO:",
      // "VALOR DE INDENIZACAO:", "pelo preco de", "no valor de".
      const rotulado = /(valor(?:\s+(?:total|declarado|de indenizacao|da transacao))?|pelo preco|no valor de|preco de)\s*:?\s*$/
        .test(chave(t.slice(Math.max(0, m.index - 34), m.index)).trim());
      achados.push({ valor: numeroBR(m[2]), trecho: t.slice(ini, m.index + 30), rotulado, moeda });
    }
    return achados;
  }

  /** valor_transacao: so em ato de transmissao, e so o valor do negocio. */
  function extraiValorTransacao(textoAto, atoClassificado) {
    if (!atoClassificado || !atoClassificado.ato || atoClassificado.ato.valor !== 4) return null;
    const candidatos = valoresRotulados(textoAto)
      .filter((c) => c.moeda === 'R$' || c.rotulado);
    if (!candidatos.length) return null;
    const preferido = candidatos.find((c) => c.rotulado) || candidatos[0];
    return achado(preferido.valor, preferido.trecho,
      preferido.moeda === 'R$' ? 'valor do negocio' : 'valor do negocio em ' + preferido.moeda);
  }

  /** ITBI/ITCD efetivamente recolhido e a base de calculo. */
  function extraiImpostos(textoAto) {
    const t = compacta(textoAto);
    let imposto = null;
    let base = null;
    let m = t.match(/(?:ITBI|ITCD)[^.]{0,120}?(?:importancia|import[âa]ncia|Valor recolhido)\s*(?:de)?\s*:?\s*R\$\s*([\d.]+,\d{2})/i);
    if (!m) m = t.match(/Valor recolhido\s*:?\s*R\$\s*([\d.]+,\d{2})/i);
    if (!m) m = t.match(/(?:valor\s+)?total a recolher\s*:?\s*R\$\s*([\d.]+,\d{2})/i);
    if (m) imposto = achado(numeroBR(m[1]), m[0], 'imposto recolhido');
    const mb = t.match(/Base de c[áa]lculo\s*:?\s*R\$\s*([\d.]+,\d{2})/i);
    if (mb) base = achado(numeroBR(mb[1]), mb[0], 'base de calculo');
    return { valor_imposto: imposto, base_calculo_itbi: base };
  }

  // -------------------------------------------------------------------- areas

  /**
   * Candidatos de area, com prioridade. Prioridade alta = area do IMOVEL;
   * prioridade baixa/zero = area de parcela, garantia ou negocio.
   */
  const REGRAS_AREA = [
    { re: /remanescente\s+de\s+([\d.]+,\d+)\s*ha/i, peso: 100, rotulo: 'REMANESCENTE de' },
    // A area declarada na descricao do imovel ("IMOVEL: Fazenda X, com a area de
    // 281,5458ha") e a DESTE imovel. A area total do CCIR pode ser a do cadastro
    // inteiro no INCRA, que reune varias matriculas - por isso vem depois.
    { re: /IM[ÓO]VEL\s*:[^.]{0,120}?com\s+a?\s*[áa]rea\s+de\s+([\d.]+,\d+)\s*ha/i,
      peso: 95, rotulo: 'area na descricao do imovel' },
    { re: /área\s+total\s*:\s*([\d.]+,\d+)\s*ha/i, peso: 90, rotulo: 'area total (CCIR)' },
    { re: /área\s+total\(ha\)\s*:\s*([\d.]+,\d+)/i, peso: 60, rotulo: 'area total (CAR, declaratoria)' },
    { re: /totalizando\s*:?\s*[\d.,]+\s*alqueires,\s*correspondentes?\s+a\s+([\d.]+,\d+)\s*hectares/i,
      peso: 50, rotulo: 'totalizando (abertura)' },
  ];

  /**
   * Area escrita por extenso no acervo antigo: "com a area de 66 (sessenta e
   * seis) hectares, 85 (oitenta e cinco) ares e 67 (sessenta e sete) centiares".
   * A conta e exata (1 are = 0,01ha; 1 centiare = 0,0001ha) e essa area e a
   * DESTA matricula - vence o CCIR, que pode ser o cadastro de varias.
   *
   * So vale onde o ato DESCREVE o imovel (abertura ou ato = 5). A mesma frase
   * aparece numa gleba VENDIDA ("com a area de 51(cinquenta e um) hectares,
   * 11(onze) ares e 90(noventa) centiares", R-32 da 1.118), e ali ela e a
   * parcela do negocio, nao a area do imovel.
   */
  const RE_AREA_EXTENSO = new RegExp(
    'com\\s+a?\\s*[áa]rea\\s+(?:total\\s+)?de\\s+'
    + '(\\d{1,4})\\s*(?:\\([^)]{0,80}\\))?\\s*hectares?'
    + '(?:\\s*,?\\s*(?:e\\s+)?(\\d{1,3})\\s*(?:\\([^)]{0,80}\\))?\\s*ares?)?'
    + '(?:\\s*,?\\s*(?:e\\s+)?(\\d{1,3}(?:,\\d+)?)\\s*(?:\\([^)]{0,80}\\))?\\s*centiares?)?', 'i');

  function candidatosArea(texto, opcoes) {
    const t = compacta(texto);
    const saida = [];
    for (const r of REGRAS_AREA) {
      const m = t.match(r.re);
      if (m) {
        saida.push({ valor: { valor: numeroBR(m[1]), unidade: 2 }, peso: r.peso,
          rotulo: r.rotulo, trecho: compacta(m[0]) });
      }
    }
    const me = (opcoes && opcoes.descricao) ? t.match(RE_AREA_EXTENSO) : null;
    // So conta se houver ao menos ares ou centiares: "com a area de 5 hectares"
    // sozinho tambem casa a regra decimal e nao precisa desta.
    if (me && (me[2] || me[3])) {
      const ha = Number(me[1]) + (me[2] ? Number(me[2]) / 100 : 0)
        + (me[3] ? numeroBR(me[3]) / 10000 : 0);
      saida.push({ valor: { valor: Number(ha.toFixed(6)), unidade: 2 }, peso: 94,
        rotulo: 'area por extenso na descricao (ha + ares + centiares)',
        trecho: compacta(me[0]) });
    }
    return saida;
  }

  // ------------------------------------------------------ cadastros do imovel

  function extraiCadastros(texto) {
    const t = compacta(texto);
    const out = {};

    // O recibo do CAR sai com separadores variados: por hifen
    // ("GO-5213806-1D9A-5CA1-..."), por ponto ("GO-5213806-E291.B492...") ou
    // sem separador nenhum ("GO-5213806-6263C338708248E9962C0F2339AFD455").
    // Por isso a janela e larga e quem decide e o tamanho normalizado: 41.
    let m = t.match(/CAR\b[\s\S]{0,120}?(?:registro\s*)?([A-Z]{2}[-.]?\d{7}[-.A-Z0-9]{32,70})/i);
    if (m) {
      const limpo = m[1].replace(/[-.]/g, '').toUpperCase();
      if (limpo.length === 41) out.car = achado(limpo, m[0], 'CAR');
    }

    // Certificacao do INCRA: "certificado pelo INCRA, conforme certificacao n.º
    // b67309ee-31c0-4c91-a121-8c46170f4f8f" - o UUID e o codigo_incra (32
    // caracteres sem os hifens, como pede a tabela de validacao).
    m = t.match(/certifica[çc][ãa]o\s*n?\.?º?\s*([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/i)
      || t.match(/(?:c[óo]digo\s+(?:SIGEF|SNCI|INCRA)|SIGEF)\s*:?\s*n?\.?º?\s*([0-9A-Za-z-]{14,36})/i);
    if (m) {
      const limpo = m[1].replace(/-/g, '');
      if (limpo.length === 32 || limpo.length === 14 || limpo.length === 12) {
        out.codigo_incra = achado(limpo, m[0], 'certificacao INCRA');
      }
    }

    m = t.match(/CIB\s*:?\s*n?\.?º?\s*([\d.\-]{9,14}|[A-Z0-9]{7}-?[A-Z0-9])/i);
    if (m) {
      const bruto = m[1];
      const limpo = bruto.replace(/[.\-]/g, '').toUpperCase();
      if (limpo.length === 8) out.cib = achado(limpo, m[0], 'CIB');
    }

    m = t.match(/NIRF\s*:?\s*n?\.?º?\s*([\d.\-]{9,14})/i);
    if (m) out.nirf = achado(m[1].replace(/[.\-]/g, ''), m[0], 'NIRF');

    m = t.match(/CCIR[\s\S]{0,120}?n\.?º?\s*(\d{11})\b/i)
      || t.match(/CCIR\s*:?\s*(\d{11})\b/i);
    if (m) out.ccir = achado(m[1], m[0], 'CCIR');

    // "Cadastrado no INCRA EM NOME DE <terceiro>, sob o nº 936.120.274.135-0":
    // o acervo antigo intercala o nome do cadastrante entre "INCRA" e "sob o".
    m = t.match(/(?:c[óo]digo do im[óo]vel rural|INCRA(?:[^;.]{0,90}?)?\s*sob o)\s*:?\s*n?[ºo°]?\.?\s*([\d.]{13,17}-?\d?)/i);
    if (m) {
      const limpo = m[1].replace(/\D/g, '');
      if (limpo.length === 12 || limpo.length === 13) out.cod_sncr = achado(limpo, m[0], 'codigo do imovel rural');
    }

    // CIF urbano: "CCI n.º 10.630" (codigo cadastral da Prefeitura) ou
    // "Cadastrado na Prefeitura sob o Nº 51/01-C.R.2ª Etapa".
    // "CCI n.º 10.630" - o "n.º" precisa ser consumido inteiro (o "º" nao e \w),
    // senao a captura para na sigla e devolve "CCI".
    m = t.match(/\b(?:CCI|CIF)\b\s*(?:n\.?\s*[ºo°]?)?\s*:?\s*([\d][\d./-]{2,24})/i)
      || t.match(/c[óo]digo cadastral[^:]{0,60}:\s*(?:CCI|CIF)?\s*(?:n\.?\s*[ºo°]?)?\s*([\d][\d./-]{2,24})/i)
      || t.match(/Cadastrado na Prefeitura sob o\s*n?[ºo°]?\.?\s*([\w./-]{3,25})/i);
    if (m) out.cif = achado(compacta(m[1]).replace(/[.,;]+$/, ''), m[0], 'CIF/CCI (Prefeitura)');

    m = t.match(/(?:C[óo]digo de Endere[çc]amento Postal|CEP)\s*[-–]?\s*(?:n\.?º?)?\s*(\d{2}\.?\d{3}-?\d{3})/i);
    if (m) {
      const limpo = m[1].replace(/\D/g, '');
      if (limpo.length === 8) out.cep = achado(limpo, m[0], 'CEP');
    }

    m = t.match(/denomina[çc][ãa]o do im[óo]vel rural\s*:\s*([^;]{3,100}?)\s*;/i)
      // "IMOVEL: Fazenda Serra ou Tras os Montes, LUGAR DENOMINADO Capim, neste
      // Municipio": o nome e o primeiro pedaco; o "lugar denominado" e a
      // localidade, nao o nome do imovel.
      || t.match(/IM[ÓO]VEL\s*:\s*([A-ZÀ-ÿ][^,;]{3,100}?)\s*,(?:\s*lugar\s+denominad[oa][^,;]{1,60}\s*,)?\s*(?:neste|nesta|situad|no Munic)/i);
    if (m) out.nome_imovel = achado(compacta(m[1]), m[0], 'denominacao do imovel');

    return out;
  }

  /** Georreferenciamento e certificacao, inferidos de evidencia explicita. */
  function extraiGeo(texto) {
    const t = compacta(texto);
    const k = chave(t);
    const out = {};
    const mGeo = k.match(/(georreferenciad|vertice asy|azimutes e distancias|sistema geodesico)/);
    if (mGeo) out.georreferenciamento = achado(true, compacta(t).slice(Math.max(0, mGeo.index - 30), mGeo.index + 90), 'descricao georreferenciada');
    // "certificado pelo Instituto Nacional de Colonizacao e Reforma Agraria -
    // INCRA", ou o numero da certificacao: e o texto do ato que afirma a
    // certificacao, e so ele.
    const mc = t.match(/certificad[oa]\s+pel[oa][\s\S]{0,80}?INCRA/i)
      || t.match(/certifica[çc][ãa]o\s*n\.?[ºo°]?\s*[0-9a-f-]{32,40}/i);
    if (mc) out.certificacao_incra = achado(true, mc[0], 'certificacao declarada no texto');

    // A "area certificada" do CCIR NAO decide: ela vem preenchida em imovel que
    // nunca foi georreferenciado, e declarar certificacao ali obriga um
    // codigo_incra que a matricula nao tem. Fica so como area candidata, visivel.
    const mCert = t.match(/área certificada\s*:\s*([\d.]+,\d+)\s*(?:ha)?/i);
    if (mCert) {
      const valor = numeroBR(mCert[1]);
      if (valor > 0) out.area_certificada = achado(valor, mCert[0], 'area certificada no CCIR');
      if (!out.certificacao_incra && valor === 0) {
        out.certificacao_incra = achado(false, mCert[0], 'area certificada 0,0000 no CCIR');
      }
    }
    const mDatum = k.match(/datum[-\s]*sad\s*69/);
    if (mDatum) out.sistema_referencia = achado(2, 'DATUM- SAD 69', 'DATUM declarado');
    else if (/sirgas\s*2000/.test(k)) out.sistema_referencia = achado(1, 'SIRGAS 2000', 'DATUM declarado');
    if (/sistema utm/.test(k)) out.sistema_coordenadas = achado(2, 'sistema UTM', 'sistema declarado');
    else if (/coordenadas geograficas|latitude:/.test(k)) out.sistema_coordenadas = achado(1, 'coordenadas geograficas', 'sistema declarado');
    const mCentro = t.match(/Centr[óo]ide\s*:\s*latitude\s*:\s*(-?[\d.]+)\s*e\s*longitude\s*:\s*(-?[\d.]+)/i);
    if (mCentro) out.centroide = achado('[' + mCentro[1] + ',' + mCentro[2] + ']', mCentro[0], 'centroide do CAR');
    return out;
  }

  // ------------------------------------------------------------- municipio/UF

  const MUNICIPIOS = {
    'morrinhos-go': { cod_ibge_municipio: 5213806, uf: 52, nome: 'Morrinhos-GO' },
    'goiania-go': { cod_ibge_municipio: 5208707, uf: 52, nome: 'Goiania-GO' },
    'caldas novas-go': { cod_ibge_municipio: 5204706, uf: 52, nome: 'Caldas Novas-GO' },
    'buriti alegre-go': { cod_ibge_municipio: 5203807, uf: 52, nome: 'Buriti Alegre-GO' },
    'piracanjuba-go': { cod_ibge_municipio: 5217104, uf: 52, nome: 'Piracanjuba-GO' },
    'goiatuba-go': { cod_ibge_municipio: 5209101, uf: 52, nome: 'Goiatuba-GO' },
  };

  /**
   * Municipio do IMOVEL. "neste Municipio" / "nesta Cidade" remete a comarca da
   * serventia, que e o padrao informado em `municipioServentia`.
   */
  function extraiMunicipio(texto, municipioServentia) {
    const k = chave(texto);
    const padrao = MUNICIPIOS[chave(municipioServentia || 'Morrinhos-GO')] || MUNICIPIOS['morrinhos-go'];
    const m = k.match(/(?:zona rural|munic[íi]pio) de ([a-z\s]+)-go/);
    if (m) {
      const achadoMun = MUNICIPIOS[compacta(m[1]) + '-go'];
      if (achadoMun) return achado(achadoMun, m[0], 'municipio citado');
    }
    if (/neste munic[íi]pio|nesta cidade|zona rural deste munic/.test(k)) {
      return achado(padrao, 'neste Municipio', 'comarca da serventia');
    }
    return achado(padrao, '(padrao da serventia)', 'padrao da serventia');
  }

  // -------------------------------------------------------------------- pessoas

  const PAPEIS = [
    // O rotulo as vezes traz sufixo antes dos dois-pontos:
    // "TRANSMITENTE/PRIMEIRO PERMUTANTE:", "ADQUIRENTE/SEGUNDA PERMUTANTE:".
    { re: /TRANSMITENTES?(?:\/[^:]{0,40})?\s*:/gi, condicao_parte: 1, rotulo: 'transmitente' },
    { re: /ADQUIRENTES?(?:\/[^:]{0,40})?\s*:/gi, condicao_parte: 2, relacao_juridica: 1, rotulo: 'adquirente' },
    { re: /DOADOR(?:A|ES)?\s*:/gi, condicao_parte: 1, rotulo: 'doador' },
    { re: /DONAT[ÁA]RI[OA]S?\s*:/gi, condicao_parte: 2, relacao_juridica: 1, rotulo: 'donatario' },
    { re: /OUTORGANTES?\s*:/gi, condicao_parte: 1, rotulo: 'outorgante' },
    { re: /OUTORGAD[OA]S?\s*:/gi, condicao_parte: 2, relacao_juridica: 1, rotulo: 'outorgado' },
    // Servidao: "como outorgada beneficiaria, Petroleo Brasileiro SA". Nao ha
    // valor de enum para servidao - o layout so tem "outros" (18).
    { re: /(?:como\s+)?outorgad[oa]s?\s+benefici[áa]ri[oa]s?/gi,
      relacao_juridica: 18, rotulo: 'beneficiaria da servidao (outros)' },
    // Anuente / outorga uxoria comparece, mas nao adquire nem transmite.
    { re: /(INTERVENIENTE\s+ANUENTE[^:]{0,40}|OUTORGA\s+UX[ÓO]RIA)\s*:/gi,
      rotulo: 'interveniente anuente (nao e parte - confirmar)' },
    // Beneficiario de usufruto ou servidao: "instituiu a favor de X", "em favor de Y".
    // "a favor de Maria", "a favor DO Banco do Brasil": o artigo contraido
    // tambem conta. Qual relacao juridica isso e depende do ato - so no usufruto
    // ou na servidao o beneficiario e usufrutuario (ver ajuste abaixo).
    { re: /(?:instituiu?\s+)?(?:a|em)\s+favor\s+d[eoa]s?\b/gi, relacao_juridica: 2, rotulo: 'beneficiario (a favor de)' },
    // Nos livros antigos o rotulo vem com ponto e virgula ("Proprietários; Fulano").
    // O "(?!\s*\/)" deixa os rotulos compostos para as regras especificas abaixo.
    { re: /PROPRIET[ÁA]RI[OA]S?\s*(?!\s*\/)[:;]/gi, condicao_parte: 2, relacao_juridica: 1, rotulo: 'proprietario' },
    // Garantia real: o dono que da o imovel em garantia continua proprietario;
    // na alienacao fiduciaria ele e o FIDUCIANTE (8) e o banco o FIDUCIARIO (9).
    { re: /PROPRIET[ÁA]RI[OA]S?\s*\/\s*FIDUCIANTES?\s*[:;]/gi,
      relacao_juridica: 8, rotulo: 'proprietario/fiduciante' },
    { re: /(?:PROPRIET[ÁA]RI[OA]S?|EMITENTES?)\s*\/\s*HIPOTECANTES?(?:\s*\/\s*DEVEDOR(?:ES)?)?\s*[:;]/gi,
      relacao_juridica: 1, rotulo: 'proprietario/hipotecante' },
    { re: /CREDOR(?:ES)?\s*\/\s*FIDUCI[ÁA]RI[OA]S?\s*[:;]/gi,
      relacao_juridica: 9, rotulo: 'credor/fiduciario' },
    { re: /(?:FIDUCIANTES?)\s*[:;]/gi, relacao_juridica: 8, rotulo: 'fiduciante' },
    { re: /adquiriu por compra feita [aà]/gi, condicao_parte: 1, rotulo: 'alienante (compra feita a)' },
    // Redacao antiga da transmissao, sem rotulo TRANSMITENTE/ADQUIRENTE:
    //   "o imovel objeto da presente matricula foi adquirido por X [...]
    //    por compra feita a Y".
    { re: /foi adquirid[oa] por/gi, condicao_parte: 2, relacao_juridica: 1, rotulo: 'adquirente (foi adquirido por)' },
    { re: /por compra feita [aà]/gi, condicao_parte: 1, rotulo: 'alienante (compra feita a)' },
    { re: /Coube (?:a|à|ao) (?:herdeir[ao] e cession[áa]ri[ao]|cession[áa]ri[ao]|vi[úu]va meeira|herdeir[ao])/gi,
      condicao_parte: 2, relacao_juridica: 1, rotulo: 'herdeiro/cessionario' },
    // O credor as vezes vem sem dois-pontos ("firmado pela credora Cooperativa...").
    { re: /(?:pel[ao]\s+)?(?:Credor(?:a|es)?|Financiador(?:a)?)\b(?!\s*\/)\s*:?/gi,
      relacao_juridica: 18, rotulo: 'credor' },
    // "Devedores?" exigia a letra "e": "Devedor:" no singular - a forma mais
    // comum nas cedulas rurais - nunca casava, e a parte ficava sem papel.
    { re: /(?:Devedor(?:es)?|Emitentes?)(?!\s*\/)\s*:/gi, relacao_juridica: 8, rotulo: 'devedor/emitente' },
    { re: /(?:Avalista\(s\)|Avalistas?|Intervenientes? [Gg]arantes?|interveniente garantidora)\s*:?/gi,
      relacao_juridica: 18, rotulo: 'avalista/garante' },
    { re: /C[ôo]njuge\s*:/gi, rotulo: 'conjuge' },
  ];

  // Alem das palavras inteiras, as ABREVIATURAS de documento: o acervo escreve
  // "portador da CI RG GO nº 47.710 e do CIC nº ...", e "CI RG GO" passava por
  // nome proprio (tres palavras, iniciais maiusculas) - o proprietario do imovel
  // aparecia chamado "CI RG" no arquivo enviado.
  const PALAVRA_NAO_NOME = /(carteira|identidade|cpf|cnpj|cic|rua|avenida|alameda|pra[çc]a|setor|quadra|lote|condom|apto|apt\.|cart[óo]rio|escritura|livro|tabelionato|serventia|comarca|fazenda|banco|cooperativa|matr[íi]cula|registro|of[íi]cio|notas|estado|munic[íi]pio|cidade|rod\.|km|selo|dou f[ée]|nos termos|forma do|origem|valor|im[óo]vel|prenota|protocolo|data|capital federal|\bci\b|\brg\b|\bcrmv\b|\bcnh\b|\bsic\b|\bcgc\b|\bssp\b|\bdgpc\b|\bdetran\b)/i;

  /**
   * Razao social logo depois do rotulo da parte: "Banco do Brasil S.A.," ate a
   * primeira virgula. E onde a PJ se identifica; o que vem depois e qualificacao
   * ("sociedade de economia mista, com sede em Brasilia, Capital Federal...").
   */
  function razaoSocialApos(trecho) {
    const t = compacta(trecho).replace(/^[\s:;-]+/, '');
    if (!t) return null;
    const m = t.match(/^([^,;]{3,150})/);
    if (!m) return null;
    const nome = m[1].replace(/[\s.;]+$/, (f) => (/\.$/.test(f) ? '.' : '')).trim();
    if (nome.split(/\s+/).length < 2) return null;
    if (!/[A-Za-zÀ-ÿ]{3}/.test(nome)) return null;
    return nome;
  }

  /**
   * Limites do "pedaco" de uma pessoa dentro do ato. Sem isso, a janela de
   * qualificacao invade a pessoa seguinte: o espolio (que era "casado") herdava
   * o "viuva" da adquirente logo abaixo.
   */
  const SEPARADOR_PESSOA = /(\d\)\s*-|;\s*e,|;\s*\d\)|TRANSMITENTES?\s*:|ADQUIRENTES?\s*:|PROPRIET[ÁA]RI[OA]S?(?:\s*\/\s*[A-ZÀ-ÝÇ]+)*\s*:|Credor(?:a|es)?(?:\s*\/\s*[A-ZÀ-ÝÇ]+)*\s*:|Devedor(?:es)?\s*:|Emitentes?(?:\s*\/\s*[A-ZÀ-ÝÇ]+)*\s*:|Avalista)/g;

  function janelaDaPessoa(texto, indice, atras, frente) {
    let ini = Math.max(0, indice - (atras || 320));
    let fim = Math.min(texto.length, indice + (frente || 320));
    SEPARADOR_PESSOA.lastIndex = 0;
    let m;
    while ((m = SEPARADOR_PESSOA.exec(texto)) !== null) {
      const p = m.index;
      if (p < indice && p > ini) ini = p;
      if (p > indice && p < fim) { fim = p; break; }
    }
    return { texto: texto.slice(ini, fim), ini, fim };
  }

  /** Nome mais proximo ANTES do indice, ignorando rotulos, enderecos e filiacao. */
  function nomeAntesDe(texto, indice, limiteIni, forcarUltimo) {
    const ini = limiteIni != null ? limiteIni : Math.max(0, indice - 320);
    const janela = texto.slice(ini, indice);
    // O "e" so continua o nome quando emenda em palavra com inicial maiuscula
    // ("Costa e Borges Holding"); em "Joao da Silva e sua mulher" o nome termina
    // no "Silva".
    const re = /([A-ZÀ-Ý][A-Za-zÀ-ÿ']+(?:\s+(?:de|da|do|dos|das)\s+[A-Za-zÀ-ÿ']+|\s+e\s+[A-ZÀ-Ý][A-Za-zÀ-ÿ']+|\s+[A-ZÀ-Ý][A-Za-zÀ-ÿ']+)+)/g;
    const candidatos = [];
    let m;
    while ((m = re.exec(janela)) !== null) {
      const nome = compacta(m[1]);
      if (nome.split(/\s+/).length < 2) continue;
      if (PALAVRA_NAO_NOME.test(nome)) continue;
      // "filho de X e Y" e filiacao, nao a parte; "com Z" e o conjuge.
      const antes = janela.slice(Math.max(0, m.index - 14), m.index);
      if (/filh[oa]s?\s+de\s*$/i.test(antes)) continue;
      // Mencao de conjuge: "casado com Y", "e sua mulher Y", "sua esposa Y".
      const ehConjuge = /(?:,?\s*com|e\s+sua\s+mulher|sua\s+mulher|e\s+sua\s+esposa|sua\s+esposa|c[ôo]njuge:?)\s*$/i.test(antes);
      candidatos.push({ nome, conjuge: ehConjuge, fim: m.index + m[1].length });
    }
    if (!candidatos.length) return null;
    // Segundo documento de uma lista do casal ("dos CPF nos. A e B;
    // respectivamente"): e o do conjuge, o ultimo nome citado.
    if (forcarUltimo) return candidatos[candidatos.length - 1];

    // "X, casado com Y pelo regime da comunhao de bens, inscrito no CPF n.º N":
    // o N e de X, nao de Y - a mencao ao conjuge faz parte da clausula de
    // casamento. Ja em "X [...] inscrito no CPF N1, casado com Y, autonoma,
    // portadora da CI [...], inscrita no CPF N2", o N2 e de Y mesmo. O que separa
    // os dois casos e a palavra "regime" entre o nome do conjuge e o documento.
    // O plural tambem denuncia documento de casal ("ambos brasileiros,
    // portadores do CPF Nº ..."): nesse caso o numero fica com o titular.
    const ultimo = candidatos[candidatos.length - 1];
    if (ultimo.conjuge && candidatos.length > 1) {
      const entre = chave(janela.slice(ultimo.fim));
      // "ele" e o modo antigo de devolver a qualificacao ao marido depois de
      // nomear a mulher: "casado com Y, ELE fazendeiro, portador do CPF N".
      if (/regime|comunhao|separacao|ambos|portadores|inscritos|casados|\bele\b/.test(entre)) {
        for (let i = candidatos.length - 2; i >= 0; i--) {
          if (!candidatos[i].conjuge) return candidatos[i];
        }
      }
    }
    return ultimo;
  }

  const RE_DOC = /(\d{3}\.\d{3}\.\d{3}-\d{2}|\d{2}\.\d{3}\.\d{3}\/\d{4}-\d{2}|\b\d{11}\b(?=-SSP)|\b\d{3}\.\d{3}\.\d{3}\b)/g;

  function estadoCivilDe(janela) {
    const k = chave(janela);
    if (/vi[úu]v/.test(k)) return { estado_civil: 5, trecho: 'viuv...' };
    if (/divorciad/.test(k)) return { estado_civil: 4, trecho: 'divorciad...' };
    if (/separad/.test(k)) return { estado_civil: 3, trecho: 'separad...' };
    if (/uniao estavel|companheir/.test(k)) return { estado_civil: 6, trecho: 'uniao estavel' };
    if (/casad|sua mulher|sua esposa|seu conjuge|conjuge/.test(k)) return { estado_civil: 2, trecho: 'casad...' };
    if (/solteir/.test(k)) return { estado_civil: 1, trecho: 'solteir...' };
    if (/pessoa juridica|ltda|s\/a|s\.a\.|sa\b|cnpj|cooperativa|banco|holding|esp[óo]lio/.test(k)) {
      return { estado_civil: 7, trecho: 'pessoa juridica / nao se aplica' };
    }
    return { estado_civil: null, trecho: null };
  }

  /**
   * Regime de bens. "comunhao de bens" sem qualificar NAO decide nada: gera
   * candidatos para o usuario resolver (universal x parcial mudam o direito).
   */
  /** Ano em que a Lei 6.515/77 trocou o regime legal: universal -> parcial. */
  const LEI_6515 = { dia: 26, mes: 12, ano: 1977 };

  function anteriorALei6515(dataBR) {
    const m = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(String(dataBR || '').trim());
    if (!m) return null; // sem data nao se presume nada
    const chaveData = (+m[3]) * 10000 + (+m[2]) * 100 + (+m[1]);
    return chaveData < (LEI_6515.ano * 10000 + LEI_6515.mes * 100 + LEI_6515.dia);
  }

  function regimeBensDe(janela, dataAto) {
    const k = chave(janela);
    if (/comunhao universal/.test(k)) return { regime_bens: 2, trecho: 'comunhao universal' };
    if (/comunhao parcial/.test(k)) return { regime_bens: 1, trecho: 'comunhao parcial' };
    if (/separacao (convencional|absoluta|total)/.test(k)) return { regime_bens: 3, trecho: 'separacao convencional/absoluta' };
    if (/separacao (legal|obrigatoria)/.test(k)) return { regime_bens: 4, trecho: 'separacao legal/obrigatoria' };
    if (/participacao final nos aquestos/.test(k)) return { regime_bens: 5, trecho: 'participacao final nos aquestos' };
    if (/pacto antenupcial/.test(k)) return { regime_bens: 6, trecho: 'pacto antenupcial' };

    // O proprio ato costuma dizer de que lado da Lei 6.515/77 o casamento esta.
    if (/(anterior|anteriormente|antes) (a|à|ao) (vigencia|advento)/.test(k)) {
      return { regime_bens: 2, trecho: 'casamento anterior a Lei 6.515/77 -> comunhao universal' };
    }
    if (/(posterior|posteriormente) (a|à|ao) (vigencia|advento)|na vigencia da lei 6.515/.test(k)) {
      return { regime_bens: 1, trecho: 'casamento na vigencia da Lei 6.515/77 -> comunhao parcial' };
    }

    // "regime da comunhao de bens", sem dizer qual: antes da Lei 6.515/77 o
    // regime legal era o da comunhao UNIVERSAL, entao a expressao so pode ser
    // essa. Depois dela, fica ambiguo mesmo.
    if (/regime da comunhao de bens|comunhao de bens/.test(k)) {
      if (anteriorALei6515(dataAto) === true) {
        return { regime_bens: 2, trecho: 'ato de ' + dataAto
          + ': "comunhao de bens" antes da Lei 6.515/77 e a comunhao universal' };
      }
      // Depois da Lei 6.515/77 a expressao continua sendo o nome ANTIGO da
      // comunhao universal: quem se casa sob o regime legal novo aparece como
      // "comunhao parcial", escrito assim. Fica como presuncao, marcada, porque
      // o casamento em si pode ser posterior e mal redigido.
      return { regime_bens: 2, presumido: true,
        trecho: 'ato de ' + (dataAto || '?') + ': "comunhao de bens" sem qualificar'
          + ' - nome antigo da comunhao universal (presumido, confira)' };
    }

    // So "casado(s)", sem regime nenhum: vale o regime legal da epoca do ato -
    // presuncao, marcada como tal para conferencia.
    if (/casad[oa]s?\b/.test(k)) {
      const antes = anteriorALei6515(dataAto);
      if (antes === true) {
        return { regime_bens: 2, presumido: true,
          trecho: 'so consta "casado"; regime legal antes da Lei 6.515/77: comunhao universal' };
      }
      if (antes === false) {
        return { regime_bens: 1, presumido: true,
          trecho: 'so consta "casado"; regime legal apos a Lei 6.515/77: comunhao parcial' };
      }
    }
    return { regime_bens: null, trecho: null };
  }

  /**
   * Percentual da parte. Aceita inteiro ("equivalente a 50% do imovel", comum
   * no urbano) e decimal com virgula ("parte de 29,50%", comum no rural).
   */
  function percentualDe(janela) {
    const num = '([\\d]{1,3}(?:,\\d{1,4})?)';
    const m = janela.match(new RegExp('parte (?:correspondente a|de|ideal de)?\\s*' + num + '\\s*%', 'i'))
      || janela.match(new RegExp('equivalente a\\s*' + num + '\\s*%', 'i'))
      || janela.match(new RegExp(num + '\\s*%\\s*do im[óo]vel', 'i'));
    return m ? { percentual: numeroBR(m[1]), trecho: compacta(m[0]) } : { percentual: null };
  }

  /**
   * Pessoas do ato: cada documento encontrado gera uma parte, com o papel
   * herdado do rotulo mais proximo antes dele.
   */
  function extraiPessoas(textoAto) {
    const t = compacta(textoAto);
    const kt = chave(t);
    // A data do ato decide o regime legal quando o texto so diz "casado" ou
    // "comunhao de bens" (ver regimeBensDe / Lei 6.515/77).
    const dataDoAto = (extraiDataAto(textoAto) || {}).valor || null;
    // O tipo de ato refina a relacao juridica: quem recebe usufruto e
    // usufrutuario (2); quem recebe a NUA propriedade e nu-proprietario (3);
    // beneficiario de servidao nao tem item proprio no enum, entra em outros (18).
    const ehUsufruto = /usufruto/.test(kt);
    const ehServidao = /servidao/.test(kt);
    const ehNuaPropriedade = /nua propriedade/.test(kt);

    // Mapa de posicao -> papel
    const marcas = [];
    for (const papel of PAPEIS) {
      papel.re.lastIndex = 0;
      let m;
      while ((m = papel.re.exec(t)) !== null) {
        marcas.push({ pos: m.index, fim: m.index + m[0].length, papel });
      }
    }
    marcas.sort((a, b) => a.pos - b.pos);

    const marcaDe = (indice) => {
      let atual = null;
      for (const marca of marcas) {
        if (marca.pos <= indice) atual = marca; else break;
      }
      return atual;
    };
    const papelDe = (indice) => {
      const marca = marcaDe(indice);
      return marca ? marca.papel : null;
    };

    const pessoas = [];
    const vistos = new Set();
    RE_DOC.lastIndex = 0;
    let m;
    while ((m = RE_DOC.exec(t)) !== null) {
      const bruto = m[1];
      const digitos = bruto.replace(/\D/g, '');
      if (digitos.length !== 11 && digitos.length !== 14 && digitos.length !== 9) continue;

      // O CPF antigo de 9 digitos (000.000.000) e ambiguo: "123.456.789" pode ser o
      // comeco do codigo do imovel rural "123.456.789.012-3". So vale como
      // documento se o texto disser CPF/CIC logo antes, e se nao houver mais
      // numero grudado depois.
      if (digitos.length === 9) {
        const antes = chave(t.slice(Math.max(0, m.index - 40), m.index));
        const depois = t.slice(m.index + bruto.length, m.index + bruto.length + 6);
        if (!/(cpf|cic)[^\d]{0,30}$/.test(antes)) continue;
        if (/^\s*[.\-]?\s*\d/.test(depois)) continue;
      }
      const papel = papelDe(m.index);
      const marca = marcaDe(m.index);
      // Janela limitada ao pedaco da propria pessoa (ver janelaDaPessoa).
      const jp = janelaDaPessoa(t, m.index, 320, 320);
      const janela = jp.texto;
      // O percentual costuma vir depois de todo o endereco da pessoa, bem alem
      // da janela de qualificacao - por isso olha mais longe a frente.
      const janelaPct = t.slice(Math.max(0, m.index - 120), Math.min(t.length, m.index + 800));
      // Lista de documentos do casal: "portadores das CI.SSP-GO nos. 145.791 e
      // 158.598 e dos CPF nos. 035.693.731-34 e 950.897.051-00; respectivamente".
      // O "respectivamente" diz que a ordem dos numeros segue a dos nomes - e a
      // qualificacao do casal e longa, entao o nome do primeiro fica bem antes
      // da janela normal de 320 caracteres.
      const depoisDoDoc = t.slice(m.index + bruto.length, m.index + bruto.length + 40);
      const antesDoDoc = t.slice(Math.max(0, m.index - 80), m.index);
      const primeiroDeDois = /^\s*e\s+[\d.]{6,}/.test(depoisDoDoc);
      const segundoDeDois = /(?:CPF|CIC|CNPJ)[^\d]{0,25}[\d.\-/]{11,20}\s*e\s*$/i.test(antesDoDoc);
      const iniNome = (primeiroDeDois || segundoDeDois)
        ? Math.min(jp.ini, Math.max(0, m.index - 700)) : jp.ini;
      const achadoNome = nomeAntesDe(t, m.index, iniNome, segundoDeDois);
      let nome = achadoNome ? achadoNome.nome : null;
      // Pessoa juridica: o nome vem LOGO DEPOIS do rotulo ("CREDOR/FIDUCIARIO:
      // Banco do Brasil S.A., sociedade de economia mista, com sede em Brasilia,
      // Capital Federal, [...] inscrita no CNPJ n.º ..."). Procurar o nome antes
      // do documento pegava "Capital Federal", ou nada.
      if (digitos.length === 14 && marca && marca.fim <= m.index) {
        const razao = razaoSocialApos(t.slice(marca.fim, m.index));
        if (razao) nome = razao;
      }
      const clave = digitos + '|' + (nome || '');
      if (vistos.has(clave)) continue;
      vistos.add(clave);

      // "no ato representada por <nome do representante>, ... CPF ..." - quem
      // representa a PJ NAO e parte do ato; entra como representante legal.
      const antes = t.slice(Math.max(0, m.index - 260), m.index);
      const representante = /representad[ao]s?\s+(?:por|pelo|pela)\b/i.test(antes)
        || /(?:procurador|bastante procurador|representante legal)\b/i.test(antes);

      const ec = estadoCivilDe(janela);
      const rb = regimeBensDe(janela, dataDoAto);
      const pct = percentualDe(janelaPct);
      const ehPJ = digitos.length === 14;

      let relacao = papel ? (papel.relacao_juridica || null) : null;
      const ehBeneficiario = papel && /favor de/.test(papel.rotulo || '');
      // Usufrutuario (2) so no usufruto. Em servidao, penhor ou cedula, quem
      // esta "a favor de" e credor/beneficiario sem item proprio no enum: 18.
      if (ehBeneficiario) relacao = ehUsufruto ? 2 : 18;
      if (ehNuaPropriedade && papel && /donatario|adquirente/.test(papel.rotulo || '')) relacao = 3;

      pessoas.push({
        nome_completo: nome,
        cpf_cnpj: digitos,
        representante_legal: representante,
        condicao_parte: papel ? (papel.condicao_parte || null) : null,
        relacao_juridica: relacao,
        estado_civil: ehPJ ? 7 : ec.estado_civil,
        regime_bens: ehPJ ? null : rb.regime_bens,
        regime_ambiguo: !!rb.ambiguo,
        regime_presumido: !!rb.presumido,
        percentual: pct.percentual,
        estrangeiro: /estrangeir/.test(chave(janela)) ? true : false,
        // Conjuge citado com "... com <nome>": pode ou nao ser parte, dependendo
        // do regime. Fica marcado para conferencia em vez de decidido aqui.
        conjuge: achadoNome ? !!achadoNome.conjuge : false,
        papel: (papel ? papel.rotulo : null)
          + (achadoNome && achadoNome.conjuge ? ' (conjuge - confirmar se e parte)' : ''),
        evidencia: compacta(janela.slice(Math.max(0, 300 - 120), 300 + 60)),
        evidencia_regime: rb.trecho || null,
        evidencia_estado_civil: ec.trecho || null,
      });
    }
    return pessoas;
  }

  // ----------------------------------------------------------- endereco urbano

  /**
   * Tipos de logradouro que aparecem em matricula urbana, do glossario oficial
   * (311 valores). A chave e a palavra como vem escrita no texto.
   */
  const TIPO_LOGRADOURO_TEXTO = {
    rua: 250, avenida: 26, av: 26, alameda: 10, praca: 215, travessa: 273,
    rodovia: 247, estrada: 117, viela: 297, beco: 42, largo: 153, via: 294,
    quadra: 223, setor: 262, conjunto: 82, condominio: 81, jardim: 146,
    parque: 191, vila: 298, chacara: 71, sitio: 263, lote: 161, loteamento: 162,
    residencial: 236, distrito: 93, marginal: 169, anel: 14, bloco: 46,
    ladeira: 148, passagem: 193, servidao: 260, area: 17, esquina: 112,
  };

  /**
   * Endereco do imovel urbano. No urbano o schema EXIGE tipo_logradouro,
   * logradouro, numero_logradouro, cep, cod_ibge_municipio e uf - por isso vale
   * a pena extrair cada pedaco em vez de jogar tudo num campo so.
   *
   * Formato real: "IMOVEL: Rua Primeira esquina com a Rua Segunda, Nº197,
   * Setor Modelo, 2ª Etapa, nesta Cidade, constituido de [...]"
   */
  /**
   * Palavras que iniciam um logradouro de verdade. Quadra, lote e setor estao
   * fora de proposito: "Lote n.º 18-B, da Quadra 27" e designacao, nao endereco.
   */
  const TIPOS_VIA = ['rua', 'avenida', 'av', 'alameda', 'praca', 'travessa', 'rodovia',
    'estrada', 'viela', 'beco', 'largo', 'via', 'marginal', 'anel', 'ladeira',
    'passagem', 'servidao', 'viaduto', 'caminho', 'esplanada', 'parque'];

  /**
   * Corta um texto no limite que o schema aceita, preferindo a ultima palavra
   * inteira. O ONR reprova o arquivo por um caractere a mais, e um nome de
   * bairro cortado ainda identifica o lugar - vazio nao identifica nada.
   */
  function cortaEm(texto, limite) {
    const t = String(texto || '');
    if (t.length <= limite) return t;
    const cortado = t.slice(0, limite);
    const espaco = cortado.lastIndexOf(' ');
    return (espaco > limite * 0.6 ? cortado.slice(0, espaco) : cortado).replace(/[\s,;.-]+$/, '');
  }

  /** O numero do glossario correspondente a primeira palavra do logradouro. */
  function tipoDeLogradouro(nomeVia) {
    const primeira = chave(String(nomeVia || '').trim().split(/\s+/)[0] || '').replace(/\./g, '');
    const tipo = TIPO_LOGRADOURO_TEXTO[primeira];
    return tipo ? achado(tipo, primeira, 'tipo pela palavra "' + primeira + '"') : null;
  }

  /**
   * Averbacao de alteracao de nome de logradouro publico (art. 167, II, 13):
   * "o logradouro publico que ate entao denominava-se 'Avenida H' [...] passou a
   * denominar-se 'Avenida Tenente Santana'". O endereco do imovel passa a ser o
   * nome NOVO - manter o da abertura e mandar ao ONR uma rua que nao existe mais.
   */
  function extraiNovoLogradouro(textoAto) {
    const t = compacta(textoAto);
    if (!/logradouro/i.test(t)) return null;
    const m = t.match(/passou?\s+a\s+(?:se\s+)?denominar(?:-se)?\s*:?\s*["“']([^"“”']{3,150})["”']/i)
      || t.match(/passou?\s+a\s+(?:se\s+)?denominar(?:-se)?\s+([A-ZÀ-Ý][^.,;]{3,80})/);
    if (!m) return null;
    return achado(cortaEm(compacta(m[1]), 150), m[0], 'novo nome do logradouro (averbacao)');
  }

  function extraiEndereco(texto) {
    const t = compacta(texto);
    const out = {};
    // Segmento que descreve o imovel (para nao pegar o endereco das PARTES).
    // O rotulo e casado primeiro e o corte vem depois, em JavaScript: com tudo
    // numa regex so, uma descricao longa (onde "PROPRIETARIOS" esta a mais de
    // 700 caracteres) fazia o motor desistir do rotulo do inicio e casar um
    // "imovel" qualquer do meio do texto ("cadastral do imovel na Prefeitura"),
    // jogando fora justamente o trecho onde o endereco esta.
    const mLabel = t.match(/IM[ÓO]VEL\s*:\s*/i) || t.match(/\bIM[ÓO]VEL\b\s*/i);
    let bruto;
    if (mLabel) {
      const ini = mLabel.index + mLabel[0].length;
      let seg = t.slice(ini, ini + 900);
      const mFim = seg.match(/PROPRIET[ÁA]RI|\.\s*Origem|T[ÍI]TULO AQUISITIVO|Cadastrado na Prefeitura/i);
      if (mFim) seg = seg.slice(0, mFim.index);
      bruto = compacta(seg);
    } else {
      bruto = compacta(t.slice(0, 700));
    }
    if (!bruto) return out;
    out.enderecoBruto = achado(bruto.slice(0, 200), bruto.slice(0, 120), 'descricao do imovel');

    const vias = TIPOS_VIA.join('|');
    // O logradouro aparece em duas posicoes no acervo:
    //   "Rua Primeira esquina com a Rua Segunda, Nº197"     (no inicio)
    //   "Lote n.º 18-B, da Quadra 27, [...] situado na Rua 06"  (depois)
    const tentativas = [
      { re: new RegExp('(?:situad[oa]s?|localizad[oa]s?)\\s+(?:n[ao]s?|em|na|no|à|a)\\s+(' + vias + ')\\.?\\s+([^,;.]{1,70})', 'i'),
        rotulo: 'logradouro apos "situado na"' },
      { re: new RegExp('^(' + vias + ')\\.?\\s+([^,;.]{1,70})', 'i'),
        rotulo: 'logradouro no inicio da descricao' },
      { re: new RegExp('\\b(' + vias + ')\\.?\\s+([A-Za-z0-9ÀÁÂÃÉÊÍÓÔÕÚÇ][^,;.]{0,70})', 'i'),
        rotulo: 'logradouro citado na descricao' },
    ];
    // "residente e domiciliado na Rua X" e endereco de PESSOA, nunca do imovel.
    const ehResidencia = (indice) => /(residente|residem|domiciliad|residia|domiciliava|com sede|sede e foro|moradia)[^.]{0,40}$/i
      .test(bruto.slice(Math.max(0, indice - 60), indice));

    let achouVia = null;
    for (const tent of tentativas) {
      const re = new RegExp(tent.re.source, 'gi');
      let m;
      while ((m = re.exec(bruto)) !== null) {
        if (ehResidencia(m.index)) continue;
        achouVia = { m, rotulo: tent.rotulo };
        break;
      }
      if (achouVia) break;
    }
    if (!achouVia) return out; // sem via reconhecida nao ha endereco a declarar

    const palavraTipo = chave(achouVia.m[1]).replace(/\./g, '');
    const tipo = TIPO_LOGRADOURO_TEXTO[palavraTipo];
    const nomeVia = compacta(achouVia.m[1] + ' ' + achouVia.m[2]).replace(/[,;]+$/, '');
    out.logradouro = achado(nomeVia, achouVia.m[0], achouVia.rotulo);
    if (tipo) out.tipo_logradouro = achado(tipo, palavraTipo, 'tipo pela palavra "' + palavraTipo + '"');

    // Numero: procurado logo depois do logradouro ("..., Nº197"), nunca antes
    // (o "n.º 18-B" de "Lote n.º 18-B" e designacao do lote).
    const depoisDaVia = bruto.slice(achouVia.m.index + achouVia.m[0].length, achouVia.m.index + achouVia.m[0].length + 90);
    const mNum = depoisDaVia.match(/(?:N[ºo°]\.?|n[úu]mero)\s*(\d{1,6}[A-Za-z]?)/i);
    if (mNum) out.numero_logradouro = achado(mNum[1], compacta(nomeVia + ' ' + mNum[0]), 'numero apos o logradouro');

    // Bairro: "Setor X", "Jardim Y", "Loteamento Z" no restante da descricao.
    const depois = bruto.slice(achouVia.m.index);
    const mBairro = depois.match(/((?:Setor|Jardim|Bairro|Vila|Parque|Residencial|Distrito|Conjunto|Cohab|Loteamento|Chac[áa]ra|Centro)[^,;]{0,60}(?:,\s*\d[ªa]?\s*Etapa)?)/i);
    if (mBairro) {
      let nomeBairro = compacta(mBairro[1]).replace(/[,;]+$/, '');
      // O loteamento costuma vir com o nome entre aspas: "do loteamento
      // residencial "Vila Santos Dumont II Etapa"". O bairro e o que esta
      // DENTRO das aspas - o resto e rotulo, e ainda estoura os 50 caracteres
      // que o schema aceita.
      const mAspas = nomeBairro.match(/["“”']([^"“”']{3,60})["“”']/);
      if (mAspas) nomeBairro = compacta(mAspas[1]);
      out.bairro = achado(cortaEm(nomeBairro, 50), mBairro[0], 'bairro');
    } else if (/Centro/i.test(depois)) out.bairro = achado('Centro', 'Centro', 'bairro');

    // Quadra/lote so valem dentro da DESCRICAO do imovel: o endereco do
    // proprietario tambem tem "Quadra 37, Lote 30" e nao e deste imovel.
    // O "n.º" aparece como "Nº01", "n.º 18-B" e "número 16": o prefixo precisa
    // ser tolerante, senao o "º" solto derruba a captura.
    const numPrefixo = '(?:n\\.?\\s*[ºo°]?\\.?\\s*|n[úu]mero\\s*)?';
    const mLote = bruto.match(new RegExp('lote\\s*(?:de\\s*terras\\s*)?' + numPrefixo
      + '([\\w-]{1,10})[^.]{0,40}?quadra\\s*' + numPrefixo + '(\\d{1,5})', 'i'))
      || bruto.match(new RegExp('quadra\\s*' + numPrefixo + '(\\d{1,5})[^.]{0,30}?lote\\s*'
        + numPrefixo + '([\\w-]{1,10})', 'i'));
    if (mLote) {
      const ehLotePrimeiro = /^lote/i.test(mLote[0]);
      const lote = ehLotePrimeiro ? mLote[1] : mLote[2];
      const quadra = ehLotePrimeiro ? mLote[2] : mLote[1];
      out.complemento = achado('Quadra ' + quadra + ', Lote ' + lote, mLote[0], 'quadra/lote');
    }
    return out;
  }

  /**
   * Areas do imovel urbano: terreno (vai para area_terreno_total, em m2) e a
   * construida, que NAO e area do terreno e fica separada para conferencia.
   */
  function candidatosAreaUrbana(texto) {
    const t = compacta(texto);
    const saida = [];
    // "com a área de 246,50m2", "com área de 175,00m²" (sem o "a"),
    // "área total: 300,00m²", "medindo 360,00m2".
    let m = t.match(/(?:terreno[^.]{0,80}?)?com\s+(?:a\s+)?[áa]rea\s+de\s+([\d.]+,\d+)\s*m[²2]/i);
    if (m) {
      saida.push({ valor: { valor: numeroBR(m[1]), unidade: 1 }, peso: 90,
        rotulo: 'area do terreno', trecho: compacta(m[0]) });
    }
    m = t.match(/[áa]rea\s+total\s*:?\s*(?:de\s*)?([\d.]+,\d+)\s*m[²2]/i);
    if (m) {
      saida.push({ valor: { valor: numeroBR(m[1]), unidade: 1 }, peso: 95,
        rotulo: 'area total', trecho: compacta(m[0]) });
    }
    // Ultimo recurso: qualquer "N,NNm²" que nao seja area construida.
    if (!saida.length) {
      const re = /([\d.]+,\d+)\s*m[²2]/gi;
      let x;
      while ((x = re.exec(t)) !== null) {
        const contexto = chave(t.slice(Math.max(0, x.index - 60), x.index));
        if (/constru[íi]d|edificad|benfeitoria/.test(contexto)) continue;
        saida.push({ valor: { valor: numeroBR(x[1]), unidade: 1 }, peso: 40,
          rotulo: 'area em m2 citada na descricao', trecho: compacta(t.slice(Math.max(0, x.index - 40), x.index + 12)) });
        break;
      }
    }
    return saida;
  }

  function extraiAreaConstruida(texto) {
    const m = compacta(texto).match(/([\d.]+,\d+)\s*m[²2]\s*de\s*[áa]rea\s*constru[íi]da/i)
      || compacta(texto).match(/[áa]rea\s*constru[íi]da\s*(?:de)?\s*:?\s*([\d.]+,\d+)\s*m[²2]/i);
    return m ? achado(numeroBR(m[1]), m[0], 'area construida') : null;
  }

  // -------------------------------------------------------- titularidade vigente

  /**
   * Le a tabela das averbacoes de "INDICACAO DE TITULARIDADE" (AV.37, AV.43,
   * AV.44 de uma matricula do acervo), que sao o retrato oficial de quem e dono e de quanto.
   *
   * Formato real (uma linha por co-proprietario):
   *   "Matr. Nome do Co-proprietario 42,67% 145,8218ha"
   *   "R.31 R.32 R.40 Outro Co-proprietario 40,63% 138,8503ha"
   *   "Espólio de <nome> ORIGEM 3,50% de 35,01% 4,1871"
   *
   * Nao ha CPF na tabela: o nome e casado depois com os CPF vistos no resto da
   * matricula. Quem nao casar fica sem documento - e pendencia, nao invencao.
   */
  function extraiTitularidade(textoAto) {
    const k = chave(textoAto);
    if (!/(indicacao (de )?(relacao )?titularidade|retificacao de indicacao)/.test(k)) return [];

    const saida = [];
    for (const linha of String(textoAto).split('\n')) {
      const l = compacta(linha);
      if (!l || /^(total|obs|dou fe|ato\b|co-propriet)/i.test(l)) continue;
      // Descarta os prefixos de ato ("Matr.", "R.31 R.32 R.40", "ORIGEM").
      const semPrefixo = l.replace(/^(?:(?:Matr\.?|R[.\-]?\s?\d+|AV[.\-]?\s?\d+|ORIGEM)\s*)+/i, '');
      const m = semPrefixo.match(/^([A-ZÀ-Ýa-zà-ÿ'.\s]{5,80}?)\s+(?:ORIGEM\s+)?(\d{1,3},\d{1,4})\s*%/);
      if (!m) continue;
      const nome = compacta(m[1]).replace(/\s+(ORIGEM|Matr\.?)$/i, '');
      if (!/[A-ZÀ-Ý]/.test(nome) || nome.split(/\s+/).length < 2) continue;
      saida.push({
        nome_completo: nome,
        percentual: numeroBR(m[2]),
        trecho: l.slice(0, 140),
      });
    }
    return saida;
  }

  /** Nome normalizado para casar a tabela de titularidade com os CPF do texto. */
  function chaveNome(nome) {
    return chave(nome)
      .replace(/\b(espolio de|de|da|do|dos|das|e)\b/g, ' ')
      .replace(/[^a-z0-9\s]/g, ' ')
      .replace(/\s+/g, ' ')
      .trim();
  }

  // ------------------------------------------------------------ confrontantes

  /**
   * Confrontantes do memorial descritivo. Dois formatos reais no acervo:
   *  - georreferenciado: "confrontando com a FAZENDA CHAPADAO / Mat. 1,812"
   *  - antigo: "confrontando com terras de <nome do lindeiro>, ao Norte"
   * O separador de milhar da matricula vem como virgula ("27,695" = 27.695).
   */
  function extraiConfrontantes(texto) {
    const t = compacta(texto);
    const saida = [];
    const vistos = new Set();
    const push = (nome, matricula, trecho) => {
      const limpo = compacta(nome || '')
        .replace(/^(?:e\s+)?com,?\s*/i, '')   // "; e com, Fulano..." -> "Fulano..."
        .replace(/^e\s+/i, '')
        .replace(/[.,;]+$/, '');
      const mat = matricula ? String(matricula).replace(/\D/g, '') : null;
      const clave = (mat || '') + '|' + chave(limpo);
      if (!limpo && !mat) return;
      if (vistos.has(clave)) return;
      vistos.add(clave);
      saida.push({
        nome_proprietario_confrontante: limpo || null,
        numero_matricula_confrontante: mat || null,
        trecho: compacta(trecho).slice(0, 140),
      });
    };

    let m;
    const reGeo = /confrontando com (?:a |o |as |os )?([^/;]{3,120}?)\s*\/\s*Mat\.?\s*([\d.,]{1,12})/gi;
    while ((m = reGeo.exec(t)) !== null) push(m[1], m[2], m[0]);

    // Memorial do SIGEF: "confrontando com CNS: 02.618-7 | Mat. 32844 | FAZENDA
    // VERA CRUZ" - matricula ANTES do nome, separadas por barra vertical.
    const reSigef = /confrontando com\s*CNS\s*:\s*[\d.\-]+\s*\|\s*Mat\.?\s*([\d.,]{1,12})\s*\|\s*([^|,;]{3,120}?)(?:\s+no azimute|,|;|$)/gi;
    while ((m = reSigef.exec(t)) !== null) push(m[2], m[1], m[0]);

    // A lista antiga vem separada por ";" e termina no ponto final - por isso o
    // ";" nao pode estar fora da captura, senao so o primeiro lindeiro aparece.
    const reAntigo = /confrontando com terras de ([^.]{3,400})/i;
    const ma = t.match(reAntigo);
    if (ma) {
      for (const parte of ma[1].split(';')) {
        const nome = parte.replace(/,?\s*(ao|à|a)\s+(Norte|Sul|Leste|Oeste|Nordeste|Noroeste|Sudeste|Sudoeste).*$/i, '');
        push(nome.replace(/^e\s+com,?\s*/i, ''), null, parte);
      }
    }
    return saida;
  }

  // ------------------------------------------------------------------ fachada

  /** Tudo que se pode saber do ato isolado. */
  function extraiAto(textoAto) {
    const classificacao = classificaAto(textoAto);
    const protocolo = extraiProtocolo(textoAto);
    const impostos = extraiImpostos(textoAto);
    return {
      data_ato: extraiDataAto(textoAto),
      protocolo_prenotacao: protocolo.numero,
      data_protocolo_prenotacao: protocolo.data,
      ato: classificacao.ato,
      alteracao_titularidade: classificacao.alteracao_titularidade,
      alteracao_imovel: classificacao.alteracao_imovel,
      valor_transacao: extraiValorTransacao(textoAto, classificacao),
      valor_imposto: impostos.valor_imposto,
      base_calculo_itbi: impostos.base_calculo_itbi,
      pessoas: extraiPessoas(textoAto),
      confrontantes: extraiConfrontantes(textoAto),
      areas: candidatosArea(textoAto),
      areasUrbanas: candidatosAreaUrbana(textoAto),
      area_construida: extraiAreaConstruida(textoAto),
      endereco: extraiEndereco(textoAto),
      cadastros: extraiCadastros(textoAto),
      geo: extraiGeo(textoAto),
    };
  }

  /** Cabecalho da matricula: numero e data de abertura. */
  function extraiAbertura(preambulo) {
    const t = compacta(preambulo);
    const out = {};
    // So vale o "MATRICULA N" do INICIO do documento. No meio do preambulo,
    // "Matricula n.º 454" e a matricula de ORIGEM (desmembramento), nao esta.
    // Os dois formatos do acervo: "MATRICULA N.º 1.118 -" e "MATRICULA: 6.529 -".
    const m = t.match(/MATR[ÍI]CULA\s*:?\s*(?:n\.?º?)?\s*:?\s*([\d.]{1,10})\s*[,.-]/i);
    if (m && m.index < 40) {
      out.numero_matricula = achado(m[1].replace(/\D/g, ''), m[0], 'cabecalho da matricula');
    }
    const md = t.slice(0, 200).match(/(\d{1,2}\s+de\s+[A-Za-zç]+\s+de\s+\d{4}|\d{2}[./]\d{2}[./]\d{4})/i);
    if (md) {
      out.data_matricula = achado(dataDeTexto(md[1]), md[0], 'cabecalho da matricula');
    } else {
      // Matricula sem cabecalho (aberta por desmembramento): a data de abertura
      // e a do fecho do preambulo ("Morrinhos-GO, 18 de julho de 2025").
      const mf = t.match(/Morrinhos[^,]{0,6},\s*(\d{1,2}\s+de\s+[A-Za-zçã]+\s+de\s+\d{4})/i);
      if (mf) out.data_matricula = achado(dataDeTexto(mf[1]), mf[0], 'fecho do preambulo');
      else {
        // "Protocolo n.º 177.671, de 27.06.2025" - o mesmo padrao do protocolo
        // dos atos, aproveitado aqui (os pontos do numero quebram regex ingenua).
        const prot = extraiProtocolo(t);
        if (prot.data) out.data_matricula = achado(prot.data.valor, prot.data.trecho, 'data do protocolo da abertura');
      }
    }
    return out;
  }

  global.ONR_EXTRATOR = {
    extraiAto,
    extraiAbertura,
    classificaAto,
    extraiPessoas,
    extraiDataAto,
    extraiProtocolo,
    extraiValorTransacao,
    extraiImpostos,
    candidatosArea,
    candidatosAreaUrbana,
    extraiAreaConstruida,
    extraiEndereco,
    extraiCadastros,
    extraiTitularidade,
    chaveNome,
    extraiConfrontantes,
    extraiGeo,
    extraiMunicipio,
    extraiNovoLogradouro,
    tipoDeLogradouro,
    cortaEm,
    MUNICIPIOS,
    _internos: { dataDeTexto, numeroBR, nomeAntesDe, regimeBensDe, estadoCivilDe },
  };
})(typeof window !== 'undefined' ? window : globalThis);
