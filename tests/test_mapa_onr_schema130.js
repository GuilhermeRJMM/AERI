'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('fs'),path=require('path'),vm=require('vm');
const root=path.join(__dirname,'../backend/static/mapa_onr');
const c=vm.createContext({document:{querySelector:()=>({value:''})}});c.window=c;
for(const m of ['documento','enums','parser','extrator','builder','validator'])vm.runInContext(fs.readFileSync(path.join(root,'src',m+'.js'),'utf8'),c);
for(const tipo of ['rural','urbano'])vm.runInContext(fs.readFileSync(path.join(root,'schemas',tipo+'.schema.js'),'utf8'),c);

function judicial(tipo,extras={}){return {version:'1.3.0',cns:'026187',imoveis:[{
 tipo_imovel:tipo==='rural'?2:1,['contexto_'+tipo]:1,motivo_envio:2,
 tipo_matricula_transcricao:1,numero_matricula:'9999',decisao_jud:true,...extras}]};}
for(const tipo of ['rural','urbano'])test('esquema oficial 1.3.0 no navegador: '+tipo,()=>{
 const schema=c['ONR_SCHEMA_'+tipo.toUpperCase()];
 assert.equal(schema.properties.version.const,'1.3.0');
 assert.equal(c.ONR_VALIDATOR.valida(schema,judicial(tipo)).valido,true);
 for(const valor of [false,null,'true',1])assert.equal(c.ONR_VALIDATOR.valida(schema,judicial(tipo,{decisao_jud:valor})).valido,false);
 // O ramo judicial oficial permite propriedades adicionais; não endurecer a cópia oficial.
 assert.equal(c.ONR_VALIDATOR.valida(schema,judicial(tipo,{campo_inventado:true})).valido,true);
 const f={numero_matricula:'9999',decisao_jud:true,motivo_envio:2};
 const r=c.ONR_BUILDER.montaImovel(f,{tipo,versao:'1.3.0'});
 assert.equal(c.ONR_VALIDATOR.valida(schema,c.ONR_BUILDER.montaArquivo('026187',[r.imovel],'1.3.0')).valido,true);
 assert.deepEqual(JSON.parse(JSON.stringify(r.pendencias)),[]);
});

test('builder urbano 1.3 não emite certificacao_incra removida do esquema',()=>{
 const r=c.ONR_BUILDER.montaImovel({numero:'9999',certificacao_incra:true},{tipo:'urbano',versao:'1.3.0'});
 assert.equal(Object.hasOwn(r.imovel,'certificacao_incra'),false);
 const legado=c.ONR_BUILDER.montaImovel({numero:'9999',certificacao_incra:true},{tipo:'urbano',versao:'1.2.0'});
 assert.equal(legado.imovel.certificacao_incra,true);
});
test('interface nativa e alternativa começam na versão ativa',()=>{
 for(const p of ['backend/templates/mapa_onr.html','backend/private/mapa_onr.html']){
  const h=fs.readFileSync(path.join(__dirname,'..',p),'utf8');
  assert.match(h,/<option value="1\.3\.0" selected>/);
 }
});

test('wrappers atuais e legados são cópias estruturais dos JSONs oficiais',()=>{
 for(const [tipo,plural] of [['rural','rurais'],['urbano','urbanos']]){
  vm.runInContext(fs.readFileSync(path.join(root,'schemas',tipo+'-legado.schema.js'),'utf8'),c);
  for(const [versao,global_] of [['','ONR_SCHEMA_'+tipo.toUpperCase()],['v1.2.0','ONR_SCHEMA_'+tipo.toUpperCase()+'_LEGADO']]){
   const json=JSON.parse(fs.readFileSync(path.join(root,'schemas',versao,'imoveis-'+plural+'-onr.schema.json'),'utf8'));
   assert.deepEqual(JSON.parse(JSON.stringify(c[global_])),json);
  }
 }
});
