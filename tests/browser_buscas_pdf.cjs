// Dados sintéticos e arquivos locais; nenhuma conexão de produção.
const {chromium}=require('playwright');
const fs=require('fs'), path=require('path'), assert=require('assert/strict');
const root=path.resolve(__dirname,'..');
(async()=>{
    const browser=await chromium.launch({channel:'chrome',headless:true});
    try {
        const page=await browser.newPage({viewport:{width:1440,height:1000}});
        const erros=[], pedidos=[];
        page.on('pageerror',e=>erros.push(e.message));
        await page.route('**/*',async route=>{
            const url=new URL(route.request().url());
            if(url.hostname!=='aeri-teste.invalid')return route.abort();
            if(url.pathname==='/'){
                let html=fs.readFileSync(path.join(root,'backend/templates/index.html'),'utf8');
                html=html.replace(/\{%\s*include\s+['"]([^'"]+)['"]\s*%\}/g,(_,n)=>fs.readFileSync(path.join(root,'backend/templates',n),'utf8'));
                html=html.replace(/<script type="module" src="\/static\/js\/app.js[^\"]*"><\/script>/,
                    `<script type="module">import {iniciarBuscas} from '/static/js/buscas.js';
                    document.getElementById('splash-aeri').remove();document.body.classList.remove('splash-active','auth-pending');
                    document.body.dataset.perfil='ADMIN';document.getElementById('login-aeri').style.display='none';
                    document.querySelectorAll('.page').forEach(p=>p.style.display='none');document.getElementById('page-buscas').style.display='block';iniciarBuscas();</script>`);
                return route.fulfill({contentType:'text/html; charset=utf-8',body:html});
            }
            if(url.pathname.startsWith('/api/')){
                pedidos.push(url);
                if(url.pathname==='/api/buscas/exportar-pdf')return route.fulfill({contentType:'application/pdf',body:Buffer.from('%PDF-1.7\n%arquivo sintetico de teste\n')});
                return route.fulfill({contentType:'application/json',body:JSON.stringify({
                    total:101,totalPaginas:3,pagina:1,porPagina:50,itens:[{matricula:12000,nome:'Pessoa Exemplo',documento:'***.123.456-**',situacao:'ATIVA',revisaoPendente:true,consultadoEm:'2026-10-26T10:00:00Z'}],candidatos:[],cobertura:{negativa_segura:false},
                })});
            }
            if(url.pathname.startsWith('/static/')){
                const arquivo=path.resolve(root,'backend','.'+decodeURIComponent(url.pathname));
                if(!arquivo.startsWith(path.join(root,'backend/static')+path.sep)||!fs.existsSync(arquivo))return route.abort();
                return route.fulfill({contentType:arquivo.endsWith('.js')?'text/javascript':arquivo.endsWith('.css')?'text/css':'image/svg+xml',body:fs.readFileSync(arquivo)});
            }
            return route.abort();
        });
        await page.goto('https://aeri-teste.invalid/');
        assert(await page.locator('#btn-buscas-pdf').isHidden());
        await page.locator('#buscas-termo').fill('Pessoa Exemplo');
        await page.locator('#buscas-incluir-encerradas').check();
        await page.locator('#btn-buscas-pesquisar').click();
        await page.locator('#btn-buscas-pdf').waitFor({state:'visible'});
        assert((await page.locator('#buscas-resultados').textContent()).includes('12.000'));
        const [download]=await Promise.all([page.waitForEvent('download'),page.locator('#btn-buscas-pdf').click()]);
        assert.equal(download.suggestedFilename(),'resultado-buscas.pdf');
        const pedido=pedidos.find(p=>p.pathname==='/api/buscas/exportar-pdf');
        assert.equal(pedido.searchParams.get('nome'),'Pessoa Exemplo');
        assert.equal(pedido.searchParams.get('somente_ativos'),'false');
        assert(!pedido.searchParams.has('pagina'));
        assert(!pedido.searchParams.has('limite'));
        assert(!pedidos.some(p=>p.pathname.includes('preparar-texto')),'Não exige conferência');
        await page.locator('#buscas-texto-aviso').getByText('PDF exportado',{exact:false}).waitFor();
        await page.screenshot({path:path.join(require('os').tmpdir(),'aeri-buscas-pdf-interface.png'),fullPage:true});
        assert.deepEqual(erros,[]);
        console.log('OK: Exportar PDF visível após busca; baixa direto sem conferir, preserva filtros e exporta todas as páginas.');
    } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
