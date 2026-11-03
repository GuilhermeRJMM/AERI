// Somente dados fictícios; rede externa bloqueada.
const {chromium}=require('playwright');const fs=require('fs'),path=require('path'),assert=require('assert/strict');
const root=path.resolve(__dirname,'..');
(async()=>{const browser=await chromium.launch({channel:'chrome',headless:true});try{
 const page=await browser.newPage({viewport:{width:1440,height:1000}}),erros=[];
 page.on('pageerror',e=>erros.push(e.message));
 await page.route('**/*',route=>{
  const u=new URL(route.request().url());if(u.hostname!=='mapa-teste.invalid')return route.abort();
  if(u.pathname==='/'){const html=fs.readFileSync(path.join(root,'backend/private/mapa_onr.html'),'utf8').replace(/src="(src|schemas)\//g,'src="/static/mapa_onr/$1/');return route.fulfill({contentType:'text/html',body:html});}
  if(u.pathname.startsWith('/static/')){const f=path.resolve(root,'backend','.'+u.pathname);if(!f.startsWith(path.join(root,'backend/static')+path.sep)||!fs.existsSync(f))return route.abort();return route.fulfill({contentType:f.endsWith('.css')?'text/css':'text/javascript',body:fs.readFileSync(f)});}
  return route.abort();
 });
 await page.goto('https://mapa-teste.invalid/');
 await page.locator('#texto').fill('R.01-1234 - Morrinhos, 01 de janeiro de 2020. Devedor: Carlos Teste da Silva, CPF nº 111.444.777-35, brasileiro, casado sob o regime da comunhão universal de bens. Credor: BANCO EXEMPLO.\n----------------------------------------------------------------------------\nR.20-1234 - Morrinhos, 12 de agosto de 2021. Devedor: Carlos Teste da Silva, já qualificado. Credor: BANCO EXEMPLO.\n----------------------------------------------------------------------------\nAV.21-1234 - Morrinhos, 13 de agosto de 2021. Em cumprimento ao mandado judicial, procede-se à averbação.');
 await page.locator('#btn-ler').click();
 const primeiro=page.getByLabel('Decisão Judicial do R.01',{exact:true});
 const segundo=page.getByLabel('Decisão Judicial do R.20',{exact:true});
 const automatico=page.getByLabel('Decisão Judicial do AV.21',{exact:true});
 assert.equal(await automatico.inputValue(),'true');
 assert.match(await automatico.locator('xpath=ancestor::details').innerText(),/SIM — base judicial identificada no texto deste ato/);
 await automatico.selectOption('false');
 assert.equal(await primeiro.inputValue(),'');assert.equal(await segundo.inputValue(),'');
 assert.match(await segundo.locator('xpath=..').innerText(),/NÃO COMPROVADO — este ato não declara/);
 assert.equal(await segundo.locator('option:checked').textContent(),'Não declarado no ato');
 await primeiro.selectOption('true');assert.equal(await primeiro.inputValue(),'true');assert.equal(await segundo.inputValue(),'');
 await segundo.selectOption('false');assert.equal(await primeiro.inputValue(),'true');assert.equal(await segundo.inputValue(),'false');
 assert.equal(await automatico.inputValue(),'false','correção manual não é sobrescrita ao renderizar');
 const ficha=segundo.locator('xpath=ancestor::details');
 assert.match(await ficha.innerText(),/qualificação do ato R\.01/);
 const regimes=await ficha.locator('table select').evaluateAll(ss=>ss.filter(s=>s.innerText.includes('Comunhao universal')||s.innerText.toLowerCase().includes('comunh')).map(s=>s.value));
 assert(regimes.includes('2'));
 fs.mkdirSync(path.join(root,'.tmp/mapa-onr'),{recursive:true});await ficha.screenshot({path:path.join(root,'.tmp/mapa-onr/qualificacao-decisao.png')});
 assert.deepEqual(erros,[]);console.log('MAPA-ONR: decisão por ato preservada após render; qualificação anterior preenchida; sem chamadas externas.');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1;});
