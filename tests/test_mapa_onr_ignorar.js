'use strict';
// Somente dados sintéticos. Exercita os handlers reais de exportação.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const codigo = fs.readFileSync(path.join(__dirname, '../backend/static/mapa_onr/src/app.js'), 'utf8');
const boot = "document.addEventListener('DOMContentLoaded', iniciar);";
assert.ok(codigo.includes(boot));

function ambiente() {
  class Elemento {
    constructor(tag) { this.tag = tag; this.children = []; this.value = ''; this._text = ''; }
    set textContent(v) { this._text = v; this.children = []; }
    get textContent() { return this._text + this.children.map(c => c.textContent).join(''); }
    appendChild(c) { this.children.push(c); return c; }
    scrollIntoView() {}
    click() { baixados.push(this.download); }
    remove() {}
  }
  const elementos = new Map();
  function campo(sel) {
    if (!elementos.has(sel)) elementos.set(sel, new Elemento('div'));
    return elementos.get(sel);
  }
  for (const [sel, valor] of Object.entries({'#tipo-imovel':'rural', '#cns':'026187', '#versao':'1.2.0', '#texto':'Texto fictício'})) campo(sel).value = valor;
  const copiados = [], baixados = [], confirmacoes = [], blobs = [], chamadas = [];
  const pendencia = {campo:'dados_pessoa[0].cpf_cnpj', motivo:'CPF com dígito verificador inválido'};
  const imovel = {numero_matricula:'7676', dados_pessoa:[{nome_completo:'Pessoa Fictícia', cpf_cnpj:'12345678900'}]};
  const ctx = vm.createContext({
    document:{querySelector:campo, createElement:t=>new Elemento(t), createTextNode:t=>Object.assign(new Elemento('#text'), {textContent:t}), body:new Elemento('body')},
    confirm:()=>{throw new Error('confirm() e bloqueado no iframe do SYNC');}, alert:()=>{},
    navigator:{clipboard:{writeText:async s=>copiados.push(s)}},
    Blob:class { constructor(parts) { blobs.push(parts.join('')); } },
    URL:{createObjectURL:()=> 'blob:teste'},
    ONR_BUILDER:{montaImovel:()=>({imovel:structuredClone(imovel), pendencias:[pendencia], avisos:[]}), montaArquivo:(cns, imoveis)=>({cns,imoveis})},
    ONR_VALIDATOR:{valida:()=>({valido:true, erros:[]})},
  });
  // O conversor nao da fetch: pede a validacao ao AERI por postMessage. O stub
  // faz o papel do AERI, inclusive podendo adiar a resposta.
  const ouvintesMsg = [], adiados = [];
  ctx.validacao = ()=>({dados:{valido:true,erros:[]}});
  // Guarda: dentro do iframe a origem e opaca e connect-src 'self' nao casa
  // com nada. Qualquer fetch daqui derruba a suite.
  ctx.fetch = ()=>{ throw new Error('fetch e bloqueado no iframe do MAPA-ONR'); };
  ctx.addEventListener = (tipo,fn)=>{ if(tipo==='message') ouvintesMsg.push(fn); };
  ctx.removeEventListener = (tipo,fn)=>{ const i=ouvintesMsg.indexOf(fn); if(i>=0) ouvintesMsg.splice(i,1); };
  ctx.setTimeout = ()=>0;
  ctx.clearTimeout = ()=>{};
  ctx.parent = {postMessage:(msg)=>{
    if(!msg || msg.tipo!=='AERI_MAPA_ONR_VALIDAR') return;
    chamadas.push(msg);
    const responder=(r)=>{ for(const fn of ouvintesMsg.slice())
      fn({data:Object.assign({tipo:'AERI_MAPA_ONR_VALIDADO', id:msg.id}, r)}); };
    if(ctx.adiar) adiados.push(responder); else responder(ctx.validacao());
  }};
  const liberarAdiada = (r)=>adiados.shift()(r);
  vm.runInContext(codigo.replace(boot, 'global.teste = {estado, gerar, renderResultado, assinaturaExportacao};'), ctx);
  const api = ctx.teste;
  api.estado.atos = [{numero:'0',ehAbertura:true}];
  api.estado.fichasAto = {'0':{pessoas:imovel.dados_pessoa}};
  api.estado.fichaImovel = {numero_matricula:'7676'};
  api.estado.selecionados.add('0');
  const nodes = (node=campo('#resultado')) => [node, ...node.children.flatMap(c=>nodes(c))];
  const botoes = () => nodes().filter(n=>n.tag==='button');
  const caixas = () => nodes().filter(n=>n.tag==='input' && n.type==='checkbox');
  function marcar(valor=true, indice=0) { const check=caixas()[indice]; check.checked=valor; check.onchange(); }
  const texto = () => campo('#resultado').textContent;
  return {ctx,api,campo,botoes,caixas,marcar,texto,copiados,baixados,blobs,confirmacoes,chamadas,liberarAdiada};
}

