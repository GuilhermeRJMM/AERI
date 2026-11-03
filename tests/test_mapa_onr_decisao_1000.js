'use strict';
// 1.000 simulações sintéticas, expectativas definidas por categoria, não pelo detector.
// São 250 combinações de redação × 4 formatos. Não representam validação jurídica
// independente nem medem uma taxa de acerto em produção.
const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('fs'),path=require('path'),vm=require('vm');
const root=path.join(__dirname,'../backend/static/mapa_onr/src');
const c=vm.createContext({document:{querySelector:()=>({value:''})}});
for(const m of ['documento','enums','parser','extrator','builder','validator'])vm.runInContext(fs.readFileSync(path.join(root,m+'.js'),'utf8'),c);
vm.runInContext(fs.readFileSync(path.join(root,'app.js'),'utf8').replace("document.addEventListener('DOMContentLoaded', iniciar);",'global.detectorTeste=decisaoJudicialDoTexto;'),c);
const conectores=[
 (x,f)=>`Em cumprimento ${f?'à':'ao'} ${x}`,
 (x,f)=>`Por força ${f?'da':'do'} ${x}`,
 (x,f)=>`Nos termos ${f?'da':'do'} ${x}`,
 (x,f)=>`Em atendimento ${f?'à':'ao'} ${x}`,
 (x,f)=>`Em obediência ${f?'à':'ao'} ${x}`,
 (x,f)=>`Em virtude ${f?'da':'do'} ${x}`,
 (x,f)=>`Em razão ${f?'da':'do'} ${x}`,
 (x)=>`Conforme ${x}`,
 (x,f)=>`Averba-se em cumprimento ${f?'à':'ao'} ${x}`,
 (x,f)=>`Registra-se por força ${f?'da':'do'} ${x}`,
];
const instrumentos=[['mandado judicial',false],['ordem judicial',true],['decisão judicial',true],['sentença judicial',true],['sentença',true]];
const formas=[t=>t,t=>t.toUpperCase(),t=>t.normalize('NFD').replace(/[\u0300-\u036f]/g,''),t=>t.replace(/ /g,'\n  ')];
const casos=[];
function incluir(grupo,base,conclusao,valor){
 for(const [formato,forma] of formas.entries())casos.push({id:casos.length+1,grupo,formato,texto:forma(`Matrícula fictícia nº 9.999. ${base}.`),conclusao,valor});
}
for(const conector of conectores)for(const [instrumento,f] of instrumentos)incluir('judicial',conector(instrumento,f)+', procede-se ao ato atual','JUDICIAL',true);
const documentos=['escritura pública de inventário','escritura pública de partilha','escritura pública de divórcio','escritura pública de separação','escritura pública de compra e venda','escritura pública de doação','escritura pública de permuta','escritura pública de cessão','instrumento particular de financiamento','instrumento particular de alienação fiduciária'];
const bases=['TÍTULO: ','Origem do ato: ','Registra-se com base em ','A pedido das partes, registra-se por ','Nos termos da '];
for(const doc of documentos)for(const base of bases)incluir('extrajudicial',base+doc,'EXTRAJUDICIAL',false);
const marcadores=['Histórico: ','Referência histórica: ','Título anterior: ','Registro anterior: ','Ato anterior: ','Mera menção: ','Simples referência: ','Apenas menciona: ','Descrição histórica: ','Citação do ato anterior: '];
for(const marco of marcadores)for(const [instrumento,f] of instrumentos)incluir('historica',marco+conectores[0](instrumento,f)+'. Ato atual: atualização cadastral','NAO_DECLARADO',null);
const neutros=['atualização de CCIR','inscrição no CAR','averbação de óbito','inventário','anotação de protocolo','retificação de área','código de endereçamento postal','menção ao Processo nº 123','ofício enviado à Vara Cível','alteração do nome da rua'];
const rotulos=['Objeto: ','Anotação: ','Procedimento: ','Registro: ','Atualização: '];
for(const neutro of neutros)for(const rotulo of rotulos)incluir('nao_declarada',rotulo+neutro,'NAO_DECLARADO',null);
const negativas=['Origem: Extrajudicial','Decisão Judicial: Não','Procedimento pela via extrajudicial','Sem necessidade de decisão judicial','Sem decisão judicial'];
for(const conector of conectores)for(const negativa of negativas)incluir('contradicao',conector('mandado judicial',false)+'. '+negativa,'CONTRADICAO',null);
assert.equal(casos.length,1000);assert.equal(new Set(casos.map(x=>x.texto)).size,1000);
for(const caso of casos)test(`simulação ${caso.id}/1000 · ${caso.grupo} · formato ${caso.formato}`,()=>{
 const r=c.detectorTeste(caso.texto);assert.equal(r.conclusao,caso.conclusao,caso.texto);assert.equal(r.valor,caso.valor,caso.texto);
 assert(r.rotulo && !r.rotulo.includes('indicações conflitantes'));
 if(r.valor!==null)assert(r.trecho && r.evidencias.length>=1,'Sim/Não precisam de evidência');
 if(r.conclusao==='CONTRADICAO')assert.equal(r.evidencias.length,2);
});
test('1.000 casos distribuídos igualmente entre cinco grupos',()=>{
 for(const grupo of ['judicial','extrajudicial','historica','nao_declarada','contradicao'])assert.equal(casos.filter(c=>c.grupo===grupo).length,200);
});
test('casos adversariais não usados na composição das 1.000 simulações',()=>{
 const casosRevisao=[
  ['Título: Sentença judicial. Registro.',true,'JUDICIAL'],
  ['Por determinação do MM. Juiz de Direito, procede-se ao registro.',true,'JUDICIAL'],
  ['Origem atual: Extrajudicial.',false,'EXTRAJUDICIAL'],
  ['Origem do título: Judicial.',true,'JUDICIAL'],
  ['Decisão judicial: NÃO INFORMADO.',null,'NAO_DECLARADO'],
  ['Decisão judicial: não consta.',null,'NAO_DECLARADO'],
  ['Decisão judicial: não se sabe.',null,'NAO_DECLARADO'],
  ['Não foi expedido mandado judicial pelo Juízo.',null,'NAO_DECLARADO'],
  ['Mandado judicial não expedido pelo Juízo.',null,'NAO_DECLARADO'],
  ['Em cumprimento ao mandado judicial revogado.',null,'NAO_DECLARADO'],
  ['Em cumprimento à ordem judicial, tornada sem efeito.',null,'NAO_DECLARADO'],
  ['Não foi realizado pela via extrajudicial.',null,'NAO_DECLARADO'],
  ['Não houve pagamento. Em cumprimento ao mandado judicial, registro.',true,'JUDICIAL'],
  ['Escritura pública de inventário, por determinação do Juízo da comarca.',true,'JUDICIAL'],
  ['Histórico: Origem: Judicial. Ato atual: Origem: Extrajudicial.',false,'EXTRAJUDICIAL'],
  ['Atualização cadastral. Referência ao R.12: carta de sentença extraída dos autos do Juízo Cível.',null,'NAO_DECLARADO'],
  ['Carta de sentença expedida pelo Juiz de Direito.',true,'JUDICIAL'],
  ['Inventário; menciona processo e sentença. Atualização de endereço.',null,'NAO_DECLARADO'],
  ['Escritura pública de compra e venda. Processo mencionado para referência.',false,'EXTRAJUDICIAL'],
  ['Em cumprimento ao mandado judi-\ncial, registra-se.',true,'JUDICIAL'],
 ];
 for(const [texto,valor,conclusao] of casosRevisao){const r=c.detectorTeste(texto);assert.equal(r.valor,valor,texto);assert.equal(r.conclusao,conclusao,texto);}
});
