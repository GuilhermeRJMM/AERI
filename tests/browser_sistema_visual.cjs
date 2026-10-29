// Auditoria visual transversal, sem credenciais, backend ou acesso à rede externa.
const {chromium}=require('playwright');
const fs=require('fs'),path=require('path'),os=require('os'),assert=require('assert/strict');
const raiz=path.resolve(__dirname,'..');
const saida=path.join(os.tmpdir(),'aeri-sistema-visual-20261029');
function template(nome){
    return fs.readFileSync(path.join(raiz,'backend/templates',nome),'utf8')
        .replace(/{%\s*include\s+['"]([^'"]+)['"]\s*%}/g,(_,n)=>template(n))
        .replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi,'');
}
(async()=>{
    const browser=await chromium.launch({channel:'chrome',headless:true});
    fs.mkdirSync(saida,{recursive:true});
    const relatorio=[];
    try{
        const page=await browser.newPage({viewport:{width:1440,height:1050},reducedMotion:'reduce'});
        const erros=[];page.on('pageerror',e=>erros.push(e.message));
        await page.route('**/*',route=>{
            const u=new URL(route.request().url());
            if(u.hostname!=='aeri-teste.invalid')return route.abort();
            const json=body=>route.fulfill({contentType:'application/json',body:JSON.stringify(body)});
            if(u.pathname==='/')return route.fulfill({contentType:'text/html; charset=utf-8',body:template('index.html')});
            if(u.pathname==='/api/painel')return json({modulos:[
                ['buscas','certidao','Buscas'],['incra','certidao','INCRA'],['rotina','certidao','Intimações'],
                ['contratos','rgi','Minutas'],['onus','rgi','Ônus e matrícula'],['mapaonr','rgi','MAPA-ONR'],
                ['usuarios','sistema','Usuários'],['integracoes','sistema','Integrações']
            ].map(([id,setor,nome])=>({id,setor,nome,grupo:'Ferramentas',descricao:'Dados sintéticos para conferência visual.'})),alertas:[]});
            if(u.pathname==='/api/sistema/configuracao')return json({oficio:{webhookConfigurado:true},executor:'Executor de teste, sem operações reais.',agendas:[{chave:'intimacoes',habilitada:true,intervalo_minutos:30,hora_inicio:8,hora_fim:18,dias_semana:[0,1,2,3,4]}],execucoes:[]});
            if(u.pathname==='/api/intimacoes')return json([{id:'visual-1',protocolo:'IN00000001X',credor:'BANCO EXEMPLO',devedor:'Pessoa Exemplo',fase:'INTIMACAO',nomeAndamento:'Aguardando orçamento',ultimoAndamento:'2026-10-29',historico:[],rtd:[],situacaoConferencia:{classe:'cinza',rotulo:'Falta conferir',ordem:3}}]);
            if(u.pathname.startsWith('/api/'))return json([]);
            if(u.pathname.startsWith('/static/')){
                const arquivo=path.resolve(raiz,'backend','.'+decodeURIComponent(u.pathname));
                if(!arquivo.startsWith(path.join(raiz,'backend/static')+path.sep)||!fs.existsSync(arquivo))return route.abort();
                return route.fulfill({contentType:arquivo.endsWith('.css')?'text/css':arquivo.endsWith('.js')?'text/javascript':arquivo.endsWith('.png')?'image/png':'image/svg+xml',body:fs.readFileSync(arquivo)});
            }
            return route.abort();
        });
        await page.goto('https://aeri-teste.invalid/');
        await page.evaluate(async()=>{
            document.getElementById('splash-aeri').remove();
            document.body.classList.remove('auth-pending','splash-active');document.body.dataset.perfil='ADMIN';
            document.getElementById('login-aeri').style.display='none';
            for(const id of ['card-setor-certidao','card-setor-rgi','card-setor-sistema'])document.getElementById(id).hidden=false;
            await (await import('/static/js/painel.js')).carregarPainel();
            await (await import('/static/js/sistema.js')).carregarSistema();
            const intimacoes=await import('/static/js/intimacoes.js');
            intimacoes.iniciarIntimacoes();await intimacoes.carregarIntimacoes();
            const analise=await import('/static/js/analisador.js');
            analise.renderizarResultado({numero_matricula:'40001',resultado:'NEGATIVA PARA ÔNUS',
                publicidade:'SEM PUBLICIDADE',atos:[],proprietarios_atuais:[],imovel:{},meta:{versao:'TESTE'}});
            const rtd=await import('/static/js/rtd_intimacoes.js');
            document.querySelector('#modal-intimacao .modal-box').insertAdjacentHTML('beforeend',rtd.detalhesRtd({fase:'INTIMACAO',rtd:[{
                protocolo:'20260000000000001',situacao:'Orçamento',novo:true,versao:1,
                dados:{ValorOrcamento:100},eventos:[],consultadoEm:'2026-10-29T12:00:00Z'
            }]}));
            document.querySelectorAll('.modal-overlay').forEach(e=>e.classList.remove('aberta'));
            document.body.style.overflow='';
        });
        const paginas=await page.locator('.page[id]').evaluateAll(es=>es.map(e=>e.id));
        for(const largura of [1440,390]){
            await page.setViewportSize({width:largura,height:1050});
            for(const id of paginas){
                await page.evaluate(id=>{
                    document.querySelectorAll('.page[id]').forEach(e=>{e.style.display=e.id===id?'block':'none';e.classList.toggle('active',e.id===id);});window.scrollTo(0,0);
                },id);
                const problemas=await page.locator('#'+id).evaluate(p=>{
                    const visivel=e=>e.getBoundingClientRect().width>0&&e.getBoundingClientRect().height>0&&getComputedStyle(e).visibility!=='hidden';
                    const escuros=[...p.querySelectorAll('*')].filter(e=>{
                        if(!visivel(e)||['BUTTON','SVG','PATH','I','CANVAS','PROGRESS'].includes(e.tagName))return false;
                        const c=getComputedStyle(e).backgroundColor.match(/[\d.]+/g)?.map(Number);
                        return c&&c.length>=3&&(c[3]??1)>.8&&Math.max(...c.slice(0,3))<100;
                    }).map(e=>({tag:e.tagName,classe:e.className,cor:getComputedStyle(e).backgroundColor}));
                    return {escuros,overflow:document.documentElement.scrollWidth>innerWidth+2};
                });
                relatorio.push({pagina:id,largura,...problemas});
                await page.screenshot({path:path.join(saida,`${id}-${largura}.png`)});
            }
        }
        await page.evaluate(()=>{
            document.querySelectorAll('.page[id]').forEach(e=>e.style.display=e.id==='page-contratos'?'block':'none');
            document.getElementById('page-contratos').classList.add('contratos-extraindo');
            document.getElementById('contratos-carregando').style.setProperty('--pct','55%');
            document.getElementById('contratos-carregando-numero').textContent='55';
        });
        assert.equal(await page.locator('#contratos-carregando-numero').evaluate(e=>getComputedStyle(e).color),'rgb(15, 23, 42)');
        assert.equal(await page.locator('.contratos-carregando-pct').evaluate(e=>getComputedStyle(e,'::after').content),'none');
        await page.screenshot({path:path.join(saida,'minutas-processando.png'),animations:'disabled'});
        await page.evaluate(()=>document.getElementById('page-contratos').classList.remove('contratos-extraindo'));
        const modais=await page.locator('.modal-overlay[id]').evaluateAll(es=>es.filter(e=>e.querySelector('.modal-box')).map(e=>e.id));
        for(const largura of [1440,390]){
            await page.setViewportSize({width:largura,height:1050});
            for(const id of modais){
                await page.evaluate(id=>{const e=document.getElementById(id);e.hidden=false;e.classList.add('aberta');},id);
                await page.waitForFunction(id=>{
                    const e=document.getElementById(id);
                    return getComputedStyle(e).opacity==='1'&&getComputedStyle(e.querySelector('.modal-box')).opacity==='1';
                },id);
                const problema=await page.locator('#'+id+' .modal-box').evaluate(e=>{
                    const r=e.getBoundingClientRect(),s=getComputedStyle(e);
                    return {cor:s.backgroundColor,overflow:r.left<0||r.right>innerWidth+2};
                });
                relatorio.push({pagina:id,largura,escuros:problema.cor!=='rgb(255, 255, 255)'?[problema]:[],overflow:problema.overflow});
                const fechar=page.locator('#'+id+' .modal-fechar').first();
                if(await fechar.count()&&await fechar.isVisible()) {
                    assert(await fechar.evaluate(e=>{
                        const r=e.getBoundingClientRect();
                        const alvo=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);
                        return r.width>=40&&r.height>=40&&(alvo===e||e.contains(alvo));
                    }),id+' botão de fechar visível e clicável');
                }
                await page.screenshot({path:path.join(saida,`${id}-${largura}.png`),animations:'disabled'});
                await page.evaluate(id=>document.getElementById(id).classList.remove('aberta'),id);
            }
        }
        await page.evaluate(async()=>{(await import('/static/js/usuarios.js')).abrirTrocaSenha(true);});
        assert(await page.locator('#btn-fechar-troca-senha').isHidden(),'Troca obrigatória não pode ser dispensada pela estilização');
        await page.evaluate(()=>document.getElementById('modal-trocar-senha').classList.remove('aberta'));
        await page.setViewportSize({width:390,height:1050});
        await page.evaluate(()=>{document.getElementById('login-aeri').style.display='flex';document.getElementById('login-aeri').classList.add('aberto');});
        await page.waitForFunction(()=>[...document.images].filter(e=>e.getBoundingClientRect().width).every(e=>e.complete&&e.naturalWidth>0));
        assert.equal(await page.locator('.login-card').evaluate(e=>getComputedStyle(e).backgroundColor),'rgb(255, 255, 255)');
        await page.screenshot({path:path.join(saida,'login-390.png')});
        fs.writeFileSync(path.join(saida,'auditoria.json'),JSON.stringify({paginas:paginas.length,relatorio,erros},null,2));
        console.log(JSON.stringify({paginas:paginas.length,casos:relatorio.length,problemas:relatorio.filter(r=>r.escuros.length||r.overflow),erros,saida}));
        assert.deepEqual(erros,[]);
        if(process.argv.includes('--exigir-limpo'))assert.deepEqual(relatorio.filter(r=>r.escuros.length||r.overflow),[]);
    }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
