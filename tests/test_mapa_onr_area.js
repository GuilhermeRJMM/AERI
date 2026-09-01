'use strict';
// Area do imovel no MAPA-ONR. Dados ficticios; nenhuma consulta a Tri7.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');

const raiz = path.join(__dirname, '../backend/static/mapa_onr/src');
const ctx = vm.createContext({ console });
for (const m of ['documento', 'enums', 'parser', 'extrator']) {
  vm.runInContext(fs.readFileSync(path.join(raiz, m + '.js'), 'utf8'), ctx);
}
const area = (texto, opcoes) => ctx.ONR_EXTRATOR.candidatosArea(texto, opcoes || {});
const melhor = (texto) => {
  const c = area(texto, { descricao: true });
  return c.length ? c.sort((x, y) => y.peso - x.peso)[0].valor.valor : null;
};

test('acervo antigo em alqueires convertidos: ha + ares + centiares', () => {
  // Forma da matricula 777. Antes da ponte "alqueires, correspondentes a",
  // a area do imovel rural saia vazia: a regra por extenso esperava hectares
  // logo apos "area de", e a regra "totalizando" exige aquela palavra.
  const t = 'constituido de 3(tres) glebas de terras contiguas e ora unificadas, '
    + 'com a área total de 58,9493 alqueires, correspondentes a 285 hectares, '
    + '31 ares e 50 centiares. Sendo: a primeira com a área de 45 alqueires.';
  assert.equal(melhor(t), 285.315);
});

test('a mesma forma sem alqueires continua valendo', () => {
  const t = 'IMÓVEL: Fazenda Exemplo, com a área de 66 (sessenta e seis) hectares, '
    + '85 (oitenta e cinco) ares e 67 (sessenta e sete) centiares.';
  assert.equal(melhor(t), 66.8567);
});

test('área decimal na descrição continua valendo', () => {
  assert.equal(melhor('IMÓVEL: Fazenda Exemplo, com a área de 281,5458ha, no lugar tal.'), 281.5458);
});

test('a ponte não vale fora de ato que descreve o imóvel', () => {
  // Sem descricao:true a area por extenso nao entra -- e o que impede a gleba
  // VENDIDA num R-xx de virar a area do imovel.
  const t = 'vende a gleba com a área total de 10 alqueires, correspondentes a '
    + '48 hectares, 40 ares e 0 centiares.';
  assert.equal(area(t, {}).length, 0);
});

test('alqueires sem a conversão em hectares não inventa área', () => {
  assert.equal(melhor('com a área total de 58,9493 alqueires de culturas.'), null);
});
