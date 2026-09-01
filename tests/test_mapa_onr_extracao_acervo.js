'use strict';
// Data do ato e cadastro rural no acervo antigo. Dados ficticios inspirados em
// formas reais; nenhuma consulta a Tri7.
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
const data = (t) => { const r = ctx.ONR_EXTRATOR.extraiDataAto(t); return r ? r.valor : null; };
const sncr = (t) => { const c = ctx.ONR_EXTRATOR.extraiCadastros(t); return c.cod_sncr ? c.cod_sncr.valor : null; };

test('dia ordinal na data por extenso', () => {
  // "1º de dezembro" (R-04 da 777): o "º" quebrava a leitura e o ato ia sem
  // data, o que faz o schema do ONR recusar o imovel inteiro.
  assert.equal(data('R-04-777 - Morrinhos, 1º de dezembro de 1977. Devedores: Fulano.'), '01/12/1977');
  assert.equal(data('AV-20-2.000- Morrinhos, 1º de agosto de 1996. Cancelamento: a requerimento.'), '01/08/1996');
  assert.equal(data('MATRÍCULA 777 - Morrinhos, 3 de dezembro de 1976. IMÓVEL: Fazenda.'), '03/12/1976');
});

test('ano de dois dígitos, com o século decidido pelo que já aconteceu', () => {
  assert.equal(data('AV-10-777 - Morrinhos, 29/08/93. Cancelamento: a requerimento.'), '29/08/1993');
  // Ato de matricula nao pode ser datado no futuro: 2093 seria absurdo.
  const ano = Number(data('AV-10-777 - Morrinhos, 29/08/93.').slice(-4));
  assert.ok(ano <= new Date().getFullYear(), 'nao pode cair no futuro');
  // Quatro digitos continuam mandando.
  assert.equal(data('AV.30-777 - Data: 20.02.2019. Protocolo n.º 149.150.'), '20/02/2019');
});

test('código do INCRA separado por hífen e rótulo no plural', () => {
  // Forma da 777: "sob o nos 22-04-013-50339". Antes so digitos e pontos eram
  // aceitos, e o plural "nos" nao era previsto: o imovel saia sem cadastro
  // rural nenhum.
  assert.equal(sncr('Cadastradas no Incra sob o nos 22-04-013-50339; com 273,4ha; módulo 62.'), '220401350339');
  assert.equal(sncr('Cadastrado no Incra sob o n° 22-04-013.50313; com 72,6ha.'), '220401350313');
  assert.equal(sncr('Cadastrado no INCRA sob o nº 936.120.001.570; com 377,5ha.'), '936120001570');
});

test('averbação posterior atualiza o cadastro do INCRA', () => {
  // Caso da 748: o INCRA renumerou e um ato seguinte declara o codigo novo.
  const t = 'Cadastrado no Incra sob o n° 22-04-013.50313; com 72,6ha. '
    + '---- O imóvel retro matriculado está cadastrado no Incra sob o n° 936.120.009.709, com 72,6ha.';
  assert.equal(sncr(t), '936120009709');
});

test('CCIR transcrito não sobrepõe o cadastro declarado pelo oficial', () => {
  // Caso da 716 e da 2.600: o bloco de CCIR traz "codigo do imovel rural" de
  // uma unidade cadastral MAIOR (943,6ha para um imovel de 377,5ha). Ele so
  // vale quando nao existe a forma "INCRA ... sob o".
  const t = 'Cadastrado no Incra sob o nº 936.120.001.570; com 377,5ha. '
    + '---- CCIR n.º 25173701197, exercício 2019; código do imóvel rural: 936.120.000.892-3; '
    + 'área total: 943,6415ha.';
  assert.equal(sncr(t), '936120001570');
  // Sem a forma oficial, o CCIR entra como reserva.
  assert.equal(sncr('CCIR: código do imóvel rural: 936.120.000.892-3; área total: 943,6415ha.'), '9361200008923');
});

test('"não se aplica" não pode cair em quem tem CPF', () => {
  // Na 777 o executado Antonio Jose (CPF) virou "nao se aplica" porque a
  // exequente "Adubos Araguaia ... LTDA. CNPJ" aparece dois nomes antes, na
  // MESMA frase. O erro ainda se propagava por CPF para outros atos. Quem
  // decide e o documento da pessoa, nao a vizinhanca.
  const t = 'EXECUCAO. Procedo a esta averbacao, sendo EXEQUENTE, ADUBOS EXEMPLO '
    + 'INDUSTRIA E COMERCIO LTDA. CNPJ Nº 03.306.578/0012-11, estabelecida em '
    + 'Anapolis-GO e EXECUTADOS, FULANO DE TAL EXEMPLO, inscrito no CPF/MF sob '
    + 'o n.º 300.169.591-91.';
  const pessoas = ctx.ONR_EXTRATOR.extraiPessoas(t, {});
  const fisica = pessoas.find((p) => (p.cpf_cnpj || '').length === 11);
  const juridica = pessoas.find((p) => (p.cpf_cnpj || '').length === 14);
  assert.ok(fisica, 'a pessoa fisica precisa ser reconhecida');
  assert.notEqual(fisica.estado_civil, 7,
    'pessoa com CPF nunca pode sair como "nao se aplica"');
  if (juridica) {
    assert.equal(juridica.estado_civil, 7, 'a pessoa juridica continua com "nao se aplica"');
  }
});
