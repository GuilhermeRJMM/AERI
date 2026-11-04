// Validação local da identidade; dados fictícios e nenhuma conexão externa.
const {chromium} = require('playwright');
const fs = require('fs'), path = require('path'), assert = require('assert/strict');
const root = path.resolve(__dirname, '..');
(async () => {
 const browser = await chromium.launch({channel:'chrome', headless:true});
 try {
  const page = await browser.newPage({viewport:{width:1440,height:1000}}), erros=[];
  page.on('pageerror', e => erros.push(e.message));
  await page.route('**/*', route => {
   const u=new URL(route.request().url());
   if(u.hostname!=='marca-teste.invalid') return route.abort();
   if(u.pathname==='/') {
    let html=fs.readFileSync(path.join(root,'backend/templates/index.html'),'utf8');
    html=html.replace(/\{%\s*include\s+['"]([^'"]+)['"]\s*%\}/g,(_,nome)=>fs.readFileSync(path.join(root,'backend/templates',nome),'utf8'));
    html=html.replace(/<script type="module" src="\/static\/js\/app.js[^\"]*"><\/script>/,`<script type="module">
     import {iniciarAutenticacao} from '/static/js/autenticacao.js';
     import {iniciarNavegacao,mostrarPagina} from '/static/js/navegacao.js';
     document.getElementById('splash-aeri').remove();document.body.classList.remove('splash-active');
     window.mostrarPaginaTeste=mostrarPagina;iniciarNavegacao();iniciarAutenticacao();</script>`);
    return route.fulfill({contentType:'text/html',body:html});
   }
   if(u.pathname==='/api/sessao') return route.fulfill({status:401,contentType:'application/json',body:'{"detail":"Entre novamente."}'});
   if(u.pathname.startsWith('/static/')) {
    const f=path.resolve(root,'backend','.'+u.pathname);
    if(!f.startsWith(path.join(root,'backend/static')+path.sep)||!fs.existsSync(f)) return route.abort();
    const mime=f.endsWith('.css')?'text/css':f.endsWith('.png')?'image/png':f.endsWith('.svg')?'image/svg+xml':'text/javascript';
    return route.fulfill({contentType:mime,body:fs.readFileSync(f)});
   }
   return route.abort();
  });
  await page.goto('https://marca-teste.invalid/');
  await page.locator('#form-login').waitFor({state:'visible'});
  assert.equal(await page.title(),'Analisador RGI');
  assert.match(await page.locator('#login-titulo').innerText(),/Analisador RGI/);
  assert(!/\bAERI\b/i.test(await page.locator('body').innerText()));
  assert(await page.locator('.login-logo').evaluate(i=>i.complete&&i.naturalWidth>0));
  assert((await page.locator('link[rel="icon"]').getAttribute('href')).includes('analisador-rgi-logo.png'));
  const pasta=path.join(root,'.tmp/marca-rgi');fs.mkdirSync(pasta,{recursive:true});
  await page.waitForFunction(()=>getComputedStyle(document.getElementById('login-aeri')).opacity==='1');
  await page.screenshot({path:path.join(pasta,'login.png')});
  await page.evaluate(()=>{
   document.body.classList.remove('auth-pending');document.getElementById('login-aeri').classList.remove('aberto');
   document.querySelectorAll('.nav-item').forEach(e=>{e.hidden=false;e.dataset.autorizado='true'});
   window.mostrarPaginaTeste('inicio');
  });
  await page.locator('#login-aeri').waitFor({state:'hidden'});
  assert.equal(await page.locator('.logo-text').innerText(),'Analisador RGI');
  assert(await page.locator('.marca-rgi-icone').evaluate(i=>i.complete&&i.naturalWidth>0));
  assert(!/\bAERI\b/i.test(await page.locator('body').innerText()));
  await page.screenshot({path:path.join(pasta,'inicio.png')});
  for(const largura of [390,768]){
   await page.setViewportSize({width:largura,height:900});
   const r=await page.locator('.logo-text').boundingBox();assert(r.x>=0&&r.x+r.width<=largura);
   await page.screenshot({path:path.join(pasta,`inicio-${largura}.png`)});
  }
  assert.deepEqual(erros,[]);
  console.log('OK: logo fornecida carregada, login, título, favicon, navegação e marca responsiva; sem AERI visível.');
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
