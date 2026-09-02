import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const codigo = readFileSync(new URL('../backend/static/js/api.js', import.meta.url), 'utf8')
    .replace(/export\s+(?=(?:async\s+)?function)/g, '');

test('cliente da API devolve Blob sem tentar interpretar PDF como texto', async () => {
    const contexto = vm.createContext({
        Blob, Headers, Response,
        window:{dispatchEvent(){}},
        fetch:async () => new Response(new Blob(['%PDF-1.7'], {type:'application/pdf'}), {
            status:200, headers:{'Content-Type':'application/pdf'},
        }),
    });
    vm.runInContext(codigo, contexto);
    const arquivo = await vm.runInContext("requisicaoAeri('/api/teste', {resposta:'blob'})", contexto);
    assert.equal(arquivo.type, 'application/pdf');
    assert.equal(await arquivo.text(), '%PDF-1.7');
});
