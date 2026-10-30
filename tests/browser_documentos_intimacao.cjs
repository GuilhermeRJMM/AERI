// Fluxo inteiro com dados sintéticos e todas as chamadas interceptadas.
const {chromium}=require('playwright');
const fs=require('fs');const path=require('path');const assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..');
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1100}});
  page.setDefaultTimeout(15000);
  const eventos=[],copias=[],erros=[];let demora=false,liberar;
  const item={id:'00000000-0000-0000-0000-000000000001',protocolo:'IN00000001C'};
  const dados={fluxo:'tres-anexos-20261030',protocoloIN:item.protocolo,protocoloTri7:'123456',dataProtocolo:'23/10/2026',
   processoCredor:'100100/2026',matricula:'1234',contrato:{numero:'123456789012',data:'16/11/2023'},
   credor:{nome:'BANCO EXEMPLO',cnpj:'00360305000104'},devedores:[{nome:'PESSOA EXEMPLO',cpf:'11144477735'}],
   enderecoImovel:'Rua A, 1, Centro, Morrinhos-GO',enderecos:['Rua B, 2, Centro, Morrinhos-GO, CEP: 75650082'],
   projecao:{data:'30/10/2026',valor:'10545.44',extenso:'dez mil quinhentos e quarenta e cinco reais e quarenta e quatro centavos'},
   fontes:['recibo','oficio','projecao'].map((p,i)=>({papel:p,nome:p+'.pdf',sha256:String(i+1).repeat(64),ocr:false})),
   inconsistencias:[],avisos:['Confira as datas e a cláusula.'],origens:{protocolo:{recibo:'123456'}}};
  await page.addInitScript(()=>{
   window.copiasTeste=[];
   Object.defineProperty(navigator,'clipboard',{value:{
    write:async itens=>{const h=await itens[0].getType('text/html');window.copiasTeste.push(await h.text());},
    writeText:async t=>window.copiasTeste.push(t)
   }});
  });
  page.on('pageerror',e=>erros.push(e.message));
  await page.route('**/*',async route=>{
   const u=new URL(route.request().url());const json=(d,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(d)});
   if(u.pathname==='/'){
    const parcial=fs.readFileSync(path.join(root,'backend/templates/intimacao_documentos.html'),'utf8');
    return route.fulfill({contentType:'text/html',body:`<!doctype html><html lang="pt-br"><head><meta charset="utf-8"><link rel="stylesheet" href="/static/tokens.css"><link rel="stylesheet" href="/static/styles.css"><link rel="stylesheet" href="/static/sync-theme.css"><link rel="stylesheet" href="/static/design-system.css"><link rel="stylesheet" href="/static/intimacao-documentos.css"></head><body class="sync-tema">${parcial}<script type="module">import {iniciarDocumentosIntimacao,abrirDocumentosIntimacao} from '/static/js/intimacao_documentos.js';iniciarDocumentosIntimacao();window.abrirTeste=()=>abrirDocumentosIntimacao(${JSON.stringify(item)});abrirTeste();</script></body></html>`});
   }
   if(u.pathname==='/api/sessao')return json({csrfToken:'csrf-sintetico'});
   if(u.pathname.endsWith('/preparar-documentos')){
    if(demora)await new Promise(r=>liberar=r);
    return json(dados);
   }
   if(u.pathname.endsWith('/documentos-evento')){eventos.push(route.request().postDataJSON());return json({registrado:true,numeroReservado:false});}
   if(u.pathname.endsWith('/preparar-documentos-rede'))return json({id:'trabalho-teste',estado:'PENDENTE'});
   if(u.pathname.endsWith('/trabalho-teste')){
    if(route.request().method()==='DELETE')return route.fulfill({status:204});
    return json({estado:'PRONTO',dados:{fluxo:'tres-anexos-20261030',arquivos:['recibo','oficio','projecao'].map((p,i)=>({id:String(i+1).repeat(64),nome:p+'.pdf',tamanho:100,sugerido:p}))}});
   }
   if(u.pathname.startsWith('/api/'))throw Error('Endpoint inesperado: '+u.pathname);
   if(u.pathname.startsWith('/static/')){
    const f=path.resolve(root,'backend','.'+u.pathname);if(!f.startsWith(path.join(root,'backend/static')+path.sep))return route.abort();
    if(!fs.existsSync(f))return route.abort();return route.fulfill({contentType:f.endsWith('.css')?'text/css':'text/javascript',body:fs.readFileSync(f)});
   }
   return route.abort();
  });
  await page.goto('https://aeri-documentos-teste.invalid/');
  const modal=page.locator('#modal-documentos-intimacao');await modal.waitFor({state:'visible'});
  await page.locator('#btn-analisar-documentos-intimacao').hover();
  assert.equal(await page.locator('#btn-analisar-documentos-intimacao').evaluate(e=>getComputedStyle(e).color),'rgb(255, 255, 255)');
  await page.locator('#doc-int-data-geracao').fill('2026-10-30');
  await page.locator('#doc-int-ultimo-oficio').fill('52');assert.equal(await page.locator('#doc-int-numero-oficio').inputValue(),'INT/2026/053');
  await page.locator('#documentos-intimacao-confirmar-origem').check();await page.locator('#btn-analisar-documentos-intimacao').click();
  await page.getByText('Anexe o Recibo do Protocolo, o Ofício do Credor e a Planilha de Projeção.',{exact:true}).waitFor();
  async function anexar(){for(const p of ['recibo','oficio','projecao'])await page.locator('#documentos-intimacao-'+p).setInputFiles({name:p+'.pdf',mimeType:'application/pdf',buffer:Buffer.from('%PDF teste '+p)});await page.locator('#documentos-intimacao-confirmar-origem').check();}
  await anexar();await page.locator('#btn-analisar-documentos-intimacao').click();await page.locator('#documentos-intimacao-editor').waitFor({state:'visible'});
  const faltantes={'titulo':'Título literal n.°','registro-garantia':'R.6','data-titulo':'19/10/2026',signatario:'Escrevente Exemplo',selo:'00000000000000000000000',clausula:'26 OUTORGA DE PROCURAÇÕES'};
  for(const [id,v] of Object.entries(faltantes))await page.locator('#doc-int-'+id).fill(v);
  await page.locator('#doc-int-modelo-conferido').check();await page.locator('#doc-int-divergencias-conferidas').check();
  await page.locator('#btn-gerar-tres-documentos').click();await page.locator('#doc-int-texto-autuacao').waitFor({state:'visible'});
  assert(await page.locator('[data-copiar-documento="autuacao"]').isDisabled());
  await page.locator('[data-aprovar-documento="autuacao"]').check();await page.locator('[data-copiar-documento="autuacao"]').waitFor({state:'visible'});
  await page.waitForFunction(()=>!document.querySelector('[data-copiar-documento="autuacao"]').disabled);
  await page.locator('[data-copiar-documento="autuacao"]').click();await page.waitForFunction(()=>window.copiasTeste.length===1);
  const html=await page.evaluate(()=>window.copiasTeste[0]);assert(html.includes('font-family: Arial') || html.includes('font-family:Arial'));
  assert(html.includes('19/10/2026'));assert.equal(eventos[0].acao,'revisao');
  await page.locator('#doc-int-texto-autuacao').press('End');await page.locator('#doc-int-texto-autuacao').press('Space');
  assert(await page.locator('[data-copiar-documento="autuacao"]').isDisabled());
  // Selecionar texto e soltar no fundo não fecha o modal.
  await modal.dispatchEvent('click');assert(await modal.isVisible());
  for(const tipo of ['oficio','convocacao']){
   await page.locator('[data-aba-documento="'+tipo+'"]').click();
   assert(await page.locator('[data-copiar-documento="'+tipo+'"]').isDisabled());
   await page.locator('[data-aprovar-documento="'+tipo+'"]').check();
   await page.waitForFunction(t=>!document.querySelector('[data-copiar-documento="'+t+'"]').disabled,tipo);
   await page.locator('[data-copiar-documento="'+tipo+'"]').click();
  }
  await page.waitForFunction(()=>window.copiasTeste.length===3);
  fs.mkdirSync(path.join(root,'.tmp/documentos-intimacao'),{recursive:true});
  await page.locator('[data-aba-documento="autuacao"]').click();
  await modal.screenshot({path:path.join(root,'.tmp/documentos-intimacao/revisao-desktop.png')});
  const fundo=await modal.locator('.modal-box').evaluate(e=>getComputedStyle(e).backgroundColor);assert.equal(fundo,'rgb(255, 255, 255)');
  await page.locator('#doc-int-contrato').fill('CONTRATO ALTERADO');assert(await page.locator('#documentos-intimacao-previa').isHidden());
  // Resposta atrasada de outro contexto não pode reabrir uma prévia.
  demora=true;await anexar();await page.locator('#btn-analisar-documentos-intimacao').click();await page.waitForTimeout(100);
  await page.locator('#btn-fechar-documentos-intimacao').click();await page.evaluate(()=>window.abrirTeste());
  if(liberar)liberar();await page.waitForTimeout(200);assert(await page.locator('#documentos-intimacao-editor').isHidden());
  demora=false;await page.locator('#btn-ler-documentos-intimacao-rede').click();
  await page.locator('[data-anexo-rede="recibo"]').waitFor({state:'visible'});
  assert.equal(await page.locator('[data-anexo-rede="recibo"]').inputValue(),'1'.repeat(64));
  assert(!await page.locator('#documentos-intimacao-arquivos-rede').innerText().then(t=>t.includes('T:\\')));
  dados.inconsistencias=[{campo:'protocoloTri7',fontes:{recibo:'123456',cadastroAeri:'99999'}}];
  await page.locator('#doc-int-ultimo-oficio').fill('52');
  await anexar();await page.locator('#btn-analisar-documentos-intimacao').click();await page.locator('#documentos-intimacao-editor').waitFor({state:'visible'});
  for(const [id,v] of Object.entries(faltantes))await page.locator('#doc-int-'+id).fill(v);
  await page.locator('#doc-int-modelo-conferido').check();await page.locator('#doc-int-divergencias-conferidas').check();
  await page.locator('#btn-gerar-tres-documentos').click();
  assert(await page.locator('#documentos-intimacao-previa').isHidden());
  await page.getByText('Confirme expressamente o protocolo do recibo antes de preparar os textos; ele difere do cadastro antigo.',{exact:true}).waitFor();
  await page.locator('#doc-int-protocolo-conferido').check();await page.locator('#btn-gerar-tres-documentos').click();
  await page.locator('#doc-int-texto-autuacao').waitFor({state:'visible'});
  await page.setViewportSize({width:390,height:844});await modal.screenshot({path:path.join(root,'.tmp/documentos-intimacao/anexos-mobile.png')});
  assert.deepEqual(erros,[]);
  assert(eventos.every(e=>e.fontes.length===3 && /^[a-f0-9]{64}$/.test(e.rascunhoHash) && !('texto' in e)));
  console.log('Bancada: anexos obrigatórios, numeração, revisão individual, cópia HTML, invalidação, resposta atrasada, seletor da rede e tema branco OK.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
