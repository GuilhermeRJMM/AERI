// Browser plugin not available: Playwright/Chrome. Só HTML e dados sintéticos.
const {chromium} = require('playwright');
const fs = require('fs'), path = require('path'), assert = require('assert/strict');
const root = path.resolve(__dirname, '..');
const coletor = fs.readFileSync(path.join(root,'scripts/oficio/coletar.js'),'utf8');

function htmlPortal(pagina, total=257, cartorio='8422', duplicado=false) {
    const campos = ['Protocolo','Prenotação','Status','Data Status','Data Pedido','Prazo da Purga'];
    const numeroPaginas = Math.ceil(total/10);
    const controles = ['filterProtocolo','filterDataPedidoDe','filterDataPedidoAte','filterPrenotacao',
        'filterEmolumentos','filterSolicitante'].map(id=>`<input id="${id}">`).join('')
        + ['filterStatus','filterIsencao','filterNotificadoPorE-mail'].map(id=>`<select id="${id}"><option value="-1" selected>Todos</option></select>`).join('');
    const linhas = Array.from({length:Math.min(10,total-(pagina-1)*10)},(_,i)=>{
        const num = duplicado ? i+1 : (pagina-1)*10+i+1;
        return `<tr><td>IN${String(num).padStart(8,'0')}C</td><td>${180000+num}</td><td>Prenotado</td><td>09/11/2026</td><td>08/11/2026</td><td>-</td></tr>`;
    }).join('');
    return `<!doctype html><meta charset="utf-8"><script>function DisableDropConditional(){};DisableDropConditional('filterCartorio',${cartorio});</script>${controles}<select id="filterCartorio"><option value="${cartorio}" selected>Serventia teste</option></select><div class="default-pagination">${total} Itens Página ${pagina} de ${numeroPaginas}</div><table><thead><tr>${campos.map(c=>`<th>${c}</th>`).join('')}</tr></thead><tbody>${linhas}</tbody></table>`;
}

