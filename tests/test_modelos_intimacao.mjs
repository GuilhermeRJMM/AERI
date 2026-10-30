import assert from 'node:assert/strict';
import {proximoOficio,gerarAutuacao,gerarOficio,gerarConvocacao} from '../backend/static/js/intimacao_modelos.js';
import {moedaLiteral,dataValida,pendencias} from '../backend/static/js/intimacao_documentos.js';
assert.equal(proximoOficio('52','2026'),'INT/2026/053');
assert.equal(proximoOficio('INT/2026/099','2026'),'INT/2026/100');
assert.equal(proximoOficio('0','2026'),'INT/2026/001');
for(const s of ['-1','1.5','abc','INT/2025/052','999999'])assert.throws(()=>proximoOficio(s,'2026'));
assert.equal(moedaLiteral('10545.44'),'R$ 10.545,44');
assert.equal(moedaLiteral('10.545,44'),'R$ 10.545,44');
assert.equal(moedaLiteral('10.001'),'');
assert.equal(dataValida('31/02/2026'),false);
const d={in:'IN00000001C',processo:'100100/2026',dataGeracao:'30/10/2026',dataProtocolo:'23/10/2026',
    oficio:'INT/2026/053',protocolo:'123456',matricula:'1.234',registro:'R.6',titulo:'Título literal n.°',contrato:'1.234-0',
    dataTituloAutuacao:'19/10/2026',dataContrato:'16/11/2023',credor:'CREDOR EXEMPLO',cnpj:'00.360.305/0001-04',
    pessoas:[{nome:'PESSOA EXEMPLO',cpf:'11144477735'}],alvo:{nome:'PESSOA EXEMPLO',cpf:'11144477735'},
    enderecoImovel:'Rua A, 1, Centro',enderecos:['Rua B, 2, Centro, Morrinhos-GO'],signatario:'Escrevente Exemplo',
    dataProjecao:'30/10/2026',valorProjecao:'R$ 10.545,44',valorExtenso:'dez mil quinhentos e quarenta e cinco reais e quarenta e quatro centavos',
    selo:'00000000000000000000000',clausula:'26 OUTORGA DE PROCURAÇÕES'};
assert.deepEqual(pendencias(d),[]);
assert(pendencias({...d,selo:''}).includes('selo existente'));
assert.deepEqual(pendencias({...d,selo:'',valorProjecao:''},'autuacao'),[]);
assert(pendencias({...d,selo:''},'oficio').includes('selo existente'));
const aut=gerarAutuacao(d),of=gerarOficio(d),conv=gerarConvocacao(d);
assert(aut.includes('19/10/2026') && !aut.includes('16/11/2023'));
assert(of.includes('16/11/2023') && conv.includes('16/11/2023'));
assert(aut.includes('font-family:Arial') && aut.includes('font-size:18pt'));
for(const html of [aut,of,conv])assert(html.includes('font-family:Arial,sans-serif;font-size:10pt;'));
assert.equal((of.match(/page-break-after:always/g)||[]).length,2);
for(const s of ['CONTRA-FÉ','CERTIDÃO','OBSERVAÇÕES:','30 dias após o término','deixei de intimar pessoalmente'])assert(of.includes(s));
assert(!aut.includes('MANIFESTO') && !of.includes('06364830102'));
assert(gerarAutuacao({...d,credor:'<img src=x onerror=alert(1)>'}).includes('&lt;img'));
assert(!gerarOficio({...d,credorEncerramento:'[PENDENTE: credorEncerramento]'}).includes('[PENDENTE: credorEncerramento]'));
assert(gerarOficio({...d,signatario:''}).includes('Luiz Fernando Ribeiro'));
console.log('Modelos: numeração, redação, datas independentes, estilos e escape conferidos.');
