'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const raiz = path.join(__dirname, '..');
const parcial = fs.readFileSync(path.join(raiz, 'backend/templates/mapa_onr.html'), 'utf8');
const indice = fs.readFileSync(path.join(raiz, 'backend/templates/index.html'), 'utf8');

test('AERI incorpora o conversor como interface nativa, sem iframe',()=>{
  assert.match(indice, /include 'mapa_onr\.html'/);
  assert.doesNotMatch(parcial, /<iframe|sandbox=|mapa-onr-frame/);
  for (const id of ['mapa-onr-nativo','texto','lista-atos','ficha-imovel','fichas-atos','btn-gerar','resultado']) {
    assert.match(parcial, new RegExp(`id="${id}"`));
  }
});

test('motor reconhece a interface nativa mesmo quando o AERI está incorporado no SYNC',()=>{
  const codigo=fs.readFileSync(path.join(raiz,'backend/static/mapa_onr/src/app.js'),'utf8');
  assert.match(codigo,/estaNaInterfaceNativa\(\) \|\| global\.parent === global/);
  assert.match(codigo,/if \(estaNaInterfaceNativa\(\)\) return;/);
});

function ambiente() {
  const elementos = new Map();
  const elemento = id => {
    if(!elementos.has(id)) elementos.set(id,{id,value:'7676',disabled:false,hidden:false,dataset:{},ouvintes:{},
      addEventListener(tipo,fn){this.ouvintes[tipo]=fn;}});
    return elementos.get(id);
  };
  const chamadas=[], cargas=[], eventos=[];
  const resultado={numero_matricula:'7676',tipo_imovel:'rural',texto:'MATRÍCULA FICTÍCIA',contexto_aeri:{modo:'hibrido'}};
  const contexto=vm.createContext({
    console,
    document:{getElementById:elemento},
    window:{
      AERI_MAPA_ONR:{
        carregarMatricula:carga=>{cargas.push(carga);return {numeroMatricula:'7676',totalAtos:3};},
        limpar:()=>cargas.push({tipo:'LIMPAR'}),
      },
      dispatchEvent:evento=>eventos.push(evento),
    },
    MessageEvent:class {constructor(tipo,opcoes){this.type=tipo;Object.assign(this,opcoes);}},
    requisicaoAeri:async(...args)=>{chamadas.push(args);return resultado;},
  });
  let codigo=fs.readFileSync(path.join(raiz,'backend/static/js/mapa_onr.js'),'utf8');
  codigo=codigo.replace(/^import .*;\r?\n/m,'const requisicaoAeri = globalThis.requisicaoAeri;')
    .replaceAll('export function','function');
  vm.runInContext(codigo+'\nglobalThis.teste={iniciarMapaOnr,limparMapaOnr,configurarAcessoMapaOnr};',contexto);
  return {contexto,api:contexto.teste,elemento,chamadas,cargas,eventos};
}

test('consulta entrega texto e contexto diretamente ao motor antes de mostrar sucesso',async()=>{
  const a=ambiente();a.api.iniciarMapaOnr();
  let preveniu=false;
  await a.elemento('form-mapa-onr').ouvintes.submit({preventDefault:()=>{preveniu=true;}});
  assert.equal(preveniu,true);assert.equal(a.chamadas.length,1);
  assert.equal(a.eventos[0].data.tipo,'AERI_MAPA_ONR_MATRICULA');
  assert.equal(a.cargas[0].texto,'MATRÍCULA FICTÍCIA');
  assert.match(a.elemento('mapa-onr-status').textContent,/3 ato\(s\) reconhecido/);
  assert.equal(a.elemento('mapa-onr-status').dataset.tipo,'sucesso');
});

test('permissão controla a interface nativa e logout limpa os dados transitórios',()=>{
  const a=ambiente();a.api.configurarAcessoMapaOnr(false);
  assert.equal(a.elemento('mapa-onr-nativo').hidden,true);
  a.api.configurarAcessoMapaOnr(true);
  assert.equal(a.elemento('mapa-onr-nativo').hidden,false);
  a.api.limparMapaOnr();
  assert.equal(a.eventos.at(-1).data.tipo,'AERI_MAPA_ONR_LIMPAR');
  assert.equal(a.cargas.at(-1).tipo,'LIMPAR');
});
