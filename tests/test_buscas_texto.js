'use strict';
// Exercita os handlers reais com dados sintéticos, sem rede ou área de transferência real.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const codigo = fs.readFileSync(path.join(__dirname, '../backend/static/js/buscas.js'), 'utf8')
    .replace(/^import .*;\r?\n/gm, '').replace(/export /g, '');

function ambiente() {
    const campos = new Map(), chamadas = [], copias = [];
    class Elemento {
        constructor() { this.value = ''; this.children = []; this.textContent = ''; this.hidden = false; this.disabled = false; this.style = {}; }
        setAttribute() {}
        appendChild(e) { this.children.push(e); return e; }
        append(...e) { this.children.push(...e); }
        replaceChildren() { this.children = []; }
        remove() { if (this.id) campos.delete(this.id); }
        insertAdjacentElement(_, e) { campos.set(e.id, e); }
        focus() {}
        select() {}
    }
    const campo = id => { if (!campos.has(id)) campos.set(id, new Elemento()); return campos.get(id); };
    campo('btn-buscas-texto').textContent = 'Gerar texto';
    const ctx = vm.createContext({
        document:{getElementById:id => id === 'buscas-texto-fallback' ? campos.get(id) : campo(id),
            createElement:() => new Elemento(), body:new Elemento(), createRange:()=>({selectNodeContents(){}}),
            execCommand:() => { if (ctx.bloquearCopia) return false; copias.push('formatada'); return true; }},
        window:{getSelection:()=>({removeAllRanges(){},addRange(){}}),setTimeout:()=>0}, navigator:{},
        URLSearchParams, Intl, Blob, console,
        escaparHtml:s => String(s).replaceAll('<', '&lt;'), mostrarPagina:()=>{},
        requisicaoAeri:async (url, opcoes) => { chamadas.push({url, opcoes}); return ctx.responder(url, opcoes); },
    });
    ctx.responder = () => ({itens:[{matricula:37404,nome:'Eduardo Costa da Nobrega', documento:'***.***.578-50',situacao:'ATIVA'}]});
    vm.runInContext(codigo + '\nthis.api = {gerarTextoPesquisa, pesquisar, montarTextoPesquisa, parametrosPesquisa, estado:()=>textoPreparado, definir:(dados)=>{buscaAtual=dados;}, invalidar:()=>{geracaoPesquisa++;textoPreparado=null;}};', ctx);
    ctx.api.definir({termo:'Eduardo da Costa Nobrega',pagina:1});
    return {ctx, campo, chamadas, copias};
}

test('prepara a pesquisa validada e copia a matrícula do vídeo', async () => {
    const {ctx, campo, chamadas, copias} = ambiente();
    await ctx.api.gerarTextoPesquisa();
    assert.equal(chamadas[0].url, '/api/buscas/preparar-texto');
    assert.equal(chamadas[0].opcoes.method, 'POST');
    assert.equal(JSON.parse(chamadas[0].opcoes.body).nome, 'Eduardo da Costa Nobrega');
    assert.ok(ctx.api.estado().texto.includes('37.404'));
    assert.ok(ctx.api.estado().texto.includes('Foi encontrado 1 (um) imóvel'));
    assert.equal(copias.length, 1);
    assert.equal(campo('btn-buscas-texto').textContent, 'Copiar texto');
});

test('segundo clique copia sem aguardar outra consulta', async () => {
    const {ctx, chamadas, copias} = ambiente();
    ctx.bloquearCopia = true;
    await ctx.api.gerarTextoPesquisa();
    assert.equal(chamadas.length, 1);
    assert.ok(ctx.document.getElementById('buscas-texto-fallback'));
    ctx.bloquearCopia = false;
    await ctx.api.gerarTextoPesquisa();
    assert.equal(chamadas.length, 1);
    assert.equal(copias.length, 1);
    assert.equal(ctx.document.getElementById('buscas-texto-fallback'), undefined);
});

test('erro de conferência é mostrado e nunca copia ou gera negativa', async () => {
    const {ctx, campo, copias} = ambiente();
    ctx.responder = () => { throw new Error('Há correspondências que precisam de conferência.'); };
    await ctx.api.gerarTextoPesquisa();
    assert.match(campo('buscas-texto-aviso').textContent, /precisam de conferência/);
    assert.equal(copias.length, 0);
    assert.equal(ctx.api.estado(), null);
    assert.equal(campo('btn-buscas-texto').disabled, false);
});

test('trocar de pesquisa durante geração descarta resposta antiga', async () => {
    const {ctx, copias} = ambiente();
    let liberar;
    ctx.responder = () => new Promise(resolve => { liberar = resolve; });
    const gerando = ctx.api.gerarTextoPesquisa();
    ctx.api.invalidar();
    ctx.api.definir({termo:'Outra Pessoa',pagina:1});
    liberar({itens:[{matricula:37404,situacao:'ATIVA'}]});
    await gerando;
    assert.equal(copias.length, 0);
    assert.equal(ctx.api.estado(), null);
});

test('não inclui matrícula encerrada e deduplica imóveis', () => {
    const {ctx} = ambiente();
    const resultado = ctx.api.montarTextoPesquisa('Pessoa', [
        {matricula:10,situacao:'ATIVA'}, {matricula:10,situacao:'ATIVA'},
        {matricula:11,situacao:'ENCERRADA'},
    ]);
    assert.equal(resultado.matriculas.length, 1);
    assert.match(resultado.texto, /Foi encontrado 1 \(um\) imóvel/);
    assert.deepEqual(Array.from(resultado.descartadas.ENCERRADA), [11]);
});
