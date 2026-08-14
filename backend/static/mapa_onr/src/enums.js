/**
 * Enums oficiais do Manual de Importacao ONR v1.3.0 (Rurais e Urbanos).
 * Fonte: Anexo I - Manual_Estruturacao_Imoveis_Rurais_Unificado_Overview_v1.3.0.pdf, secao 6.
 * Os enums NAO estao no JSON Schema do Anexo II (o schema usa apenas type/pattern),
 * por isso a validacao de dominio depende desta tabela.
 */
(function (global) {
  'use strict';

  const ENUMS = {
    tipo_imovel: { 1: 'Urbano', 2: 'Rural' },

    contexto_rural: {
      1: 'Imovel Rural Padrao',
      2: 'Imovel Rural da Uniao',
      3: 'Imovel Rural de Estrangeiros',
    },

    contexto_urbano: {
      1: 'Imovel Urbano Padrao',
      2: 'Imovel Urbano da Uniao',
    },

    motivo_envio: {
      1: 'Novo ato (ITN 003/2025)',
      2: 'Acervo (legado / georreferenciados / estrangeiros)',
    },

    tipo_matricula_transcricao: { 1: 'Matricula', 2: 'Transcricao' },

    situacao: {
      1: 'Ativa',
      2: 'Anulada',
      3: 'Bloqueada',
      4: 'Encerrada',
      5: 'Inexistente',
      6: 'Cancelada',
    },

    tipo_ato: { 1: 'Registro', 2: 'Averbacao' },

    ato: {
      1: 'Abertura de matricula',
      2: 'Abertura de matricula (oficio/decisao judicial)',
      3: 'Alteracao da relacao juridica',
      4: 'Transmissao-Aquisicao Originaria de Direitos Reais',
      5: 'Alteracao do imovel',
      6: 'Outro',
    },

    alteracao_titularidade: {
      1: 'Compra e Venda',
      2: 'Arrematacao',
      3: 'Cisao Total de Pessoa Juridica',
      4: 'Cisao Parcial de Pessoa Juridica',
      5: 'Dacao em pagamento',
      6: 'Doacao',
      7: 'Fusao de Pessoa Juridica',
      8: 'Integralizacao de capital social/Incorporacao Societaria',
      9: 'Partilha/Adjudicacao por Obito',
      10: 'Partilha por divorcio',
      11: 'Partilha por dissolucao de uniao estavel',
      12: 'Partilha por separacao',
      13: 'Partilha por nulidade ou anulacao do casamento',
      14: 'Permuta',
      15: 'Promessa de compra e venda',
      16: 'Outras nao onerosas',
      17: 'Outras onerosas',
      18: 'Usucapiao',
      19: 'Nao se aplica',
    },

    alteracao_imovel: {
      1: 'Aluviao',
      2: 'Avulsao',
      3: 'Desdobro',
      4: 'Desmembramento',
      5: 'Divisao',
      6: 'Estremacao',
      7: 'Formacao de ilha',
      8: 'Loteamento',
      9: 'Regularizacao fundiaria',
      10: 'Retificacao',
      11: 'Unificacao',
      12: 'Outro',
    },

    regime_utilizacao: {
      1: 'Aforamento',
      2: 'Ocupacao',
      3: 'CDRU',
      4: 'CUEM',
      5: 'Foro/Ocupacao',
      6: 'TAUS',
      7: 'Nao se aplica',
    },

    onerosa_nao_onerosa: { 1: 'Onerosa', 2: 'Nao onerosa' },

    estado_civil: {
      1: 'Solteiro',
      2: 'Casado',
      3: 'Separado',
      4: 'Divorciado',
      5: 'Viuvo',
      6: 'Uniao Estavel',
      7: 'Nao se aplica',
    },

    // ATENCAO: enum unificado na v1.1.0 - nao existe mais a distincao
    // "antes / na vigencia da Lei 6.515/77". Ver docs/divergencias.md.
    regime_bens: {
      1: 'Comunhao parcial',
      2: 'Comunhao universal',
      3: 'Separacao convencional/absoluta',
      4: 'Separacao legal/obrigatoria',
      5: 'Participacao final nos aquestos',
      6: 'Regime misto definido em pacto antenupcial',
      7: 'Regime estrangeiro',
    },

    relacao_juridica: {
      1: 'proprietario',
      2: 'usufrutuario',
      3: 'nu-proprietario',
      4: 'usuario',
      5: 'habitador',
      6: 'fundeiro',
      7: 'superficiario',
      8: 'fiduciante',
      9: 'fiduciario',
      10: 'arrendante',
      11: 'arrendatario',
      12: 'promitente comprador',
      13: 'multiproprietario',
      14: 'parceiro',
      15: 'expropriante',
      16: 'senhorio direto',
      17: 'enfiteuta',
      18: 'outros',
    },

    condicao_parte: { 1: 'alienante', 2: 'adquirente' },

    unidade_area: { 1: 'm2', 2: 'ha' },

    sistema_coordenadas: { 1: 'Geografica', 2: 'UTM' },

    fuso_zona: {
      1: '18 S', 2: '19 S', 3: '20 S', 4: '21 S', 5: '22 S',
      6: '23 S', 7: '24 S', 8: '25 S', 9: 'Nao informado',
    },

    sistema_referencia: {
      1: 'Sirgas 2000',
      2: 'SAD/69',
      3: 'Corrego Alegre',
      4: 'Astro Chua',
      5: 'nao informado',
    },

    categoria_poligono: { 1: 'Cat A', 2: 'Cat B', 3: 'Cat C' },

    genero: {
      1: 'Masculino',
      2: 'Feminino',
      3: 'Nao binario',
      4: 'Prefiro nao identificar',
    },

    filhos_brasileiros: { 1: 'Sim', 2: 'Nao', 3: 'Nao informado' },
  };

  /**
   * Tipo de logradouro: 311 valores no glossario. Mantemos apenas os usados no
   * dia a dia registral; a lista completa fica em docs/spec-v1.3.0.md.
   * Os codigos abaixo sao os oficiais (nao renumerar).
   */
  const TIPO_LOGRADOURO = {
    10: 'Alameda', 26: 'Avenida', 42: 'Beco', 59: 'Caminho', 71: 'Chacara',
    81: 'Condominio', 82: 'Conjunto', 86: 'Corrego', 117: 'Estrada',
    121: 'Fazenda', 135: 'Gleba', 144: 'Inaplicavel', 146: 'Jardim',
    153: 'Largo', 161: 'Lote', 162: 'Loteamento', 177: 'Nao Especificado',
    184: 'Outros', 191: 'Parque', 197: 'Pasto', 215: 'Praca', 221: 'Propriedade',
    223: 'Quadra', 232: 'Rancho', 236: 'Residencial', 238: 'Retiro',
    247: 'Rodovia', 250: 'Rua', 255: 'Sede', 258: 'Serra', 260: 'Servidao',
    262: 'Setor', 263: 'Sitio', 269: 'Terra', 270: 'Terreno', 273: 'Travessa',
    294: 'Via', 298: 'Vila', 301: 'Zona',
  };

  /** Codigos de UF (IBGE). */
  const UF = {
    11: 'RO', 12: 'AC', 13: 'AM', 14: 'RR', 15: 'PA', 16: 'AP', 17: 'TO',
    21: 'MA', 22: 'PI', 23: 'CE', 24: 'RN', 25: 'PB', 26: 'PE', 27: 'AL',
    28: 'SE', 29: 'BA', 31: 'MG', 32: 'ES', 33: 'RJ', 35: 'SP', 41: 'PR',
    42: 'SC', 43: 'RS', 50: 'MS', 51: 'MT', 52: 'GO', 53: 'DF',
  };

  /** Verdadeiro se `valor` pertence ao dominio do enum `nome`. */
  function valido(nome, valor) {
    const tabela = ENUMS[nome];
    if (!tabela) throw new Error('Enum desconhecido: ' + nome);
    return Object.prototype.hasOwnProperty.call(tabela, String(valor));
  }

  /** Rotulo legivel de um valor de enum, ou null. */
  function rotulo(nome, valor) {
    const tabela = ENUMS[nome];
    if (!tabela) return null;
    return tabela[String(valor)] || null;
  }

  /** Opcoes [{valor, rotulo}] para montar <select>. */
  function opcoes(nome) {
    const tabela = ENUMS[nome] || {};
    return Object.keys(tabela)
      .map(Number)
      .sort((a, b) => a - b)
      .map((v) => ({ valor: v, rotulo: tabela[v] }));
  }

  global.ONR_ENUMS = { ENUMS, TIPO_LOGRADOURO, UF, valido, rotulo, opcoes };
})(typeof window !== 'undefined' ? window : globalThis);
