import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {temNovidadeRtd, ordenarNovidadesRtd, resumoRtd, detalhesRtd} from '../backend/static/js/rtd_intimacoes.js';

const telaIntimacoes = readFileSync(new URL('../backend/static/js/intimacoes.js', import.meta.url), 'utf8');

const antigo = {rtd:[{novo:false,alteradoEm:'2026-10-01T10:00:00Z'}]};
const evento = {
    anterior:{Situacao:'Orçamento', ValorOrcamento:100, DataSituacao:'2026-10-01'},
    atual:{Situacao:'Aguardando pagamento', ValorOrcamento:125, DataSituacao:'2026-10-02'},
    criado_em:'2026-10-02T12:30:00Z',
};
const novo = {id:'1',fase:'INTIMACAO',rtd:[{
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
const editalComAtualizacao = {...novo, fase:'EDITAL'};
const consolidacaoComAtualizacao = {...novo, fase:'CONSOLIDACAO'};
assert.equal(temNovidadeRtd(editalComAtualizacao), false);
assert.equal(temNovidadeRtd(consolidacaoComAtualizacao), false);
assert.equal(resumoRtd(editalComAtualizacao), '');
assert.equal(detalhesRtd(consolidacaoComAtualizacao), '');
assert.ok(ordenarNovidadesRtd(novo,antigo)<0);
assert.ok(ordenarNovidadesRtd(novo,{rtd:[{novo:true,alteradoEm:'2026-10-01T08:00:00Z'}]})<0);
assert.ok(resumoRtd(novo).includes('Atualização para conferir'));
assert.ok(resumoRtd({...antigo, protocoloRtd:'20260708155369985'}).includes('RTD 20260708155369985'));
assert.ok(resumoRtd({...antigo, protocoloRtd:'20260708155369985'}).includes('Protocolo informado no cadastro do IN'));
assert.ok(resumoRtd(novo).includes('Situação: Orçamento'));
assert.ok(!resumoRtd(novo).includes('<script>'));
assert.ok(!detalhesRtd(novo).includes('<script>'));
assert.ok(detalhesRtd(novo).includes('Orçamento'));
assert.ok(detalhesRtd(novo).includes('Aguardando pagamento'));
assert.ok(detalhesRtd(novo).includes('data-versao="2"'));
assert.ok(detalhesRtd(novo).includes('não altera a fase'));
assert.ok(detalhesRtd(novo).includes('Ver arquivos'));
assert.ok(detalhesRtd(novo).includes('data-acao="rtd-documentos"'));
assert.ok(detalhesRtd(novo).includes('Arquivos do RTD'));
assert.ok(!detalhesRtd(novo).includes('Buscar documentos'));
assert.equal(detalhesRtd({}), '');
assert.ok(resumoRtd({}).includes('Sem protocolo RTD vinculado'));
assert.match(telaIntimacoes, /rotina-fila-protocolo-rtd/);
assert.match(telaIntimacoes, /item\.fase === 'INTIMACAO'.*?Protocolos RTD vinculados a este IN/s);
assert.match(telaIntimacoes, /Protocolo\$\{protocolosRtd\.length === 1/);
const malicioso = {rtd:[{novo:true,protocolo:'<script>',situacao:'<img>',versao:1,eventos:[]}]};
assert.ok(resumoRtd(malicioso).includes('&lt;script&gt;'));
assert.ok(!detalhesRtd(malicioso).includes('<script>'));
assert.ok(!detalhesRtd(malicioso).includes('<img>'));
assert.match(telaIntimacoes, /method:'PUT', body:arquivo, signal:controlador\.signal/);
assert.doesNotMatch(telaIntimacoes, /method:'PUT', headers:\s*\{\s*'Content-Type':'application\/pdf'/);
assert.ok(telaIntimacoes.includes('A conexão falhou ao ${etapaExtracao}.'));
assert.ok(telaIntimacoes.includes('O PDF já foi guardado e será anexado quando você confirmar o envio ao RTD.'));
assert.ok(telaIntimacoes.includes('btn-repetir-envio-pdf-rtd'));
assert.doesNotMatch(telaIntimacoes, /arquivoInput\.value\s*=\s*'';\s*\}\s*if\s*\(versao\s*===\s*versaoExtracaoRtd/);

console.log('RTD frontend: verificações de destaque, separação e comparação aprovadas.');
