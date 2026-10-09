import assert from 'node:assert/strict';
import {gerarAutuacao, gerarConvocacao, gerarOficio, montarParesRtd} from '../backend/static/js/intimacao_documentos.js';

const pessoas = [
    {nome:'Pessoa A', cpf:'11111111111'},
    {nome:'Pessoa B', cpf:'22222222222'},
];
const enderecos = [
    'Rua A, 11, Centro, Morrinhos-GO, CEP 75650082',
    'Rua B, 22, Jardim América, Morrinhos-GO, CEP 75650292',
    'Rua C, 33, Centro, Goiânia-GO, CEP 74000000',
];
const pares = montarParesRtd(pessoas, enderecos);
assert.equal(pares.length, 4);
assert.deepEqual(pares.map(par => par.pessoa.nome), ['Pessoa A','Pessoa A','Pessoa B','Pessoa B']);
assert.deepEqual(pares.map(par => par.endereco.Numero), ['11','22','11','22']);
assert.ok(pares.every(par => par.endereco.Cidade === 'Morrinhos' && par.endereco.UF === 'GO'));

const dados = {
    in:'IN00000000C', dataGeracao:'09/10/2026', processo:'217507/2026', oficio:'INT/2026/042',
    protocolo:'186462', dataProtocolo:'06/10/2026', matricula:'30.338', registro:'R.03',
    credor:'Credora de teste', cnpj:'00.000.000/0001-00', titulo:'Contrato de Compra e Venda',
    contrato:'844441753253', dataContrato:'18/01/2018', pessoas,
    alvo:pessoas[0], enderecoImovel:'Rua Imóvel, 10, Morrinhos-GO', enderecos,
    dataProjecao:'09/10/2026', valorProjecao:'R$2.879,34',
    valorExtenso:'dois mil oitocentos e setenta e nove reais e trinta e quatro centavos',
    signatario:'Escrevente de teste',
};
assert.ok(gerarAutuacao(dados).includes('PROCESSO N.º 217507/2026'));
assert.ok(gerarAutuacao(dados).includes('DEVEDORES FIDUCIANTES'));
const oficio = gerarOficio(dados);
assert.equal((oficio.match(/page-break-after:always/g) || []).length, 2);
assert.ok(oficio.includes('<strong>PESSOA A, CPF n.º'));
assert.ok(oficio.includes('R$2.879,34 (dois mil oitocentos'));
assert.ok(oficio.includes('Rua A'));
assert.ok(!oficio.includes('Rua C'));
assert.ok(gerarConvocacao(dados).includes('30.338'));

console.log('Preparação RTD: duas pessoas em dois endereços geram quatro pedidos individuais.');
