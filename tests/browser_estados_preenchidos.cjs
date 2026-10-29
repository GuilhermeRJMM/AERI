// Regressão de consultas preenchidas, filtros selecionados e hover. Rede isolada.
const {chromium}=require('playwright');
const fs=require('fs'),path=require('path'),os=require('os'),assert=require('assert/strict');
const raiz=path.resolve(__dirname,'..'),saida=path.join(os.tmpdir(),'aeri-estados-preenchidos');
function template(nome){return fs.readFileSync(path.join(raiz,'backend/templates',nome),'utf8')
 .replace(/{%\s*include\s+['"]([^'"]+)['"]\s*%}/g,(_,n)=>template(n)).replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi,'');}
function contraste(a,b){const lum=cor=>{const c=cor.slice(0,3).map(n=>n/255).map(n=>n<=.04045?n/12.92:((n+.055)/1.055)**2.4);return c[0]*.2126+c[1]*.7152+c[2]*.0722;};const x=lum(a),y=lum(b);return (Math.max(x,y)+.05)/(Math.min(x,y)+.05);}
async function cores(alvo){return alvo.evaluate(e=>{
 const rgba=s=>s.match(/[\d.]+/g)?.map(Number)||[255,255,255,0];
 let bg=[255,255,255];const pais=[];for(let n=e;n;n=n.parentElement)pais.unshift(n);
 for(const n of pais){const c=rgba(getComputedStyle(n).backgroundColor),a=c[3]??1;bg=bg.map((v,i)=>c[i]*a+v*(1-a));}
 const s=getComputedStyle(e);return {fg:rgba(s.color),bg,background:s.backgroundColor,image:s.backgroundImage,transform:s.transform};
});}
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});fs.mkdirSync(saida,{recursive:true});
 const erros=[],problemas=[];let estados=0;
 try{
 const page=await browser.newPage({viewport:{width:1440,height:1050},reducedMotion:'reduce'});
 page.on('pageerror',e=>erros.push(e.message));
 await page.route('**/*',route=>{
  const u=new URL(route.request().url());if(u.hostname!=='aeri-teste.invalid')return route.abort();
  const json=v=>route.fulfill({contentType:'application/json',body:JSON.stringify(v)});
  if(u.pathname==='/')return route.fulfill({contentType:'text/html; charset=utf-8',body:template('index.html')});
  if(u.pathname==='/api/sessao')return json({csrfToken:'teste'});
  if(u.pathname==='/api/livro-protocolos/analisar-data')return json({fonte:'TRI7',dataEsperada:'2026-10-29',resumo:{total:4,conferidos:2,totalOcorrencias:0,registrados:1,prenotados:1,semEfeito:1,indefinidos:1,comOcorrencias:0,falhasConsulta:0},protocolos:['REGISTRADO','PRENOTADO','SEM_EFEITO','INDEFINIDO'].map((status,i)=>({numero:String(186001+i),numeroFormatado:String(186001+i),nomeApresentante:'Pessoa Exemplo',data:'2026-10-29',status,conferido:true,ocorrencias:[]}))});
  if(u.pathname==='/analisar-incra')return json({protocolos_unicos:3,lancamentos:3,paginas:1,contagens:{COMUNICAR:1,REVISAR:1,FORA_DAS_HIPOTESES:1},itens:['COMUNICAR','REVISAR','FORA_DAS_HIPOTESES'].map((status,i)=>({protocolo:String(186101+i),ato:'Registro de teste',motivo:'Exemplo de teste',status,matriculas:[],ocorrencias:0}))});
  if(u.pathname==='/api/custas')return json([{id:'teste',pedido:'S000000001D',nome:'Pessoa Exemplo',documento:'***.***.333-44',modalidade:'PENHOR',produto:'SOJA',safra:'2026/2027',resultado:'PENDENTE',status:'FAZER_PESQUISA',finalizado:false}]);
  if(u.pathname.startsWith('/api/'))return json([]);
  if(u.pathname.startsWith('/static/')){const p=path.resolve(raiz,'backend','.'+decodeURIComponent(u.pathname));if(!p.startsWith(path.join(raiz,'backend/static')+path.sep)||!fs.existsSync(p))return route.abort();return route.fulfill({contentType:p.endsWith('.css')?'text/css':p.endsWith('.js')?'text/javascript':p.endsWith('.png')?'image/png':'image/svg+xml',body:fs.readFileSync(p)});}
  return route.abort();
 });
 await page.goto('https://aeri-teste.invalid/');
 await page.evaluate(async()=>{
  document.getElementById('splash-aeri').remove();document.body.classList.remove('auth-pending','splash-active');document.body.dataset.perfil='ADMIN';document.getElementById('login-aeri').style.display='none';
  window.paginaTeste=id=>{document.querySelectorAll('.page[id]').forEach(e=>{e.style.display=e.id===id?'block':'none';e.classList.toggle('active',e.id===id);});};
  (await import('/static/js/livro_protocolos.js')).iniciarLivroProtocolos();
  (await import('/static/js/incra.js')).iniciarIncra();
  const custas=await import('/static/js/custas.js');custas.iniciarCustas();await custas.carregarCustas();
  window.paginaTeste('page-livroproto');
 });
 await page.locator('#livroproto-data').fill('2026-10-29');await page.locator('#btn-livroproto-data').click();
 await page.locator('#livroproto-resultado .incra-resumo').waitFor();
 const verificar=async(alvo,nome,cartao=false)=>{const c=await cores(alvo);estados++;if(contraste(c.fg,c.bg)<4.5)problemas.push({nome,contraste:contraste(c.fg,c.bg),...c});if(cartao&&(c.background!=='rgb(255, 255, 255)'||c.image!=='none'))problemas.push({nome,tipo:'cartão não branco',...c});};
 for(const largura of [1440,390]){
  await page.setViewportSize({width:largura,height:1050});
  for(let i=0;i<4;i++){const cartao=page.locator('#livroproto-resultado .incra-resumo > div').nth(i);await cartao.hover();await verificar(cartao,`Livro cartão hover ${i} ${largura}`,true);}
  for(const filtro of ['TODOS','REGISTRADO','PRENOTADO','SEM_EFEITO','INDEFINIDO','OCORRENCIAS','FALHAS']){
   const botao=page.locator(`#livroproto-resultado [data-filtro="${filtro}"]`);await botao.click();await verificar(botao.locator('b'),`Livro filtro ${filtro} ${largura}`);
  }
  await page.locator('#livroproto-resultado [data-filtro="SEM_EFEITO"]').click();await page.locator('#livroproto-resultado .incra-resumo > div').first().hover();
  await page.screenshot({path:path.join(saida,`livro-resultado-hover-${largura}.png`),animations:'disabled'});
 }
 await page.evaluate(()=>window.paginaTeste('page-incra'));
 await page.locator('#incra-pdf').setInputFiles({name:'teste.pdf',mimeType:'application/pdf',buffer:Buffer.from('%PDF teste sintético')});await page.locator('#btn-incra').click();await page.locator('#incra-resultado .incra-resumo').waitFor();
 for(const filtro of ['COMUNICAR','REVISAR','FORA_DAS_HIPOTESES']){const botao=page.locator(`#incra-resultado [data-filtro="${filtro}"]`).first();await botao.click();await verificar(botao.locator('b'),'INCRA filtro '+filtro);}
 for(let i=0;i<4;i++){const c=page.locator('#incra-resultado .incra-resumo > div').nth(i);await c.hover();await verificar(c,'INCRA cartão '+i,true);}
 await page.evaluate(()=>window.paginaTeste('page-custas'));
 for(const seletor of ['.custas-legenda button','.custas-acoes button','.custas-tab']){const n=page.locator('#page-custas '+seletor);for(let i=0;i<await n.count();i++){await n.nth(i).hover();await verificar(n.nth(i),'Custas hover '+seletor+i);}}
 // Mesmas classes compartilhadas usadas por resultados que só existem após consulta.
 await page.evaluate(()=>{const e=document.createElement('section');e.id='estados-catalogo';e.innerHTML=`<div class="rotina-resumo-card"><strong>17</strong><span>Conferidos</span></div><div class="perfis-resumo"><div><strong>3</strong><span>Usuários</span></div></div><article class="card"><h3>Resultado</h3><p>Informação do registro.</p></article><div class="gerador-notas-previa"><span class="falta">Campo pendente</span></div><div class="rotina-in-mais-acoes"><button>Mais ações</button></div>
 <div class="buscas-resumo"><div><strong>40</strong>Resultados</div></div>
 <span class="buscas-prioridade" data-prioridade="P0-CRITICA">Revisão crítica</span>
 <div class="regaux-certidao-resumo"><div><strong>2</strong><span>Registros</span></div></div>
 <div class="contratos-previas"><span class="contratos-previa-selo">Prévia</span></div>
 <div class="contratos-bancada-minuta"><pre class="contratos-previa-rascunho">Rascunho</pre><span class="contratos-previa-selo">Minuta em revisão</span></div>
 <div class="mapa-onr-nativo"><pre class="json">{"matricula":"40001"}</pre></div>
 <div class="contratos-confirmacoes"><p class="ok">Confirmado</p></div>
 <div class="incra-matricula-atos"><strong>40.001</strong><span>R.1</span></div>
 <div class="gerador-notas-item marcado"><strong>Exigência selecionada</strong></div>
 <div class="gerador-notas-norma ativa">Norma selecionada</div>`;document.getElementById('page-custas').append(e);});
 for(const s of ['.rotina-resumo-card','.perfis-resumo > div','.card','.gerador-notas-previa .falta','.rotina-in-mais-acoes button','.buscas-resumo > div','.buscas-prioridade','.regaux-certidao-resumo > div','.contratos-previas .contratos-previa-selo','.contratos-bancada-minuta .contratos-previa-selo','.mapa-onr-nativo pre.json','.contratos-confirmacoes .ok','.incra-matricula-atos','.gerador-notas-item.marcado','.gerador-notas-norma.ativa']){const e=page.locator('#estados-catalogo '+s);await e.hover();await verificar(e,'Catálogo hover '+s,['.rotina-resumo-card','.perfis-resumo > div','.card'].includes(s));}
 fs.writeFileSync(path.join(saida,'resultado.json'),JSON.stringify({estados,problemas,erros},null,2));console.log(JSON.stringify({estados,problemas,erros,saida}));
 assert.deepEqual(erros,[]);assert.deepEqual(problemas,[]);
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
