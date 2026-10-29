// Confere interfaces protegidas usando somente arquivos locais, sem autenticar.
const {chromium}=require('playwright');
const fs=require('fs'),path=require('path'),os=require('os'),assert=require('assert/strict');
const raiz=path.resolve(__dirname,'..');
const arquivos={mapa:'mapa_onr.html',notas:'gerador_notas/index.html',legislacao:'gerador_notas/legislacao.html',revisao:'gerador_notas/revisar.html'};
(async()=>{
    const browser=await chromium.launch({channel:'chrome',headless:true});
    const saida=path.join(os.tmpdir(),'aeri-interfaces-20261029');fs.mkdirSync(saida,{recursive:true});
    let casos=0;
    try{
        const page=await browser.newPage({reducedMotion:'reduce'});
        const erros=[];page.on('pageerror',e=>erros.push(e.message));
        await page.route('**/*',route=>{
            const u=new URL(route.request().url());
            if(u.hostname!=='aeri-teste.invalid')return route.abort();
            if(u.pathname.startsWith('/__interfaces/')){
                const nome=arquivos[u.pathname.split('/').at(-1)];if(!nome)return route.abort();
                const html=fs.readFileSync(path.join(raiz,'backend/private',nome),'utf8').replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi,'');
                return route.fulfill({contentType:'text/html; charset=utf-8',body:html});
            }
            if(u.pathname.startsWith('/static/')){
                const arquivo=path.resolve(raiz,'backend','.'+decodeURIComponent(u.pathname));
                if(!arquivo.startsWith(path.join(raiz,'backend/static')+path.sep)||!fs.existsSync(arquivo))return route.abort();
                return route.fulfill({contentType:'text/css',body:fs.readFileSync(arquivo)});
            }
            return route.abort();
        });
        for(const cor of ['light','dark']){
            await page.emulateMedia({colorScheme:cor,reducedMotion:'reduce'});
            for(const largura of [1440,390]){
                await page.setViewportSize({width:largura,height:1050});
                for(const nome of Object.keys(arquivos)){
                    await page.goto('https://aeri-teste.invalid/__interfaces/'+nome);
                    for(const embedded of nome==='mapa'?[false,true]:[false]){
                        await page.evaluate(valor=>document.body.classList.toggle('aeri-embedded',valor),embedded);
                        const estilo=await page.evaluate(()=>({cor:getComputedStyle(document.body).backgroundColor,
                            scheme:getComputedStyle(document.documentElement).colorScheme,
                            overflow:document.documentElement.scrollWidth>innerWidth+2}));
                        assert(['rgb(255, 255, 255)','rgb(248, 250, 252)'].includes(estilo.cor),JSON.stringify({nome,cor,embedded,estilo}));
                        assert.equal(estilo.scheme,'light');assert(!estilo.overflow,nome+' sem rolagem lateral');
                        if(cor==='dark')await page.screenshot({path:path.join(saida,`${nome}-${largura}${embedded?'-embedded':''}.png`)});
                        casos++;
                    }
                }
            }
        }
        assert.deepEqual(erros,[]);
        console.log(`OK: ${casos} combinações; MAPA-ONR isolado/embutido, Notas, Legislação e Revisão, preferências clara/escura, desktop e mobile. Capturas: ${saida}`);
    }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
