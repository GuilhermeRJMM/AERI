'use strict';

const assert = require('node:assert/strict');

require('../backend/static/mapa_onr/src/documento.js');
require('../backend/static/mapa_onr/src/parser.js');
require('../backend/static/mapa_onr/src/extrator.js');

const extrator = globalThis.ONR_EXTRATOR;
const parser = globalThis.ONR_PARSER;

assert.equal(
  extrator.extraiDataAto('R.01 - 25 de abril de 1.995. VENDA E COMPRA.').valor,
  '25/04/1995',
);
assert.equal(
  parser.motivoEnvio('25/04/1995'),
  2,
);

const divisao = extrator.classificaAto(
  'R.09 - DIVISÃO AMIGÁVEL. Celebrada entre os condôminos.',
);
assert.equal(divisao.ato.valor, 4);
assert.equal(divisao.alteracao_titularidade.valor, 16);

const caracterizacao = extrator.classificaAto(
  'AV.06 - CARACTERIZAÇÃO DO IMÓVEL. Procede-se à retificação da descrição.',
);
assert.equal(caracterizacao.ato.valor, 5);
assert.equal(caracterizacao.alteracao_imovel.valor, 10);

const areas = extrator.candidatosArea(
  'AV.06 - GEORREFERENCIAMENTO. RETIFICADA passa a ter a área total de 2,6925ha.',
);
assert.equal(areas[0].valor.valor, 2.6925);

console.log('OK: regressões importadas do Json-ITN');
