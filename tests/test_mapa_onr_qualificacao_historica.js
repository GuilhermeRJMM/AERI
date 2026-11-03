'use strict';
const {test}=require('node:test');const assert=require('node:assert/strict');
const fs=require('fs'),vm=require('vm'),path=require('path');
const raiz=path.join(__dirname,'../backend/static/mapa_onr/src');
function carregar(blocos){
 const texto=blocos.join('\n----------------------------------------------------------------------------\n');
 const c=vm.createContext({document:{querySelector:s=>({value:({'#texto':texto,'#tipo-imovel':'rural','#cns':'026187','#municipio':'Morrinhos'})[s]||''})}});
 for(const m of ['documento','enums','parser','extrator','builder','validator'])vm.runInContext(fs.readFileSync(path.join(raiz,m+'.js'),'utf8'),c);
 vm.runInContext(fs.readFileSync(path.join(raiz,'app.js'),'utf8').replace("document.addEventListener('DOMContentLoaded', iniciar);",'render=function(){};global.teste={lerMatricula,estado,qualificarPartesDoAto,pendenciasDeConferencia,decisaoJudicialDoTexto};'),c);
 c.teste.lerMatricula();return c;
}
const primeiro='R.01-1234 - Morrinhos, 01 de janeiro de 2020. Devedor: Carlos Teste da Silva, portador do CPF nº 111.444.777-35, brasileiro, casado sob o regime da comunhão universal de bens com Maria Teste Ribeiro. Credor: BANCO EXEMPLO.';
const esposa='R.02-1234 - Morrinhos, 02 de janeiro de 2020. Devedor: Maria Teste Ribeiro, brasileira, casada sob o regime da comunhão universal de bens, CPF nº 123.456.789-00. Credor: BANCO EXEMPLO.';
const referencia='R.20-1234 - Morrinhos, 12 de agosto de 2021. Devedores: Carlos Teste da Silva e sua mulher Maria Teste Ribeiro, já qualificados e Pedro Teste de Souza, brasileiro, solteiro, maior, CPF nº 987.654.321-00. Credor: BANCO EXEMPLO. Título: Cédula Rural Hipotecária.';
const ficha=(c,n)=>c.teste.estado.fichasAto[n];
test('recupera casal já qualificado, sem atribuir seu casamento ao solteiro',()=>{
 const c=carregar([primeiro,esposa,referencia]);const ps=ficha(c,'20').pessoas;
 assert.equal(ps.length,3);
 for(const nome of ['Carlos Teste da Silva','Maria Teste Ribeiro']){const p=ps.find(p=>p.nome_completo===nome);assert.equal(p.regime_bens,2);assert.equal(p.estado_civil,2);assert.match(p.herdado,/qualificação do ato R\.0[12]/);assert.equal(p.relacao_juridica,8);}
 const p=ps.find(p=>p.nome_completo==='Pedro Teste de Souza');assert.equal(p.estado_civil,1);assert.equal(p.regime_bens,null);
});
test('decisão judicial detectada somente por indicação expressa e com evidência',()=>{
 const c=carregar([]),detectar=c.teste.decisaoJudicialDoTexto;
 for(const t of ['Em cumprimento ao mandado judicial, procede-se à averbação.',
   'Nos termos da sentença judicial, procede-se ao registro.',
   'Formal de Partilha extraído dos autos do inventário, julgado por sentença.',
   'Mandado expedido pelo Juízo da Vara Cível.',
   'Carta de arrematação emitida pela Vara Cível.',
   'Decisão Judicial: Sim. Averbação.', 'Origem: Judicial. Registro.']){
   const r=detectar(t);assert.equal(r?.valor,true,t);assert(r.trecho && r.rotulo);
 }
 for(const t of ['Origem: Extrajudicial.','Procedimento pela via extrajudicial.',
   'Escritura pública de inventário e partilha.','Decisão Judicial: Não.','Sem necessidade de decisão judicial.'])assert.equal(detectar(t)?.valor,false,t);
 for(const t of ['INVENTÁRIO. Averbação de óbito.','Processo nº 123. Referência ao Juízo.',
   'Nos termos do contrato, procede-se ao registro.',
   'Mera menção: em cumprimento ao mandado judicial no ato anterior.',
   'Não foi realizado em cumprimento ao mandado judicial.',
   'Decisão Judicial: Sim. Origem: Extrajudicial.'])assert.equal(detectar(t)?.valor ?? null,null,t);
 const atos=carregar(['R.01-1234 - Morrinhos, 01 de janeiro de 2020. Em cumprimento ao mandado judicial, registro.',
   'AV.02-1234 - Morrinhos, 02 de janeiro de 2020. Atualização cadastral.']);
 assert.equal(ficha(atos,'01').decisao_jud,true);assert.equal(ficha(atos,'02').decisao_jud,null,'não herdar decisão de outro ato');
});
test('retoma qualificação acima qualificada e corrige uma letra só com casal anterior confirmado',()=>{
 const c=carregar([primeiro,esposa,referencia.replace('Carlos Teste','Carllos Teste').replace('já qualificados','acima qualificados')]);
 const p=ficha(c,'20').pessoas.find(p=>p.nome_completo==='Carlos Teste da Silva');assert(p);assert.match(p.herdado,/grafia divergente/);
 const semEsposa=carregar([primeiro,referencia.replace('Carlos Teste','Carllos Teste')]);
 assert(!ficha(semEsposa,'20').pessoas.some(p=>p.nome_completo==='Carlos Teste da Silva'));
});
test('não herda regime de ato futuro e respeita mudança de estado civil',()=>{
 const antes=primeiro.replace('sob o regime da comunhão universal de bens com Maria Teste Ribeiro','');
 const depois='R.02-1234 - Morrinhos, 02 de janeiro de 2022. Devedor: Carlos Teste da Silva, casado sob o regime da comunhão universal de bens, CPF nº 111.444.777-35.';
 const divorcio='R.03-1234 - Morrinhos, 03 de janeiro de 2023. Devedor: Carlos Teste da Silva, divorciado, CPF nº 111.444.777-35. Credor: BANCO EXEMPLO.';
 const repetido='R.04-1234 - Morrinhos, 04 de janeiro de 2024. Devedor: Carlos Teste da Silva, já qualificado. Credor: BANCO EXEMPLO.';
 const c=carregar([antes,depois,divorcio,repetido]);
 assert.notEqual(ficha(c,'01').pessoas[0].regime_bens,2);
 assert.equal(ficha(c,'02').pessoas[0].regime_bens,2);
 for(const n of ['03','04']){const p=ficha(c,n).pessoas[0];assert.equal(p.estado_civil,4);assert.equal(p.regime_bens,null);}
});
test('homônimo com documentos diferentes e pessoa apenas mencionada não são recuperados',()=>{
 const outro=primeiro.replace('R.01','R.02').replace('111.444.777-35','222.333.444-05');
 const ref='R.03-1234 - Morrinhos, 03 de janeiro de 2024. Devedor: Carlos Teste da Silva, já qualificado. Credor: BANCO EXEMPLO.';
 assert.equal(ficha(carregar([primeiro,outro,ref]),'03').pessoas.length,0);
 const mencao='R.03-1234 - Morrinhos, 03 de janeiro de 2024. Objeto: confronta com Carlos Teste da Silva, já qualificado.';
 assert.equal(ficha(carregar([primeiro,mencao]),'03').pessoas.length,0);
});
test('novo casamento não recebe regime declarado para o casamento anterior',()=>{
 const novas='R.02-1234 - Morrinhos, 02 de janeiro de 2024. Devedor: Carlos Teste da Silva, CPF nº 111.444.777-35, casado em segundas núpcias. Credor: BANCO EXEMPLO.';
 const p=ficha(carregar([primeiro,novas]),'02').pessoas[0];assert.notEqual(p.regime_bens,2);assert(!/regime de bens/.test(p.herdado || ''));
});
test('CPF explícito divergente não recebe documento de uma pessoa anterior',()=>{
 const c=carregar([primeiro,referencia.replace('Carlos Teste da Silva','Carlos Teste da Silva, CPF nº 222.333.444-05,')]);
 assert(!ficha(c,'20').pessoas.some(p=>p.cpf_cnpj==='11144477735'));
});
test('Decisão Judicial é independente por ato, booleana e compatível com a versão',()=>{
 const c=carregar([primeiro,esposa]);assert.equal(ficha(c,'01').decisao_jud,null);assert.equal(ficha(c,'02').decisao_jud,null);
 const b=c.ONR_BUILDER;
 const a=b.montaImovel({numero_matricula:'1234',decisao_jud:true},{tipo:'rural',versao:'1.3.0'});assert.equal(a.imovel.decisao_jud,true);
 const nao=b.montaImovel({numero_matricula:'1234',decisao_jud:false},{tipo:'rural',versao:'1.3.0'});assert.equal(nao.imovel.decisao_jud,false);assert(nao.pendencias.length>0);
 const legado=b.montaImovel({numero_matricula:'1234',decisao_jud:true},{tipo:'rural',versao:'1.2.0'});assert(legado.pendencias.some(p=>p.campo==='decisao_jud'));
 assert.equal(c.teste.pendenciasDeConferencia({arquivo:{imoveis:[legado.imovel]},relatorio:[{ato:'R.01',pendencias:[{campo:'decisao_jud',motivo:'Versão incompatível'}]}]}).length,0,'Incompatibilidade de versão não pode ser ignorada como conferência');
});
