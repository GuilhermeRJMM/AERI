import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {perfisDoTitulo,pertinenteAoTitulo,numeroDigitado} from '../backend/static/js/nota_regras.js';
const python=process.env.AERI_PYTHON;if(!python)throw Error('Configure AERI_PYTHON.');
const cat=JSON.parse(execFileSync(python,['-B','-X','utf8','-c','import json;from backend.app.gerador_notas.servico import catalogo_para_tela;print(json.dumps(catalogo_para_tela()))'],{encoding:'utf8'}));
const casos=[['Formal de Partilha','inventario'],['Inventário e partilha','inventario'],
 ['Escritura Pública de Compra e Venda','transferencia'],['VENDA E COMPRA','transferencia'],
 ['Doação','doacao'],['Averbação de construção','construcao'],['EDIFICAÇÃO','construcao'],
 ['Retificação de área','area'],['Georreferenciamento','area'],['Desmembramento rural','parcelamento'],
 ['Loteamento','parcelamento'],['Incorporação imobiliária','condominio'],['Condomínio','condominio'],
 ['Alienação fiduciária','garantia'],['Cédula de Produto Rural','garantia'],['Penhor','garantia'],
 ['Cancelamento de hipoteca','cancelamento'],['Certidão de óbito','cadastro']];
for(const [titulo,perfil] of casos)for(const variante of [titulo,titulo.toUpperCase(),`  ${titulo}  `])
 assert(perfisDoTitulo(variante,cat.filtros_titulo).some(p=>p.id===perfil),variante);
for(const titulo of ['', 'Escritura Pública','Mandado judicial','Título não classificado']) {
 const perfis=perfisDoTitulo(titulo,cat.filtros_titulo);assert.equal(perfis.length,0);
 assert.equal(cat.exigencias.filter(e=>pertinenteAoTitulo(e,perfis)).length,72);
}
assert(cat.exigencias.every(e=>e.contextos.length>0),'Todos os itens classificados explicitamente');
const construcao=perfisDoTitulo('Averbação de construção',cat.filtros_titulo);
assert(pertinenteAoTitulo(cat.exigencias.find(e=>e.id==='construcao-sem-habite-se'),construcao));
assert(!pertinenteAoTitulo(cat.exigencias.find(e=>e.id==='itbi-nao-apresentado'),construcao));
assert.equal(perfisDoTitulo('Compra e venda com alienação fiduciária',cat.filtros_titulo).length,2);
for(const [entrada,saida] of [['',''],['18552','18552'],['18.552','18552'],['1.234.567','1234567']])assert.equal(numeroDigitado(entrada),saida);
for(const invalido of ['R.20','123 e 456','12,34','1e3','-10','１２３','1234567890123','1.23'])assert.equal(numeroDigitado(invalido),null);
console.log('OK: perfis, acentos/caixa, títulos mistos e desconhecidos, cobertura dos 72 itens e entradas numéricas.');
