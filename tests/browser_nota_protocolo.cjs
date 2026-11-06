// Navegador real; servidor e dados fictícios. Nenhum acesso a produção.
const {chromium}=require('playwright'),fs=require('fs'),path=require('path'),assert=require('assert/strict');
const root=path.resolve(__dirname,'..');
(async()=>{const b=await chromium.launch({channel:'chrome',headless:true});try{
 const p=await b.newPage({viewport:{width:1440,height:960}}),erros=[];let atrasar=null,liberar=null,confirmar=null,modo='normal';
 p.on('pageerror',e=>erros.push(e.message));
 await p.route('**/*',async r=>{
  const u=new URL(r.request().url());if(u.hostname!=='nota-teste.invalid')return r.abort();
  if(u.pathname==='/'){
   let h=fs.readFileSync(path.join(root,'backend/templates/index.html'),'utf8').replace(/\{%\s*include\s+['"]([^'"]+)['"]\s*%\}/g,(_,n)=>fs.readFileSync(path.join(root,'backend/templates',n),'utf8'));
   h=h.replace(/<script type="module" src="\/static\/js\/app.js[^\"]*"><\/script>/,`<script type="module">import {iniciarConsultaProtocoloNota} from '/static/js/nota_protocolo.js';import {definirCsrfToken} from '/static/js/api.js?v=20260902-arquivo-v1';definirCsrfToken('teste-csrf');document.getElementById('splash-aeri').remove();document.body.classList.remove('splash-active','auth-pending');document.querySelectorAll('.page').forEach(e=>e.classList.remove('active'));document.getElementById('page-geradornotas').classList.add('active');document.getElementById('gn-editor').hidden=false;window.previas=0;window.consulta=iniciarConsultaProtocoloNota(()=>window.previas++);window.consulta.configurar(true,'usuario-a');</script>`);
   return r.fulfill({contentType:'text/html; charset=utf-8',body:h});
  }
  if(u.pathname==='/api/gerador-notas/consultar-protocolo'){
   assert.equal(r.request().headers()['x-csrf-token'],'teste-csrf');
   const n=r.request().postDataJSON().protocolo.replace(/\./g,'');
   if(atrasar){confirmar();await atrasar;}
   return r.fulfill({status:modo==='erro'?502:200,contentType:'application/json',body:JSON.stringify(modo==='erro'?{detail:'Consulta indisponível; preencha manualmente.'}:{protocolo:n,titulo:modo==='vazio'?'':n==='186805'?'FORMAL DE PARTILHA':'ESCRITURA PÚBLICA DE VENDA E COMPRA'})});
  }
  if(u.pathname.startsWith('/static/')){
   const f=path.resolve(root,'backend','.'+u.pathname);if(!f.startsWith(path.join(root,'backend/static')+path.sep)||!fs.existsSync(f))return r.abort();
   return r.fulfill({contentType:f.endsWith('.css')?'text/css':f.endsWith('.png')?'image/png':'text/javascript',body:fs.readFileSync(f)});
  }return r.abort();
 });
 await p.goto('https://nota-teste.invalid/');await p.locator('#gn-editor').waitFor({state:'visible'});
 await p.locator('#gn-protocolo').fill('186.804');
 await p.waitForFunction(()=>document.getElementById('gn-titulo').value==='ESCRITURA PÚBLICA DE VENDA E COMPRA');
 assert.equal(await p.locator('#gn-judicial').isChecked(),false);
 await p.locator('#gn-titulo').fill('Meu título revisado');await p.locator('#gn-protocolo').fill('186805');
 await p.locator('#gn-usar-titulo-tri7').waitFor({state:'visible'});assert.equal(await p.locator('#gn-titulo').inputValue(),'Meu título revisado');
 await p.locator('#gn-usar-titulo-tri7').click();assert.equal(await p.locator('#gn-titulo').inputValue(),'FORMAL DE PARTILHA');
 // Trocar protocolo retira somente o título preenchido automaticamente.
 atrasar=new Promise(r=>liberar=r);const recebida=new Promise(r=>confirmar=r);
 await p.locator('#gn-protocolo').fill('186804');await recebida;
 assert.equal(await p.locator('#gn-titulo').inputValue(),'');
 await p.locator('#gn-protocolo').fill('186805');liberar();atrasar=null;
 await p.waitForFunction(()=>document.getElementById('gn-titulo').value==='FORMAL DE PARTILHA');
 modo='erro';await p.locator('#gn-consultar-protocolo').click();
 await p.waitForFunction(()=>document.getElementById('gn-protocolo-aviso').textContent.includes('indisponível'));
 assert.equal(await p.locator('#gn-titulo').inputValue(),'FORMAL DE PARTILHA');
 modo='vazio';await p.locator('#gn-protocolo').fill('186804');
 await p.waitForFunction(()=>document.getElementById('gn-protocolo-aviso').textContent.includes('não tem descrição'));
 assert.equal(await p.locator('#gn-titulo').inputValue(),'');
 // Logout descarta resposta em trânsito.
 modo='normal';atrasar=new Promise(r=>liberar=r);const recebida2=new Promise(r=>confirmar=r);
 await p.locator('#gn-consultar-protocolo').click();await recebida2;
 await p.evaluate(()=>window.consulta.configurar(false));liberar();atrasar=null;
 await p.waitForTimeout(200);assert.equal(await p.locator('#gn-titulo').inputValue(),'');
 await p.evaluate(()=>window.consulta.configurar(true,'usuario-b'));await p.locator('#gn-consultar-protocolo').click();
 await p.waitForFunction(()=>document.getElementById('gn-titulo').value.includes('ESCRITURA'));
 fs.mkdirSync(path.join(root,'.tmp/nota-protocolo'),{recursive:true});await p.screenshot({path:path.join(root,'.tmp/nota-protocolo/desktop.png'),fullPage:true});
 await p.setViewportSize({width:390,height:844});assert(await p.locator('#gn-consultar-protocolo').isVisible());await p.screenshot({path:path.join(root,'.tmp/nota-protocolo/mobile.png'),fullPage:true});
 assert.deepEqual(erros,[]);console.log('OK: preenchimento automático, preservação manual, troca de protocolo, respostas atrasadas, ausência/erro, CSRF e logout; desktop/mobile.');
}finally{await b.close()}})().catch(e=>{console.error(e);process.exitCode=1});
