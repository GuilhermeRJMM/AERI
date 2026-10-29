// Chrome + Playwright. Apenas dados sintéticos; nenhuma chamada de produção.
const {chromium} = require('playwright');
const fs = require('fs');
const path = require('path');
const assert = require('assert/strict');
const root = path.resolve(__dirname, '..');
(async () => {
    const browser = await chromium.launch({channel:'chrome', headless:true});
    try {
        const page = await browser.newPage({viewport:{width:1440,height:1080}});
        const erros = [];
        page.on('pageerror', erro => erros.push(erro.message));
        page.on('dialog', dialog => dialog.type() === 'confirm' ? dialog.accept() : dialog.dismiss());
        const registros = Array.from({length:6}, (_, i) => ({
            id:`teste-${i}`, protocolo:`IN0000000${i+1}X`, credor:i === 0 ? 'BANCO EXEMPLO' : 'CREDOR TESTE',
            devedor:`Pessoa Exemplo ${i+1}`, fase:['INTIMACAO','INTIMACAO','EDITAL','CONSOLIDACAO','EDITAL','INTIMACAO'][i],
            nomeAndamento:'Aguardando orçamento', ultimoAndamento:'2026-10-20', ultimaConferencia:null,
            historico:[], protocoloRtd:i === 0 ? '20260000000000001' : '', atualizadoEm:'2026-10-20T12:00:00Z',
            rtd:i === 0 ? [{protocolo:'20260000000000002',novo:false,situacao:'Orçamento',eventos:[]}] : [],
            situacaoConferencia:{classe:'cinza',rotulo:'Falta conferir',detalhe:'',ordem:3},
        }));
        const envios = [];
        let falhar = false;
        await page.route('**/*', async route => {
            const url = new URL(route.request().url());
            if (url.hostname !== 'aeri-teste.invalid') return route.abort();
            const json = (body, status=200) => route.fulfill({status, contentType:'application/json',body:JSON.stringify(body)});
            if (url.pathname === '/') {
                let html = fs.readFileSync(path.join(root,'backend/templates/index.html'),'utf8');
                html = html.replace(/\{%\s*include\s+['"]([^'"]+)['"]\s*%\}/g,
                    (_,nome) => fs.readFileSync(path.join(root,'backend/templates',nome),'utf8'));
                html = html.replace(/<script type="module" src="\/static\/js\/app.js[^\"]*"><\/script>/,
                    `<script type="module">import {iniciarIntimacoes,carregarIntimacoes} from '/static/js/intimacoes.js';
                    window.recarregarMesa=carregarIntimacoes;document.getElementById('splash-aeri').remove();
                    document.body.classList.remove('splash-active','auth-pending');document.body.dataset.perfil='ADMIN';
                    document.querySelectorAll('.page').forEach(p=>p.classList.remove('active','ativa'));
                    const p=document.getElementById('page-rotina');p.classList.add('active','ativa');p.style.display='block';
                    document.getElementById('login-aeri').style.display='none';
                    iniciarIntimacoes();await carregarIntimacoes();</script>`);
                return route.fulfill({contentType:'text/html; charset=utf-8',body:html});
            }
            if (url.pathname === '/api/sessao') return json({csrfToken:'teste-sintetico'});
            if (url.pathname === '/api/intimacoes') return json(registros);
            if (url.pathname.endsWith('/conferir')) {
                const dados = route.request().postDataJSON() || {};
                envios.push(dados);
                if (falhar) return json({detail:'Falha sintética ao salvar'},500);
                const registro = registros.find(r=>url.pathname.includes(r.id));
                Object.assign(registro,{ultimaConferencia:'2026-10-26',atualizadoEm:'2099-01-01T12:00:00Z',
                    situacaoConferencia:{classe:'verde',rotulo:'Conferida hoje',ordem:0}});
                if (dados.nomeAndamento) Object.assign(registro,{nomeAndamento:dados.nomeAndamento,ultimoAndamento:dados.dataAndamento});
                return json(registro);
            }
            if (url.pathname.startsWith('/api/')) return json([]);
            if (url.pathname.startsWith('/static/')) {
                const arquivo = path.resolve(root,'backend','.'+decodeURIComponent(url.pathname));
                if (!arquivo.startsWith(path.join(root,'backend/static')+path.sep) || !fs.existsSync(arquivo)) return route.abort();
                return route.fulfill({contentType:arquivo.endsWith('.js')?'text/javascript':arquivo.endsWith('.css')?'text/css':'image/svg+xml',body:fs.readFileSync(arquivo)});
            }
            return route.abort();
        });
        await page.goto('https://aeri-teste.invalid/');
        const fila = page.locator('#rotina-fila [data-selecionar-intimacao]');
        await fila.first().waitFor();
        assert.equal(await fila.count(),6);
        const foco=page.locator('#rotina-foco');
        assert(await foco.getByText('20260000000000001',{exact:true}).isVisible());
        assert(await foco.getByText('20260000000000002',{exact:true}).isVisible());
        assert(await foco.locator('.mesa-confirmar').isDisabled());
        await foco.getByLabel('Mesmo andamento',{exact:false}).check();
        assert.equal(envios.length,0,'Selecionar opção não salva');
        await foco.getByRole('button',{name:'Registrar conferência sem alteração'}).click();
        await page.locator('#mesa-feedback').waitFor({state:'visible'});
        assert.equal(envios.length,1);
        assert.equal(await fila.count(),6,'IN conferido continua na fila');
        assert.equal(await foco.locator('h2').textContent(),'IN00000001X');
        await foco.getByLabel('Mesmo andamento',{exact:false}).check();
        assert(await foco.locator('.mesa-confirmar').isDisabled(),'Evita dupla conferência sem alteração');
        await foco.getByRole('radio',{name:'Novo andamento Encontrei uma movimentação diferente.'}).check();
        await foco.locator('[name=novoAndamento]').fill('Orçamento disponível');
        await foco.locator('[name=dataAndamento]').fill('2026-10-23');
        await page.evaluate(()=>window.recarregarMesa());
        assert.equal(await foco.locator('[name=novoAndamento]').inputValue(),'Orçamento disponível','Polling preserva rascunho');
        assert.equal(await foco.locator('[name=dataAndamento]').inputValue(),'2026-10-23');
        await foco.getByRole('button',{name:'Salvar novo andamento e conferir'}).click();
        await page.waitForFunction(()=>document.querySelector('.mesa-referencia strong')?.textContent==='Orçamento disponível');
        assert.equal(envios[1].dataAndamento,'2026-10-23');
        assert.equal(envios[1].nomeAndamento,'Orçamento disponível');
        const busca = page.locator('#busca-intimacao');
        for (const [termo,total] of [['BANCO EXEMPLO',1],['Pessoa Exemplo 3',1],['IN00000004X',1],['20260000000000002',1],['',6]]) {
            await busca.fill(termo); assert.equal(await fila.count(),total,`Busca ${termo}`);
        }
        for (const fase of ['EDITAL','CONSOLIDACAO']) {
            await page.locator(`[data-fase=${fase}]`).click();
            assert.equal(await foco.locator('.rotina-in-protocolo-rtd').count(),0);
            assert.equal(await foco.locator('[data-acao=novo-envio-rtd]').count(),0);
        }
        await page.locator('[data-fase=TODAS]').click();
        await page.locator('[data-selecionar-intimacao="teste-1"]').click();
        falhar=true;
        await foco.getByLabel('Mesmo andamento',{exact:false}).check();
        await foco.locator('.mesa-confirmar').click();
        await page.waitForFunction(()=>!document.querySelector('.mesa-editor fieldset').disabled);
        assert.equal(await foco.locator('.rotina-in-estado').textContent(),'Falta conferir','Falha não confirma item');
        falhar=false;
        await page.locator('[data-selecionar-intimacao="teste-0"]').click();
        assert((await page.locator('.rotina-fila-painel').boundingBox()).x < (await foco.boundingBox()).x,'Fila à esquerda e comparação à direita');
        const cores=await page.evaluate(()=>['.rotina-in-cartao','.mesa-referencia','.mesa-consulta','.rotina-fila-painel'].map(s=>getComputedStyle(document.querySelector('#page-rotina '+s)).backgroundColor));
        assert(cores.every(c=>c==='rgb(255, 255, 255)'),JSON.stringify(cores));
        const tema = await page.evaluate(() => {
            const folhas = [...document.querySelectorAll('link[rel=stylesheet]')];
            return {
                legado: folhas.findIndex(e => e.id === 'rtd-estilos'),
                sync: folhas.findIndex(e => e.id === 'sync-theme'),
                mesa: folhas.findIndex(e => e.href.includes('/intimacoes-mesa.css')),
                verde: getComputedStyle(document.getElementById('page-rotina')).getPropertyValue('--aeri-green').trim(),
                fundoAtivo: getComputedStyle(document.querySelector('.rotina-fase-btn.ativa')).backgroundColor,
            };
        });
        assert(tema.legado >= 0 && tema.legado < tema.sync && tema.sync < tema.mesa,'Legado não sobrepõe o tema da mesa');
        assert.equal(tema.verde,'#047857','Tokens locais independem do Design System global');
        assert.equal(tema.fundoAtivo,'rgb(236, 253, 245)');
        await page.evaluate(()=>window.scrollTo(0,0));
        await page.screenshot({path:path.join(require('os').tmpdir(),'aeri-mesa-real-desktop.png'),fullPage:true});
        await page.setViewportSize({width:390,height:844});
        assert(await page.evaluate(()=>document.documentElement.scrollWidth <= window.innerWidth),'Sem overflow horizontal');
        await page.screenshot({path:path.join(require('os').tmpdir(),'aeri-mesa-real-mobile.png'),fullPage:true});
        await page.evaluate(async()=>{document.body.dataset.perfil='USUARIO';window.aeriPermissoes={};await window.recarregarMesa();});
        assert.equal(await foco.locator('[data-mesa-conferencia]').count(),0,'Perfil sem permissão não registra conferência');
        assert.deepEqual(erros,[]);
        console.log('OK Mesa: seis INs, busca, fases, RTD, confirmação explícita, data, rascunho, erro, tema branco e mobile.');
    } finally {await browser.close();}
})().catch(erro=>{console.error(erro);process.exitCode=1;});
