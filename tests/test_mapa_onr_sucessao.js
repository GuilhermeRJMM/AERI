'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');

// Estrutura da 7.676, com nomes e documentos ficticios. Nenhum dado da Tri7
// e consultado ou persistido por esta suite.
const abertura = 'MATRÍCULA 7.676 - Morrinhos, 22 de fevereiro de 1988. '
  + 'IMÓVEL: Fazenda Exemplo, com área de 187 hectares. '
  + 'Proprietário: João Teste da Silva, brasileiro, fazendeiro, '
  + 'portador do CPF n.º 123.456.789-00, residente neste município.';
const benfeitorias = 'AV.01-7.676 - Data: 22.02.1988. AVERBAÇÃO DE BENFEITORIAS. '
  + 'No imóvel foi edificado uma casa de morada.';
const partilha = 'R.02-7.676 - Data: 22.02.1988. Nos termos do formal de partilha '
  + 'extraído dos autos de inventário e partilha dos bens deixados por falecimento de João Teste da Silva; '
  + 'julgado por sentença; coube à viúva meeira Maria Teste de Souza, brasileira, do lar, '
  + 'portadora do CPF n.º 111.444.777-35; em pagamento de sua meação o imóvel constante da presente matrícula, '
  + 'ficando ressalvados direitos de terceiros.';
const car = 'AV.03-7.676 - Data: 05.07.2018. INSCRIÇÃO NO CAR. Procede-se à presente averbação.';
const cep = 'AV.12-7.676 - Data: 31.08.2026. CÓDIGO DE ENDEREÇAMENTO POSTAL. CEP 75.650-000.';
const ccir = 'AV.13-7.676 - Data: 31.08.2026. ATUALIZAÇÃO DO CERTIFICADO DE CADASTRO DE IMÓVEL RURAL - CCIR.';
const raiz = path.join(__dirname, '../backend/static/mapa_onr/src');

function carregar(blocos) {
  const texto = blocos.join('\n----------------------------------------------------------------------------\n');
  const contexto = vm.createContext({
    document: {
      querySelector: (sel) => ({ value: ({ '#texto': texto, '#tipo-imovel': 'rural',
        '#cns': '026187', '#municipio': 'Morrinhos' })[sel] || '' }),
    },
  });
  for (const mod of ['documento', 'enums', 'parser', 'extrator', 'builder', 'validator']) {
    vm.runInContext(fs.readFileSync(path.join(raiz, mod + '.js'), 'utf8'), contexto);
  }
  const app = fs.readFileSync(path.join(raiz, 'app.js'), 'utf8');
  const inicializacao = "document.addEventListener('DOMContentLoaded', iniciar);";
  assert.ok(app.includes(inicializacao));
  // Executa o fluxo real de leitura/fichas sem renderizar ou chamar o backend.
  vm.runInContext(app.replace(inicializacao,
    'render = function() {}; global.teste = {lerMatricula, estado, antecessorSubstituidoNaPartilha};'), contexto);
  contexto.teste.lerMatricula();
  return contexto;
}

function temJoao(lista) {
  return lista.some((p) => /João Teste da Silva/.test(p.nome_completo));
}

function pendenciaCpf(ctx, numero) {
  const e = ctx.teste.estado;
  const fa = e.fichasAto[numero];
  const r = ctx.ONR_BUILDER.montaImovel({ ...e.fichaImovel, ...fa, dados_pessoa: fa.pessoas }, { tipo: 'rural' });
  return r.pendencias.filter((p) => /^dados_pessoa\[\d+\]\.cpf_cnpj$/.test(p.campo));
}

test('7.676: retira antecessor no R.02 sem apagar abertura e AV.01', () => {
  const ctx = carregar([abertura, benfeitorias, partilha, car, cep, ccir]);
  const e = ctx.teste.estado;
  assert.equal(temJoao(e.vigente.proprietarios), false);
  assert.equal(e.vigente.proprietarios.length, 1);
  assert.equal(e.vigente.proprietarios[0].nome_completo, 'Maria Teste de Souza');
  assert.equal(temJoao(e.vigente.snapshots['AV.01'].proprietarios), true);
  assert.equal(temJoao(e.vigente.snapshots['R.02'].proprietarios), false);
  for (const numero of ['0', '01']) {
    assert.equal(temJoao(e.fichasAto[numero].pessoas), true);
    assert.equal(pendenciaCpf(ctx, numero).length, 1, 'pendencia historica nao deve ser ocultada');
    assert.equal(e.fichasAto[numero].pessoas[0].cpf_cnpj, '12345678900');
  }
  for (const numero of ['02', '03', '12', '13']) {
    assert.equal(temJoao(e.fichasAto[numero].pessoas), false);
    assert.equal(pendenciaCpf(ctx, numero).length, 0);
  }
});

test('nao remove o antecessor em atribuicao de fracao', () => {
  for (const parcela of ['50% do imóvel', 'uma parte do imóvel', 'uma fração ideal do imóvel']) {
    const ctx = carregar([abertura, partilha.replace('o imóvel constante', parcela + ' constante'), car]);
    assert.equal(temJoao(ctx.teste.estado.vigente.proprietarios), true);
  }
});

test('simples obito nao transfere a propriedade', () => {
  const ctx = carregar([abertura, 'AV.02-7.676 - Data: 22.02.1988. ÓBITO. '
    + 'Averba-se o falecimento de João Teste da Silva.', car]);
  assert.equal(temJoao(ctx.teste.estado.vigente.proprietarios), true);
});

