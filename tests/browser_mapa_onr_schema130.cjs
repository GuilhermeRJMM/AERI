// Chrome local, dados fictícios, rede externa bloqueada. Transporte HTTP simulado;
// o corpo da validação é executado pelo serviço Python real, sem banco/Tri7.
const {chromium}=require('playwright');
const {spawnSync}=require('child_process');
const fs=require('fs'),path=require('path'),os=require('os'),assert=require('assert/strict');
const root=path.resolve(__dirname,'..'),python=process.env.AERI_TEST_PYTHON||'python';
const evidencia=path.join(os.tmpdir(),'mapa-onr-schema130.png');
(async()=>{const browser=await chromium.launch({channel:'chrome',headless:true});try{
 const page=await browser.newPage({viewport:{width:1440,height:1000}}),erros=[],validados=[];
 page.on('pageerror',e=>erros.push(e.message));
 page.on('console',m=>{if(m.type()==='error')erros.push(m.text());});
 await page.route('**/*',async route=>{
  const u=new URL(route.request().url());if(u.hostname!=='mapa-teste.invalid')return route.abort();
  if(u.pathname==='/')return route.fulfill({contentType:'text/html; charset=utf-8',body:'<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><title>MAPA-ONR — Teste</title><link rel="stylesheet" href="/static/styles.css"><link rel="stylesheet" href="/static/sync-theme.css"></head><body>'+fs.readFileSync(path.join(root,'backend/templates/mapa_onr.html'),'utf8')+'</body></html>'});
  if(u.pathname==='/api/mapa-onr/validar-json'){
   const dados=route.request().postDataJSON();
   const r=spawnSync(python,['-B','-c','import sys,json; from backend.app.servicos.mapa_onr import validar_json_mapa_onr; d=json.load(sys.stdin); print(json.dumps(validar_json_mapa_onr(d["tipo"],d["arquivo"])))'],{cwd:root,input:JSON.stringify(dados),encoding:'utf8',env:{...process.env,PYTHONIOENCODING:'utf-8'}});
   assert.equal(r.status,0,r.stderr);const resposta=JSON.parse(r.stdout);validados.push({dados,resposta});
   return route.fulfill({contentType:'application/json',body:r.stdout});
  }
  if(u.pathname.startsWith('/static/')){const f=path.resolve(root,'backend','.'+u.pathname);if(!f.startsWith(path.join(root,'backend/static')+path.sep)||!fs.existsSync(f))return route.abort();return route.fulfill({contentType:f.endsWith('.css')?'text/css':'text/javascript',body:fs.readFileSync(f)});}
  return route.abort();
 });
 await page.goto('https://mapa-teste.invalid/');assert.match(await page.title(),/MAPA-ONR/);
 assert.deepEqual(erros,[],'Carregamento dos scripts');
 await page.evaluate(()=>{document.body.className='sync-tema';document.querySelector('.page').classList.add('active');document.querySelector('#mapa-onr-nativo').hidden=false;});
 assert.equal(await page.locator('#versao').inputValue(),'1.3.0');
 for(const tipo of ['rural','urbano']){
  await page.evaluate(tipo=>window.AERI_MAPA_ONR.carregarMatricula({numeroMatricula:'9999',tipoImovel:tipo,texto:'Matrícula nº 9.999. Imóvel fictício.\n----------------------------------------------------------------------------\nAV.01-9999 - Morrinhos, 11 de novembro de 2026. Nos termos do acórdão do Tribunal de Justiça, procede-se ao cancelamento da penhora.'}),tipo);
  const decisao=page.getByLabel('Decisão Judicial do AV.01',{exact:true});assert.equal(await decisao.inputValue(),'true');
  await page.getByRole('button',{name:'Desmarcar todos',exact:true}).click();
  await page.locator('#lista-atos tr').filter({has:page.locator('td',{hasText:/^AV\.01$/})}).locator('input[type=checkbox]').check();
  await page.locator('#btn-gerar').click();
  await page.getByRole('button',{name:'Baixar JSON',exact:true}).waitFor();
  const prom=page.waitForEvent('download');await page.getByRole('button',{name:'Baixar JSON',exact:true}).click();const dl=await prom;
  const json=JSON.parse(fs.readFileSync(await dl.path(),'utf8'));assert.equal(json.version,'1.3.0');assert.equal(json.imoveis.length,1);assert.equal(json.imoveis[0].decisao_jud,true);
  assert(validados.at(-1).resposta.valido,'Servidor real aceitou arquivo '+tipo);
  // A alteração manual invalida o download e não é sobrescrita na renderização.
  await decisao.selectOption('false');await page.locator('#btn-gerar').click();
  await page.waitForFunction(()=>!document.querySelector('#resultado').innerText.includes('Baixar JSON'));
  assert.equal(await decisao.inputValue(),'false');assert.equal(validados.at(-1).resposta.valido,false);
  await decisao.selectOption('true');await page.locator('#versao').selectOption('1.2.0');await page.locator('#btn-gerar').click();
  await page.waitForFunction(()=>document.querySelector('#resultado').innerText.includes('exige versão 1.3.0'));
  assert.equal(await page.getByRole('button',{name:'Baixar JSON',exact:true}).count(),0);
  await page.locator('#versao').selectOption('1.3.0');await page.locator('#btn-gerar').click();await page.getByRole('button',{name:'Baixar JSON',exact:true}).waitFor();
 }
 await page.locator('#resultado').screenshot({path:evidencia});
 await page.setViewportSize({width:390,height:844});assert(await page.locator('#versao').isVisible());
 await page.locator('[data-aba="validar"]').click();
 for(const tipo of ['rural','urbano']){
  const arquivo={version:'1.3.0',cns:'026187',imoveis:[{tipo_imovel:tipo==='rural'?2:1,['contexto_'+tipo]:1,motivo_envio:2,tipo_matricula_transcricao:1,numero_matricula:'9999',decisao_jud:true}]};
  await page.locator('#json-externo').fill(JSON.stringify(arquivo));await page.locator('#btn-validar').click();
  assert.match(await page.locator('#saida-validador').innerText(),/1 imovel\(is\) - valido/);
 }
 await page.locator('#json-externo').fill(JSON.stringify({version:'1.2.0',cns:'026187',imoveis:[]}));await page.locator('#btn-validar').click();
 assert.match(await page.locator('#saida-validador').innerText(),/minItems/);assert.doesNotMatch(await page.locator('#saida-validador').innerText(),/version/);
 await page.locator('#json-externo').fill(JSON.stringify({version:'9.9.9',cns:'026187',imoveis:[]}));await page.locator('#btn-validar').click();
 assert.match(await page.locator('#saida-validador').innerText(),/erro\(s\)/);
 for(const invalido of ['null','[]','{"imoveis":{}}']){await page.locator('#json-externo').fill(invalido);await page.locator('#btn-validar').click();assert.match(await page.locator('#saida-validador').innerText(),/Arquivo inválido/);}
 assert.deepEqual(erros,[]);console.log(JSON.stringify({resultado:'OK',validacoesPython:validados.length,screenshot:evidencia,fluxo:'Nativo: decisão automática → exportação rural/urbana 1.3 → correção manual → bloqueio legado 1.2',console:erros}));
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1;});
