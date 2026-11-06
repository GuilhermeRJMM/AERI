// Navegador real, motor Python real, dados fictícios. Sem acesso a produção.
const {chromium}=require('playwright');
const {spawnSync}=require('child_process');
const fs=require('fs'),path=require('path'),assert=require('assert/strict');
const root=path.resolve(__dirname,'..');
const python=process.env.AERI_PYTHON;
if(!python)throw Error('Informe AERI_PYTHON para executar o motor local.');
function motor(acao,dados={}){
 const script=`import json,sys,base64\nfrom backend.app.gerador_notas.servico import catalogo_para_tela,previa,gerar_documento_com_resumo\nd=json.load(sys.stdin)\nif sys.argv[1]=='catalogo': r=catalogo_para_tela()\nelif sys.argv[1]=='previa': r=previa(d)\nelse:\n n,b,a,s=gerar_documento_com_resumo(d); r={'arquivo':n,'conteudo':base64.b64encode(b).decode(),'nao_revisadas':a,'resumo':s,'resumo_incluido':True}\nprint(json.dumps(r,ensure_ascii=False))`;
 const r=spawnSync(python,['-B','-X','utf8','-c',script,acao],{cwd:root,input:JSON.stringify(dados),encoding:'utf8'});
 if(r.status!==0)throw Error(r.stderr);return JSON.parse(r.stdout);
}
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1080}}),erros=[];
  page.on('pageerror',e=>erros.push(e.message));
  let semResumo=false,gerados=0;
  await page.route('**/*',async route=>{
   const u=new URL(route.request().url());if(u.hostname!=='nota-teste.invalid')return route.abort();
   if(u.pathname==='/'){
    let html=fs.readFileSync(path.join(root,'backend/templates/index.html'),'utf8').replace(/\{%\s*include\s+['"]([^'"]+)['"]\s*%\}/g,(_,nome)=>fs.readFileSync(path.join(root,'backend/templates',nome),'utf8'));
    html=html.replace(/<script type="module" src="\/static\/js\/app.js[^\"]*"><\/script>/,`<script type="module">
     import {iniciarGeradorNotas,configurarAcessoGeradorNotas} from '/static/js/gerador_notas.js';
     import {definirCsrfToken} from '/static/js/api.js?v=20260902-arquivo-v1';
     definirCsrfToken('csrf-ficticio-do-teste');
     document.getElementById('splash-aeri').remove();document.body.classList.remove('splash-active','auth-pending');
     document.querySelectorAll('.page').forEach(p=>p.classList.remove('active'));
     document.getElementById('page-geradornotas').classList.add('active');
     document.querySelectorAll('.nav-item').forEach(n=>n.classList.toggle('active',n.dataset.page==='geradornotas'));
     iniciarGeradorNotas();configurarAcessoGeradorNotas(true);</script>`);
    return route.fulfill({contentType:'text/html',body:html});
   }
   if(u.pathname.startsWith('/api/gerador-notas/')){
    const acao=u.pathname.split('/').at(-1);
    if(acao==='consultar-protocolo')return route.fulfill({contentType:'application/json',body:JSON.stringify({protocolo:route.request().postDataJSON().protocolo.replace(/\./g,''),titulo:''})});
    const dados=route.request().postDataJSON()||{};
    const r=motor(acao,dados);if(acao==='gerar'){gerados++;if(semResumo)delete r.resumo_incluido;}
    return route.fulfill({contentType:'application/json',body:JSON.stringify(r)});
   }
   if(u.pathname.startsWith('/static/')){
    const f=path.resolve(root,'backend','.'+u.pathname);
    if(!f.startsWith(path.join(root,'backend/static')+path.sep)||!fs.existsSync(f))return route.abort();
    return route.fulfill({contentType:f.endsWith('.css')?'text/css':f.endsWith('.png')?'image/png':'text/javascript',body:fs.readFileSync(f)});
   }
   return route.abort();
  });
  await page.goto('https://nota-teste.invalid/');
  await page.locator('#gn-editor').waitFor({state:'visible'});
  assert.equal(await page.locator('[data-gn-exigencia]').count(),72);
  await page.locator('#gn-titulo').fill('Escritura pública de compra e venda');
  await page.locator('#gn-protocolo').fill('186.999');
  await page.locator('[data-gn-exigencia="area-divergente-itcd"]').check();
  await page.locator('[data-gn-campo="area_documento"]').fill('100,00 ha');
  await page.locator('[data-gn-campo="area_matricula"]').fill('90,00 ha');
  await page.waitForFunction(()=>document.querySelector('.nota-resumo')?.textContent.includes('100,00 ha'));
  assert.match(await page.locator('.nota-resumo').innerText(),/186\.999/);
  await page.locator('[data-gn-campo="area_documento"]').fill('105,00 ha');
  await page.waitForFunction(()=>document.querySelector('.nota-resumo')?.textContent.includes('105,00 ha'));
  assert.match(await page.locator('#gn-previa').innerText(),/Demonstrativo de Cálculo/);
  assert.equal(await page.locator('[data-resumo-numero="1"]').count(),1);
  const download=page.waitForEvent('download');await page.locator('#gn-gerar').click();
  assert((await download).suggestedFilename().endsWith('.docx'));
  await page.locator('#gn-modal-titulo').filter({hasText:'Nota e resumo gerados'}).waitFor();
  await page.locator('#gn-modal-ok').click();
  // Resposta antiga/incompleta nunca é baixada como nota sem resumo.
  semResumo=true;let extras=0;page.on('download',()=>extras++);
  await page.locator('#gn-gerar').click();
  await page.waitForFunction(()=>document.getElementById('gn-modal-corpo').textContent.includes('nenhum arquivo foi baixado'));
  assert.equal(extras,0);assert.equal(gerados,2);await page.locator('#gn-modal-ok').click();
  await page.locator('#gn-previa').evaluate(e=>e.scrollTop=e.scrollHeight);
  fs.mkdirSync(path.join(root,'.tmp/nota-resumo'),{recursive:true});
  await page.screenshot({path:path.join(root,'.tmp/nota-resumo/previa-navegador.png'),fullPage:true});
  assert.equal(await page.locator('.nota-resumo').evaluate(e=>getComputedStyle(e).backgroundColor),'rgb(255, 255, 255)');
  await page.setViewportSize({width:390,height:900});
  assert(await page.locator('#gn-gerar').isVisible());
  assert.deepEqual(erros,[]);
  console.log('OK: 72 itens, prévia formal e simples sincronizadas, download conjunto e bloqueio de resposta sem resumo; tema branco e mobile.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