test('nao confunde o antecessor com nome maior ou outro falecido', () => {
  for (const nome of ['João Teste da Silva Junior', 'Pedro Teste da Silva']) {
    const ctx = carregar([abertura, partilha.replace('falecimento de João Teste da Silva;', 'falecimento de ' + nome + ';'), car]);
    assert.equal(temJoao(ctx.teste.estado.vigente.proprietarios), true);
  }
});

test('regra exige autor da heranca, nao mera mencao ao falecido', () => {
  const ctx = carregar([abertura, partilha.replace('bens deixados por falecimento', 'documentos com menção ao falecimento'), car]);
  assert.equal(temJoao(ctx.teste.estado.vigente.proprietarios), true);
});

test('identificacao nao depende de caixa, acentos ou numero da matricula', () => {
  const ctx = carregar([abertura, partilha.toUpperCase().replace(/JOÃO/g, 'JOAO'), car]);
  assert.equal(temJoao(ctx.teste.estado.vigente.proprietarios), false);
  const regra = ctx.teste.antecessorSubstituidoNaPartilha;
  assert.equal(regra(partilha.replace(/João Teste da Silva/g, 'Pedro Exemplo Neto'), { nome_completo: 'Pedro Exemplo Neto' }), true);
});

test('nao remove outro condomino nem aceita percentual na atribuicao', () => {
  const ctx = carregar([abertura]);
  const regra = ctx.teste.antecessorSubstituidoNaPartilha;
  assert.equal(regra(partilha, { nome_completo: 'Carlos Outro Titular' }), false);
  assert.equal(regra(partilha.replace('em pagamento', 'quanto a 50%, em pagamento'), { nome_completo: 'João Teste da Silva' }), false);
});

test('sucessora com CPF invalido continua gerando pendencia', () => {
  const ctx = carregar([abertura, partilha.replace('111.444.777-35', '111.444.777-00'), car]);
  assert.equal(temJoao(ctx.teste.estado.vigente.proprietarios), false);
  assert.equal(pendenciaCpf(ctx, '03').length, 1);
});

test('venda convencional continua retirando o transmitente pelo CPF', () => {
  const venda = 'R.02-7.676 - Data: 22.02.1988. VENDA E COMPRA. '
    + 'TRANSMITENTE: João Teste da Silva, brasileiro, CPF n.º 123.456.789-00. '
    + 'ADQUIRENTE: Maria Teste de Souza, brasileira, CPF n.º 111.444.777-35.';
  const ctx = carregar([abertura, venda, car]);
  assert.equal(temJoao(ctx.teste.estado.vigente.proprietarios), false);
  assert.equal(pendenciaCpf(ctx, '03').length, 0);
});

test('CIB alfanumerico com pontos substitui NIRF antigo na ficha e no JSON', () => {
  const ctx = carregar([abertura, partilha,
    'R.11-7.676 - Data: 09.10.2024. ESTREMAÇÃO. NIRF: 9.887.010-6.',
    ccir + ' CADASTRO IMOBILIÁRIO BRASILEIRO - CIB. Certidão de ITR, CIB: M.HRQ.PJR-M, emitida em 23.06.2026.',
    'R.14-7.676 - Data: 31.08.2026. ESTREMAÇÃO. CIB: M.HRQ.PJR-M, emitida em 23.06.2026.',
  ]);
  const e = ctx.teste.estado;
  assert.equal(e.vigente.campos.cib.valor, 'MHRQPJRM');
  assert.equal(e.vigente.campos.cib.ato, 'R.14');
  assert.equal(e.vigente.campos.cib.rotulo, 'CIB');
  assert.equal(e.fichaImovel.cib, 'MHRQPJRM');
  const fa = e.fichasAto['14'];
  const r = ctx.ONR_BUILDER.montaImovel({ ...e.fichaImovel, ...fa, dados_pessoa: fa.pessoas }, { tipo: 'rural' });
  assert.equal(r.imovel.cib, 'MHRQPJRM');
});

test('CIB aceita formatos numerico, alfanumerico, pontuado e compacto', () => {
  const ctx = carregar([abertura]);
  for (const [entrada, esperado] of [
    ['CIB: M.HRQ.PJR-M', 'MHRQPJRM'], ['CIB n.º MHRQPJR-M', 'MHRQPJRM'],
    ['CIB: m.hrq.pjr-m', 'MHRQPJRM'], ['CIB: M. HRQ. PJR - M', 'MHRQPJRM'],
    ['CIB: MHRQPJRM', 'MHRQPJRM'], ['CIB: 9.887.010-6.', '98870106'],
    ['CIB nº 9887010-6', '98870106'], ['CIB: 98870106;', '98870106'],
  ]) {
    assert.equal(ctx.ONR_EXTRATOR.extraiCadastros(entrada).cib.valor, esperado, entrada);
  }
});

test('CIB nao captura recibo do CAR, CCIR ou prefixo de numero maior', () => {
  const ctx = carregar([abertura]);
  for (const entrada of [
    'Recibo de Inscrição do Imóvel Rural no CAR, 98870106.',
    'CCIR: 78881964260.', 'CIB: M.HRQ.PJR-MM', 'CIB: 988701060',
    'CIB: MHRQPJRMZ', 'CIB: 9.887.010-60', 'CIB: 9.887.010',
  ]) assert.equal(ctx.ONR_EXTRATOR.extraiCadastros(entrada).cib, undefined, entrada);
});
