import assert from 'node:assert/strict';
import {temNovidadeRtd, ordenarNovidadesRtd, resumoRtd, detalhesRtd} from '../backend/static/js/rtd_intimacoes.js';

const antigo = {rtd:[{novo:false,alteradoEm:'2026-10-01T10:00:00Z'}]};
const evento = {
    anterior:{Situacao:'Orçamento', ValorOrcamento:100, DataSituacao:'2026-10-01'},
    atual:{Situacao:'Aguardando pagamento', ValorOrcamento:125, DataSituacao:'2026-10-02'},
    criado_em:'2026-10-02T12:30:00Z',
};
const novo = {id:'1',rtd:[{
    novo:true,
    alteradoEm:'2026-10-02T12:30:00Z',
    consultadoEm:'2026-10-02T12:31:00Z',
    protocolo:'12345678901234567',
    situacao:'Aguardando pagamento',
    dados:{Situacao:'Aguardando pagamento',ValorOrcamento:125},
    versao:2,
    eventos:[evento],
}]};

assert.equal(temNovidadeRtd(novo), true);
assert.equal(temNovidadeRtd({}), false);
assert.ok(ordenarNovidadesRtd(novo,antigo)<0);
assert.ok(ordenarNovidadesRtd(novo,{rtd:[{novo:true,alteradoEm:'2026-10-01T08:00:00Z'}]})<0);
assert.ok(resumoRtd(novo).includes('Atualização para conferir'));
assert.ok(resumoRtd(novo).includes('Situação: Orçamento'));
assert.ok(!resumoRtd(novo).includes('<script>'));
assert.ok(!detalhesRtd(novo).includes('<script>'));
assert.ok(detalhesRtd(novo).includes('Orçamento'));
assert.ok(detalhesRtd(novo).includes('Aguardando pagamento'));
assert.ok(detalhesRtd(novo).includes('data-versao="2"'));
assert.ok(detalhesRtd(novo).includes('não altera a fase'));
assert.equal(detalhesRtd({}), '');
assert.ok(resumoRtd({}).includes('Sem protocolo RTD vinculado'));
const malicioso = {rtd:[{novo:true,protocolo:'<script>',situacao:'<img>',versao:1,eventos:[]}]};
assert.ok(resumoRtd(malicioso).includes('&lt;script&gt;'));
assert.ok(!detalhesRtd(malicioso).includes('<script>'));
assert.ok(!detalhesRtd(malicioso).includes('<img>'));

console.log('RTD frontend: verificações de destaque, separação e comparação aprovadas.');
