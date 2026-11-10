// Navegador real, API/motor local e dados sintéticos. Rede de produção bloqueada.
const {chromium}=require('playwright'),{spawnSync}=require('child_process');
const fs=require('fs'),path=require('path'),assert=require('assert/strict');
const root=path.resolve(__dirname,'..'),python=process.env.AERI_PYTHON;
if(!python)throw Error('Configure AERI_PYTHON.');
function motor(acao,dados={}) {
    const r=spawnSync(python,['-B','-X','utf8','-c',`import sys,json\nfrom backend.app.gerador_notas.servico import catalogo_para_tela,previa\nd=json.load(sys.stdin)\nprint(json.dumps(catalogo_para_tela() if sys.argv[1]=='catalogo' else previa(d),ensure_ascii=False))`,acao],{cwd:root,input:JSON.stringify(dados),encoding:'utf8'});
    if(r.status!==0)throw Error(r.stderr);return JSON.parse(r.stdout);
}
(async()=>{
 const b=await chromium.launch({channel:'chrome',headless:true});try {
    const p=await b.newPage({viewport:{width:1440,height:1000}}),erros=[],previas=[];let geracoes=0;
    p.on('pageerror',e=>erros.push(e.message));
    await p.route('**/*',async r=>{
        const u=new URL(r.request().url());if(u.hostname!=='notas-ajustes.invalid')return r.abort();
        const json=(v,status=200)=>r.fulfill({status,contentType:'application/json',body:JSON.stringify(v)});
        if(u.pathname==='/'){
            let h=fs.readFileSync(path.join(root,'backend/templates/index.html'),'utf8').replace(/\{%\s*include\s+['"]([^'"]+)['"]\s*%\}/g,(_,n)=>fs.readFileSync(path.join(root,'backend/templates',n),'utf8'));
            h=h.replace(/<script type="module" src="\/static\/js\/app.js[^\"]*"><\/script>/,`<script type="module">import {iniciarGeradorNotas,configurarAcessoGeradorNotas} from '/static/js/gerador_notas.js';import {definirCsrfToken} from '/static/js/api.js?v=20260902-arquivo-v1';definirCsrfToken('csrf-teste');document.getElementById('splash-aeri').remove();document.body.classList.remove('splash-active','auth-pending');document.querySelectorAll('.page').forEach(e=>e.classList.remove('active'));document.getElementById('page-geradornotas').classList.add('active');document.querySelectorAll('.nav-item').forEach(e=>e.classList.toggle('active',e.dataset.page==='geradornotas'));iniciarGeradorNotas();configurarAcessoGeradorNotas(true,'pessoa-teste');</script>`);
            return r.fulfill({contentType:'text/html; charset=utf-8',body:h});
        }
        if(u.pathname==='/api/gerador-notas/catalogo')return json(motor('catalogo'));
        if(u.pathname==='/api/gerador-notas/consultar-protocolo'){
            const n=r.request().postDataJSON().protocolo.replace(/\./g,'');
            return json({protocolo:n,titulo:n==='186804'?'Averbação de construção':'Escritura pública de compra e venda'});
        }
        if(u.pathname==='/api/gerador-notas/previa') {
            const d=r.request().postDataJSON();previas.push(d);return json(motor('previa',d));
        }
        if(u.pathname==='/api/gerador-notas/gerar'){geracoes++;return json({},422);}
        if(u.pathname.startsWith('/static/')){
            const f=path.resolve(root,'backend','.'+u.pathname);
            if(!f.startsWith(path.join(root,'backend/static')+path.sep)||!fs.existsSync(f))return r.abort();
            return r.fulfill({contentType:f.endsWith('.css')?'text/css':f.endsWith('.png')?'image/png':'text/javascript',body:fs.readFileSync(f)});
        }return r.abort();
    });
    await p.goto('https://notas-ajustes.invalid/');await p.locator('#gn-editor').waitFor({state:'visible'});
    assert.equal(await p.locator('[data-gn-exigencia]').count(),72);
    await p.locator('#gn-protocolo').fill('186804');
    await p.waitForFunction(()=>document.getElementById('gn-titulo').value==='Averbação de construção');
    assert(await p.locator('[data-gn-exigencia="construcao-sem-habite-se"]').isVisible());
    assert.equal(await p.locator('[data-gn-exigencia="itbi-nao-apresentado"]').count(),0);
    assert.equal(await p.locator('[data-gn-exigencia="art-area-nao-corresponde"]').count(),0);
    await p.locator('[data-gn-exigencia="construcao-sem-habite-se"]').check();
    const matricula=p.locator('[data-gn-campo="matricula"]');
    assert.equal(await matricula.getAttribute('inputmode'),'numeric');
    await matricula.fill('18.552');assert.equal(await matricula.inputValue(),'18552');
    await matricula.fill('R20');assert.equal(await matricula.inputValue(),'18552');
    assert.equal(await matricula.evaluate(e=>e.checkValidity()),false);
    await p.locator('#gn-gerar').click();assert.equal(geracoes,0);
    await matricula.fill('18552');
    await p.waitForFunction(()=>document.querySelector('.nota-resumo-balao')?.textContent.includes('18.552'));
    assert(await p.locator('#gn-previa').evaluate(e=>e.firstElementChild.classList.contains('nota-resumo')));
    assert.equal(await p.locator('.nota-resumo-balao').evaluate(e=>getComputedStyle(e).backgroundColor),'rgb(180, 199, 219)');
    assert.equal(await p.locator('.nota-resumo-balao p').evaluate(e=>getComputedStyle(e).color),'rgb(16, 36, 58)');
    assert.equal(await p.locator('.nota-resumo > p').first().textContent().then(t=>t.includes('Referência conjunta')),false);
    assert(await p.locator('.nota-referencia').isVisible());
    await p.locator('#gn-protocolo').fill('186805');
    await p.waitForFunction(()=>document.getElementById('gn-titulo').value==='Escritura pública de compra e venda');
    assert(await p.locator('[data-gn-exigencia="itbi-nao-apresentado"]').isVisible());
    assert(await p.locator('[data-gn-exigencia="construcao-sem-habite-se"]').isChecked(),'Não apagar seleção anterior');
    await p.locator('#gn-todas-pendencias').click();assert.equal(await p.locator('[data-gn-exigencia]').count(),72);
    await p.locator('[data-gn-exigencia="declaracao-limites-sem-assinatura"]').check();
    const numeros=p.locator('[data-gn-campo="matriculas_confrontantes"]');
    await numeros.first().fill('10100');await p.locator('[data-gn-adicionar-matricula="matriculas_confrontantes"]').click();
    await numeros.nth(1).fill('10200');
    await p.waitForTimeout(700);
    assert.deepEqual(previas.at(-1).itens.find(i=>i.exigencia==='declaracao-limites-sem-assinatura').valores.matriculas_confrontantes,['10100','10200']);
    assert.match(await p.locator('#gn-previa').textContent(),/10\.100 e 10\.200/);
    await p.locator('#gn-titulo').fill('Documento excepcional sem classificação');assert.equal(await p.locator('[data-gn-exigencia]').count(),72);
    // Capturas do estado mais simples, sem alerta de formulário ou balão nativo.
    await p.locator('[data-gn-exigencia="declaracao-limites-sem-assinatura"]').uncheck();
    await p.locator('#gn-titulo').fill('Averbação de construção');await p.waitForTimeout(600);
    fs.mkdirSync(path.join(root,'.tmp/notas-ajustes'),{recursive:true});
    await p.locator('#gn-editor').screenshot({path:path.join(root,'.tmp/notas-ajustes/desktop.png')});
    await p.setViewportSize({width:390,height:900});
    assert(await p.locator('#gn-gerar').isVisible());
    await p.screenshot({path:path.join(root,'.tmp/notas-ajustes/mobile.png'),fullPage:true});
    assert.deepEqual(erros,[]);
    const legado=await b.newPage();
    legado.on('pageerror',e=>erros.push(e.message));
    await legado.route('**/*',async r=>{
        const u=new URL(r.request().url());if(u.hostname!=='notas-legado.invalid')return r.abort();
        const json=v=>r.fulfill({contentType:'application/json',body:JSON.stringify(v)});
        if(u.pathname==='/')return r.fulfill({contentType:'text/html; charset=utf-8',body:fs.readFileSync(path.join(root,'backend/private/gerador_notas/index.html'))});
        if(u.pathname==='/api/sessao')return json({csrfToken:'csrf-teste'});
        if(u.pathname==='/api/gerador-notas/catalogo')return json(motor('catalogo'));
        if(u.pathname==='/api/gerador-notas/previa')return json(motor('previa',r.request().postDataJSON()));
        if(u.pathname.startsWith('/static/')){
            const f=path.resolve(root,'backend','.'+u.pathname);
            if(!f.startsWith(path.join(root,'backend/static')+path.sep)||!fs.existsSync(f))return r.abort();
            return r.fulfill({contentType:f.endsWith('.css')?'text/css':'text/javascript',body:fs.readFileSync(f)});
        }return r.abort();
    });
    await legado.goto('https://notas-legado.invalid/');
    await legado.waitForFunction(()=>document.querySelectorAll('#lista input[type=checkbox]').length===72);
    await legado.locator('#titulo').fill('Averbação de construção');
    assert(await legado.locator('#lista input[type=checkbox]').count()<72);
    await legado.locator('#lista label').filter({hasText:'Averbação de construção sem habite-se'}).locator('input').check();
    await legado.locator('[data-numero]').fill('18.552');
    assert.equal(await legado.locator('[data-numero]').inputValue(),'18552');
    await legado.waitForFunction(()=>document.querySelector('.nota-resumo-balao')?.textContent.includes('18.552'));
    assert.deepEqual(erros,[]);
    console.log('OK: protocolo preenche título e filtra; desconhecido/ver todas; seleção preservada; somente números e matrículas separadas; resumo antes da nota; balão azul; referência no rodapé; desktop/mobile.');
 }finally{await b.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
