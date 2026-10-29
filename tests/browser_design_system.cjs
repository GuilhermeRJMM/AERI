// Componentes reais e dados sintéticos. Não inicia o backend nem acessa produção.
const {chromium}=require('playwright');
const fs=require('fs');
const path=require('path');
const os=require('os');
const assert=require('assert/strict');
const root=path.resolve(__dirname,'..');
function contraste(a,b) {
    const lum=cor=>{
        const rgb=cor.match(/[\d.]+/g).slice(0,3).map(n=>Number(n)/255)
            .map(n=>n<=.04045?n/12.92:((n+.055)/1.055)**2.4);
        return rgb[0]*.2126+rgb[1]*.7152+rgb[2]*.0722;
    };
    const x=lum(a),y=lum(b); return (Math.max(x,y)+.05)/(Math.min(x,y)+.05);
}
(async()=>{
    const browser=await chromium.launch({channel:'chrome',headless:true});
    const saida=path.join(os.tmpdir(),'aeri-design-system-20261029');
    fs.mkdirSync(saida,{recursive:true});
    try {
        const page=await browser.newPage({viewport:{width:1440,height:1080}});
        const erros=[];
        page.on('pageerror',e=>erros.push(e.message));
        await page.route('**/*',route=>{
            const url=new URL(route.request().url());
            if(url.hostname!=='aeri-teste.invalid') return route.abort();
            if(url.pathname==='/') {
                const html=fs.readFileSync(path.join(root,'backend/templates/index.html'),'utf8')
                    .replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi,'')
                    .replace(/{%\s*include\s+[^%]+%}/g,'');
                return route.fulfill({contentType:'text/html; charset=utf-8',body:html});
            }
            if(url.pathname.startsWith('/static/')) {
                const arquivo=path.resolve(root,'backend','.'+decodeURIComponent(url.pathname));
                if(!arquivo.startsWith(path.join(root,'backend/static')+path.sep)||!fs.existsSync(arquivo)) return route.abort();
                return route.fulfill({contentType:arquivo.endsWith('.css')?'text/css':arquivo.endsWith('.png')?'image/png':'image/svg+xml',body:fs.readFileSync(arquivo)});
            }
            return route.abort();
        });
        await page.goto('https://aeri-teste.invalid/');
        await page.evaluate(()=>{
            document.getElementById('splash-aeri').remove();
            document.body.classList.remove('splash-active','auth-pending');
            document.getElementById('login-aeri').style.display='none';
            document.querySelectorAll('.page').forEach(p=>p.style.display=p.id==='page-buscas'?'block':'none');
            document.getElementById('main-content').style.display='block';
            document.querySelector('#page-buscas .page-content')?.removeAttribute('hidden');
            const painel=document.createElement('section');
            painel.id='ds-componentes';
            painel.innerHTML=`<h2>Estados compartilhados — dados de teste</h2>
              <p class="aeri-alert" data-state="success">Conferência salva.</p>
              <p class="aeri-alert" data-state="warning">Confira o documento antes de continuar.</p>
              <p class="aeri-alert" data-state="error">Não foi possível salvar. Os dados foram mantidos.</p>
              <p class="aeri-alert" data-state="info">Atualização em andamento.</p>
              <button class="aeri-button aeri-button--primary" aria-busy="true">Processando</button>
              <button class="aeri-button aeri-button--secondary">Cancelar</button>
              <button class="aeri-button aeri-button--danger">Excluir</button>
              <button class="aeri-button aeri-button--primary" disabled>Indisponível</button>
              <p class="aeri-empty">Nenhum resultado encontrado para os filtros informados.</p>`;
            document.querySelector('#page-buscas .buscas-pesquisa-card').append(painel);
        });
        const estilo=async seletor=>page.locator(seletor).first().evaluate(el=>{
            const s=getComputedStyle(el);
            return {bg:s.backgroundColor,color:s.color,opacity:s.opacity,height:el.getBoundingClientRect().height,
                outline:s.outlineStyle,border:s.borderTopColor};
        });
        const campo=await estilo('#buscas-termo');
        assert.equal(campo.bg,'rgb(255, 255, 255)');
        assert(campo.height>=44);
        assert(contraste(campo.color,campo.bg)>=4.5);
        await page.locator('#buscas-termo').focus();
        assert.notEqual((await estilo('#buscas-termo')).outline,'none');
        const primario=await estilo('#btn-buscas-pesquisar');
        assert(contraste(primario.color,primario.bg)>=4.5);
        assert.equal((await estilo('#ds-componentes button:disabled')).opacity,'1');
        assert(contraste((await estilo('.aeri-button--danger')).color,(await estilo('.aeri-button--danger')).bg)>=4.5);
        for(const estado of ['success','warning','error','info']) {
            const s=await estilo(`.aeri-alert[data-state="${estado}"]`);
            assert(contraste(s.color,s.bg)>=4.5,estado);
        }
        await page.locator('#buscas-incluir-encerradas').check();
        assert(await page.locator('#buscas-incluir-encerradas').isChecked());
        assert((await estilo('#buscas-incluir-encerradas')).height<44);
        await page.locator('#buscas-termo').evaluate(e=>{e.readOnly=true;e.value='Pessoa Exemplo';});
        assert.equal((await estilo('#buscas-termo')).opacity,'1');
        await page.locator('#ds-componentes').screenshot({path:path.join(saida,'componentes.png')});
        for(const modal of ['modal-trocar-senha','modal-custas-edicao']) {
            await page.evaluate(id=>document.getElementById(id).classList.add('aberta'),modal);
            await page.waitForFunction(id=>{
                const overlay=document.getElementById(id);
                return getComputedStyle(overlay).opacity==='1'
                    &&getComputedStyle(overlay.querySelector('.modal-box')).opacity==='1';
            },modal);
            assert.equal((await estilo(`#${modal} .modal-box`)).bg,'rgb(255, 255, 255)');
            assert.equal((await estilo(`#${modal} input:not([type="hidden"])`)).bg,'rgb(255, 255, 255)');
            assert((await estilo(`#${modal} input:not([type="hidden"])`)).height>=44);
            await page.screenshot({path:path.join(saida,`${modal}.png`)});
            await page.setViewportSize({width:390,height:844});
            const box=await page.locator(`#${modal} .modal-box`).boundingBox();
            assert(box&&box.x>=0&&box.x+box.width<=391,modal+' cabe no celular');
            await page.screenshot({path:path.join(saida,`${modal}-mobile.png`)});
            await page.evaluate(id=>document.getElementById(id).classList.remove('aberta'),modal);
            await page.setViewportSize({width:1440,height:1080});
        }
        await page.emulateMedia({reducedMotion:'reduce'});
        const tempo=await page.locator('[aria-busy="true"]').evaluate(e=>getComputedStyle(e,'::after').animationDuration);
        assert(parseFloat(tempo)<.01);
        assert.deepEqual(erros,[]);
        console.log('OK: campos reais, contraste AA, foco, checkbox, readonly, quatro alertas, botões, modais de senha/custas, mobile e movimento reduzido. Capturas: '+saida);
    } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
