// Executar com Node + Playwright e Chrome instalado. Dados sintéticos apenas.
const {chromium} = require('playwright');
const fs = require('fs');
const path = require('path');
const assert = require('assert/strict');
const root = path.resolve(__dirname, '..');

(async () => {
    const browser = await chromium.launch({channel: 'chrome', headless: true});
    try {
        const page = await browser.newPage({viewport: {width: 1280, height: 900}});
        page.on('pageerror', erro => console.error('Erro JavaScript:', erro.message));
        const estado = {status: 200, origem: 'HUB', logouts: 0};
        await page.addInitScript(() => {
            window.__avisosHub = [];
            window.chrome = window.chrome || {};
            window.chrome.webview = {postMessage: aviso => window.__avisosHub.push(aviso)};
        });
        await page.route('**/*', async route => {
            const url = new URL(route.request().url());
            if (url.hostname !== 'aeri-teste.invalid') return route.abort();
            if (url.pathname === '/') {
                let html = fs.readFileSync(path.join(root, 'backend/templates/index.html'), 'utf8');
                html = html.replace(/\{%\s*include\s+['"]painel.html['"]\s*%\}/g,
                    () => fs.readFileSync(path.join(root, 'backend/templates/painel.html'), 'utf8'));
                html = html.replace(/<script type="module" src="\/static\/js\/app.js[^\"]*"><\/script>/,
                    `<script type="module">import {iniciarAutenticacao} from '/static/js/autenticacao.js';
                    document.getElementById('splash-aeri').remove();document.body.classList.remove('splash-active');iniciarAutenticacao();</script>`);
                return route.fulfill({contentType: 'text/html; charset=utf-8', body: html});
            }
            if (url.pathname === '/api/sessao') return route.fulfill({status: estado.status,
                contentType: 'application/json', body: JSON.stringify(estado.status === 200 ? {
                    usuario: 'SINTETICO', nome: 'Pessoa Teste', perfil: 'USUARIO',
                    csrfToken: 'csrf-sintetico', permissoes: {}, origemAutenticacao: estado.origem,
                } : {detail: 'Faça login para continuar.'})});
            if (url.pathname === '/api/logout') {
                estado.logouts++;
                return route.fulfill({status: 204, body: ''});
            }
            if (url.pathname.startsWith('/static/')) {
                const arquivo = path.resolve(root, 'backend', '.' + decodeURIComponent(url.pathname));
                if (!arquivo.startsWith(path.join(root, 'backend/static') + path.sep) || !fs.existsSync(arquivo)) return route.abort();
                const tipo = arquivo.endsWith('.js') ? 'text/javascript' : arquivo.endsWith('.css') ? 'text/css' : arquivo.endsWith('.svg') ? 'image/svg+xml' : 'image/png';
                return route.fulfill({contentType: tipo, body: fs.readFileSync(arquivo)});
            }
            return route.abort();
        });
        await page.goto('https://aeri-teste.invalid/');
        await page.waitForFunction(() => !document.body.classList.contains('auth-pending'));
        assert(await page.locator('#btn-sair').isHidden());
        assert(await page.locator('#btn-minha-senha').isHidden());
        estado.status = 401;
        await page.evaluate(() => window.dispatchEvent(new CustomEvent('aeri:sessao-expirada')));
        await page.locator('#login-hub').waitFor({state: 'visible'});
        assert(await page.locator('#form-login').isHidden());
        assert(await page.evaluate(() => window.__avisosHub.some(a => a.type === 'aeri:reauth-required')));
        await page.waitForFunction(() => getComputedStyle(document.getElementById('login-aeri')).opacity === '1');
        await page.screenshot({path: process.env.AERI_QA_SCREENSHOT || path.join(require('os').tmpdir(), 'aeri-sessao-hub.png')});
        await page.reload();
        await page.locator('#login-hub').waitFor({state: 'visible'});
        assert(await page.locator('#form-login').isHidden());
        assert(await page.evaluate(() => document.body.classList.contains('auth-pending')));
        estado.status = 200;
        await page.locator('#btn-verificar-acesso-hub').click();
        await page.waitForFunction(() => !document.body.classList.contains('auth-pending'));
        assert(await page.locator('#btn-sair').isHidden());
        estado.origem = 'LOCAL';
        await page.reload();
        await page.waitForFunction(() => !document.body.classList.contains('auth-pending'));
        assert(await page.locator('#btn-sair').isVisible());
        assert(await page.locator('#btn-minha-senha').isVisible());
        await page.locator('#btn-sair').click();
        await page.locator('#form-login').waitFor({state: 'visible'});
        assert(await page.locator('#login-hub').isHidden());
        assert.equal(estado.logouts, 1);
        console.log('OK: HUB, expiração, recarga, renovação externa e logout local; preferência visual não autentica.');
    } finally { await browser.close(); }
})().catch(erro => {console.error(erro); process.exitCode = 1;});