(async()=>{
    const browser = await chromium.launch({channel:'chrome',headless:true});
    try {
        const portal = await browser.newPage(); let modo='normal'; const chamadas=[];
        await portal.route('**/*', async r=>{
            const u=new URL(r.request().url());
            assert.equal(u.hostname,'oficioeletronico.com.br');
            assert.equal(u.pathname,'/Cartorios/Intimacoes');
            if (r.request().method()==='GET') return r.fulfill({contentType:'text/html',body:htmlPortal(1)});
            assert.equal(r.request().method(),'POST');
            assert.equal(r.request().postData(),null);
            const n=Number(u.searchParams.get('page')); chamadas.push(n);
            return r.fulfill({contentType:'text/html',body:htmlPortal(n,modo==='reset'?28:257,modo==='cartorio'?'9999':'8422',modo==='duplicado')});
        });
        await portal.goto('https://oficioeletronico.com.br/Cartorios/Intimacoes');
        const executar=()=>portal.evaluate(`(${coletor})({cartorio:'8422',minimo:250})`);
        let dados=await executar();
        assert.equal(dados.completo,true); assert.equal(dados.itens.length,257);assert.equal(dados.paginas.length,26);
        assert.equal(new Set(dados.itens.map(i=>i.protocolo)).size,257);
        assert.deepEqual(Object.keys(dados.itens[0]).sort(),['protocolo','prenotacao','status','dataStatus','dataPedido','prazoPurga'].sort());
        assert.equal(chamadas.length,25);
        await portal.evaluate(()=>{const i=document.createElement('input');i.id='filterAptoEdital';i.value='sim';document.body.append(i)});
        assert.equal((await executar()).erro,'filtro_ativo_ou_desconhecido');
        await portal.locator('#filterAptoEdital').evaluate(e=>e.remove());
        for (const [m,erro] of [['reset','total_ou_pagina_divergente'],['cartorio','cartorio_nao_confirmado'],['duplicado','in_invalido_ou_duplicado']]) {
            modo=m; chamadas.length=0; dados=await executar(); assert.equal(dados.erro,erro);assert.equal(chamadas.length,1);
        }
        chamadas.length=0;
        await portal.locator('#filterProtocolo').fill('IN00000001C');
        assert.equal((await executar()).erro,'filtro_ativo_ou_desconhecido');assert.equal(chamadas.length,0);
        await portal.close();

        const p=await browser.newPage({viewport:{width:1440,height:1000}}), erros=[], escritas=[];
        p.on('pageerror',e=>erros.push(e.message));
        let temCaptura=true, offline=false, polls=0;
        const registros=[1,2].map(i=>({id:`teste-${i}`,protocolo:`IN0000000${i}C`,credor:'BANCO TESTE',
            devedor:`Pessoa Exemplo ${i}`,fase:'INTIMACAO',nomeAndamento:'Pagar RTD',ultimoAndamento:'2026-11-04',
            ultimaConferencia:null,historico:[],rtd:[],atualizadoEm:'2026-11-04T12:00:00Z',
            situacaoConferencia:{classe:'cinza',rotulo:'Falta conferir',detalhe:'',ordem:3}}));
        await p.route('**/*', async r=>{
            const u=new URL(r.request().url());if(u.hostname!=='analisador-teste.invalid')return r.abort();
            const json=(d,status=200)=>r.fulfill({status,contentType:'application/json',body:JSON.stringify(d)});
            if(u.pathname==='/'){
                let html=fs.readFileSync(path.join(root,'backend/templates/index.html'),'utf8').replace(/\{%\s*include\s+['"]([^'"]+)['"]\s*%\}/g,(_,n)=>fs.readFileSync(path.join(root,'backend/templates',n),'utf8'));
                html=html.replace(/<script type="module" src="\/static\/js\/app.js[^\"]*"><\/script>/,
                    `<script type="module">import {iniciarIntimacoes,carregarIntimacoes,limparIntimacoes} from '/static/js/intimacoes.js';
                    import {carregarConsultaOficio} from '/static/js/oficio_consultas.js?v=20261110-consulta-v1';
                    window.limpar=limparIntimacoes;window.recarregar=()=>carregarConsultaOficio(true);
                    document.getElementById('splash-aeri').remove();document.body.classList.remove('splash-active','auth-pending');document.body.dataset.perfil='ADMIN';
                    document.querySelectorAll('.page').forEach(e=>e.classList.remove('active','ativa'));
                    document.getElementById('page-rotina').classList.add('active','ativa');document.getElementById('page-rotina').style.display='block';
                    document.getElementById('login-aeri').style.display='none';iniciarIntimacoes();await carregarIntimacoes();</script>`);
                return r.fulfill({contentType:'text/html; charset=utf-8',body:html});
            }
            if(u.pathname==='/api/sessao')return json({csrfToken:'csrf-teste'});
            if(u.pathname==='/api/intimacoes')return json(registros);
            if(u.pathname==='/api/oficio-consultas/trabalhos'){
                assert.equal(r.request().headers()['x-csrf-token'],'csrf-teste');
                escritas.push(u.pathname);
                if(offline)return json({detail:'Abra o conector neste computador'},409);
                return json({id:'11111111-1111-4111-8111-111111111111',estado:'PENDENTE'},202);
            }
            if(u.pathname.startsWith('/api/oficio-consultas/trabalhos/')){
                polls++;return json({estado:polls<2?'LENDO':'PRONTO',mensagem:''});
            }
            if(u.pathname==='/api/oficio-consultas/conectores')return json({codigo:'oficio_pair_'+'a'.repeat(43)});
            if(u.pathname==='/api/oficio-consultas'){
                if(r.request().method()==='POST'){
                    assert.equal(r.request().headers()['x-csrf-token'],'csrf-teste');
                    escritas.push(u.pathname);return json({totalConsultado:1});
                }
                if(!temCaptura)return json({detail:'Falha sintética na consulta'},503);
                return json({disponivel:true,consultadoEm:new Date().toISOString(),totalConsultado:257,totalVinculado:1,
                    itens:[{protocolo:'IN00000001C',status:'Expedição de Intimação - RI',prenotacao:'186804',dataStatus:'2026-11-04'}]});
            }
            if(u.pathname.startsWith('/api/')) {if(r.request().method()!=='GET')escritas.push(u.pathname);return json([]);}
            if(u.pathname.startsWith('/static/')){
                const f=path.resolve(root,'backend','.'+u.pathname);
                if(!f.startsWith(path.join(root,'backend/static')+path.sep)||!fs.existsSync(f))return r.abort();
                return r.fulfill({contentType:f.endsWith('.js')?'text/javascript':f.endsWith('.css')?'text/css':'image/svg+xml',body:fs.readFileSync(f)});
            }
            return r.abort();
        });
        await p.goto('https://analisador-teste.invalid/');
        await p.locator('.mesa-consulta strong').filter({hasText:'Expedição de Intimação - RI'}).waitFor();
        assert(await p.locator('.mesa-referencia').getByText('Pagar RTD',{exact:true}).isVisible());
        assert(await p.locator('.mesa-confirmar').isDisabled());assert.equal(escritas.length,0);
        assert.equal(await p.locator('.mesa-consulta a').getAttribute('href'),'https://oficioeletronico.com.br/');
        await p.locator('.oficio-consulta-painel > summary').click();
        assert.match(await p.locator('#oficio-consulta-aviso').textContent(),/257 INs históricos/);
        assert.equal(await p.locator('.oficio-consulta-painel').evaluate(e=>getComputedStyle(e).backgroundColor),'rgb(255, 255, 255)');
        assert.equal(await p.locator('#importar-consulta-oficio').count(),0,'Sem importação manual');
        await p.locator('#oficio-consultar-agora').click();
        await p.waitForFunction(()=>!document.getElementById('oficio-consultar-agora').disabled);
        assert.deepEqual(escritas,['/api/oficio-consultas/trabalhos']);
        assert.equal(polls,2);
        assert(await p.locator('.mesa-confirmar').isDisabled());
        offline=true;await p.locator('#oficio-consultar-agora').click();
        await p.waitForFunction(()=>document.getElementById('oficio-consulta-aviso').textContent.includes('Abra o conector'));
        assert.equal(polls,2,'Conector offline não inicia polling interminável');
        await p.locator('#oficio-consulta-acoes details summary').click();
        await p.locator('#oficio-conectar-computador').click();
        await p.locator('#oficio-conector-pareamento').waitFor({state:'visible'});
        assert((await p.locator('#oficio-conector-codigo').inputValue()).startsWith('oficio_pair_'));
        const fila=p.locator('#rotina-fila [data-selecionar-intimacao]');
        await fila.nth(1).click();
        assert.match(await p.locator('.mesa-consulta').textContent(),/não localizado nesta captura/);
        assert.match(await p.locator('.mesa-consulta').textContent(),/não significa arquivamento/);
        await fila.first().click();
        fs.mkdirSync(path.join(root,'.tmp/oficio'),{recursive:true});
        await p.screenshot({path:path.join(root,'.tmp/oficio/mesa-desktop.png'),fullPage:true});
        await p.setViewportSize({width:390,height:844});
        assert(await p.locator('.oficio-consulta-painel > summary').isVisible());
        assert(await p.locator('.mesa-consulta strong').isVisible());
        assert(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+2));
        await p.screenshot({path:path.join(root,'.tmp/oficio/mesa-mobile.png'),fullPage:true});
        temCaptura=false;await p.evaluate(()=>window.recarregar());
        assert.match(await p.locator('#oficio-consulta-aviso').textContent(),/indisponível/);
        assert(!await p.locator('.mesa-consulta').textContent().then(t=>t.includes('186804')),'Falha não mantém status como atual');
        await p.evaluate(()=>window.limpar());
        assert.equal(await p.locator('#oficio-consulta-aviso').textContent(),'');
        assert.equal(await p.locator('#oficio-conector-codigo').inputValue(),'');
        assert.equal(await p.locator('#rotina-fila [data-selecionar-intimacao]').count(),0);
        assert.deepEqual(erros,[]);
        console.log('OK: 257 INs/26 páginas; reset, duplicidade, cartório e filtro recusados; mesa desktop/mobile branca; CSRF; status separado; sem conferência automática; falha e logout limpos.');
    } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
