// QA de impressão em memória, com dados sintéticos e sem acesso à produção.
const {chromium}=require('playwright');
const {spawnSync}=require('child_process');
const {pathToFileURL}=require('url');const path=require('path');const fs=require('fs');const assert=require('assert/strict');
(async()=>{
 const root=path.resolve(__dirname,'..');
 const {gerarOficio}=await import(pathToFileURL(path.join(root,'backend/static/js/intimacao_modelos.js')).href);
 const d={in:'IN00000001C',processo:'100100/2026',dataGeracao:'30/10/2026',dataProtocolo:'23/10/2026',oficio:'INT/2026/053',protocolo:'123456',matricula:'1.234',registro:'R.06',titulo:'Contrato de Venda e Compra de Imóvel, Mútuo e Alienação Fiduciária em Garantia - Carta de Crédito Individual - CCFGTS - Programa Minha, Casa Minha Vida Com Utilização dos Recursos da Conta Vinculada do FGTS do Devedor',contrato:'1.2344.1234567-0',dataContrato:'16/11/2023',credor:'CREDOR EXEMPLO',cnpj:'00.360.305/0001-04',alvo:{nome:'PESSOA EXEMPLO',cpf:'11144477735'},enderecoImovel:'Lote comercial n.º 02, Quadra 01, situado na Avenida Perimetral, Jardim Vera Cruz, Morrinhos-GO, CEP: 75.656-485',enderecos:['Avenida Perimetral, 336, Quadra 01, Lote 02, Jardim Vera Cruz, Morrinhos-GO, CEP: 75.656-485','Fazenda Exemplo, zona rural, Município de Morrinhos, CEP: ________','Rua Fora, 10, Goiânia-GO'],dataProjecao:'30/10/2026',valorProjecao:'R$ 10.545,44',valorExtenso:'dez mil quinhentos e quarenta e cinco reais e quarenta e quatro centavos',selo:'00000000000000000000000',clausula:'26 OUTORGA DE PROCURAÇÕES'};
 if(process.env.AERI_DADOS_STDIN)Object.assign(d,JSON.parse(fs.readFileSync(0,'utf8')));
 const browser=await chromium.launch({channel:'chrome',headless:true});
 try{
  const page=await browser.newPage();
  await page.setContent('<!doctype html><meta charset="utf-8"><style>@page{size:A4;margin:52mm 22.5mm 20mm}body{margin:0}</style>'+gerarOficio(d));
  const alturas=await page.locator('section').evaluateAll(es=>es.map(e=>e.getBoundingClientRect().height*25.4/96));
  console.log('Alturas das três páginas (mm):',alturas);
  const pdf=await page.pdf({preferCSSPageSize:true,printBackground:true});
  const out=path.join(root,'.tmp/documentos-intimacao/paginacao');fs.mkdirSync(out,{recursive:true});
  const r=spawnSync(process.env.AERI_PYTHON||'python',['-c',`import pymupdf,sys,json\nd=pymupdf.open(stream=sys.stdin.buffer.read(),filetype='pdf')\nif sys.argv[2]=='render':\n for i,p in enumerate(d):p.get_pixmap(matrix=pymupdf.Matrix(1,1)).save(sys.argv[1]+'/pagina-'+str(i+1)+'.png')\nprint(json.dumps([p.get_text() for p in d]))`,out,process.env.AERI_DADOS_STDIN?'memoria':'render'],{input:pdf,maxBuffer:2000000});
  if(r.status!==0)throw Error(r.stderr.toString());
  const ps=JSON.parse(r.stdout.toString());assert.equal(ps.length,3,'O Ofício deve imprimir exatamente três páginas A4.');
  assert(ps[0].includes('Luiz Fernando Ribeiro') && !ps[0].includes('CONTRA-FÉ'));
  assert(ps[0].trim().endsWith('Luiz Fernando Ribeiro - Escrevente'));
  assert(ps[1].includes('CONTRA-FÉ') && ps[1].includes('CERTIDÃO'));
  assert(ps[1].includes('3ª tentativa:') && !ps[2].includes('3ª tentativa:'));
  if(!process.env.AERI_DADOS_STDIN)assert(ps[2].includes('Fazenda Exemplo') && !ps.join('').includes('Goiânia'));
  assert(ps[2].indexOf('Endereços para')<ps[2].indexOf('OBSERVAÇÕES'));
  console.log('Impressão: 3 páginas; assinatura encerra a primeira; Certidão completa na segunda; endereços locais antes das Observações na terceira.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