test('marcar a caixa ignora a pendência sem modal, preservando CPF e JSON originais', async()=>{
  const a=ambiente(); await a.api.gerar();
  const original=JSON.stringify(a.api.estado.resultado.arquivo);
  assert.equal(a.botoes().length,0);
  a.marcar();
  assert.match(a.texto(),/liberado com ressalvas/); assert.match(a.texto(),/Ignorada — Abertura · CPF\/CNPJ · Pessoa Fictícia/);
  assert.equal(a.botoes().length,2);
  a.botoes()[0].onclick(); await Promise.resolve();
  a.botoes()[1].onclick();
  assert.equal(JSON.stringify(JSON.parse(a.copiados[0])),original);
  assert.equal(JSON.stringify(JSON.parse(a.blobs[0])),original);
  assert.equal(JSON.parse(a.copiados[0]).imoveis[0].dados_pessoa[0].cpf_cnpj,'12345678900');
  assert.equal(a.baixados.length,1);
  a.marcar(false); assert.equal(a.botoes().length,0);
});

test('não ignora outra pendência nem reaproveita a escolha em uma nova geração',async()=>{
  const a=ambiente(); await a.api.gerar();
  a.api.estado.resultado.relatorio[0].pendencias.push({campo:'dados_pessoa[1].cpf_cnpj',motivo:'CPF inválido'});
  a.api.renderResultado(); a.marcar();
  assert.equal(a.botoes().length,0); assert.equal(a.caixas()[1].checked,false);
  a.marcar(true,1); assert.equal(a.botoes().length,2);
  await a.api.gerar(); assert.equal(a.botoes().length,0);
  assert.equal(a.api.estado.resultado.ignoradas.size,0);
});

test('erro de schema no cliente continua bloqueando após ignorar a pendência',async()=>{
  const a=ambiente(); await a.api.gerar();
  a.api.estado.resultado.validacao={valido:false,erros:[{path:'imoveis[0].dados_pessoa[0].cpf_cnpj',message:'Formato inválido'}]};
  a.api.renderResultado(); a.marcar();
  assert.equal(a.botoes().length,0); assert.match(a.texto(),/erro\(s\) de schema/);
});

for (const falha of ['schema','autenticação','comunicação','JSON inválido']) {
  test(`falha de ${falha} do servidor não pode ser ignorada`,async()=>{
    const a=ambiente();
    if(falha==='schema') a.ctx.validacao=()=>({dados:{valido:false,erros:[{mensagem:'Estrutura inválida'}]}});
    if(falha==='autenticação') a.ctx.validacao=()=>({erro:'Sessão expirada'});
    if(falha==='comunicação') a.ctx.validacao=()=>({erro:'Sem conexão'});
    if(falha==='JSON inválido') a.ctx.validacao=()=>({erro:'JSON inválido'});
    await a.api.gerar(); a.marcar();
    assert.equal(a.botoes().length,0); assert.match(a.texto(),/não foi liberado/);
  });
}

test('edição da entrada invalida botões antigos, inclusive cópia e download',async()=>{
  const a=ambiente(); await a.api.gerar(); a.marcar();
  const antigos=a.botoes(); a.campo('#cns').value='000001';
  antigos.forEach(b=>b.onclick());
  assert.equal(a.copiados.length,0); assert.equal(a.baixados.length,0);
  assert.equal(a.botoes().length,0); assert.match(a.texto(),/dados foram alterados/);
});

test('resposta atrasada não substitui validação da geração mais recente',async()=>{
  const a=ambiente();
  a.ctx.adiar=true;
  const antiga=a.api.gerar();
  a.ctx.adiar=false;
  a.ctx.validacao=()=>({dados:{valido:false,erros:[{mensagem:'Falha atual'}]}});
  await a.api.gerar(); const atual=a.api.estado.resultado;
  a.liberarAdiada({dados:{valido:true,erros:[]}}); await antiga;
  assert.equal(a.api.estado.resultado,atual); a.marcar();
  assert.equal(a.botoes().length,0); assert.match(a.texto(),/Falha atual/);
});
