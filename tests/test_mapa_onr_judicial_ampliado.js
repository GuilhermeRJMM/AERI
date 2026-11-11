'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('fs'),path=require('path'),vm=require('vm');
const root=path.join(__dirname,'../backend/static/mapa_onr/src');
const c=vm.createContext({document:{querySelector:()=>({value:''})}});
for(const m of ['documento','enums','parser','extrator','builder','validator'])vm.runInContext(fs.readFileSync(path.join(root,m+'.js'),'utf8'),c);
vm.runInContext(fs.readFileSync(path.join(root,'app.js'),'utf8').replace("document.addEventListener('DOMContentLoaded', iniciar);",'global.detectorTeste=decisaoJudicialDoTexto;'),c);
// Expectativas independentes da implementação; somente dados fictícios.
const positivos=[
 'TÍTULO: Formal de Partilha. Juízo da 1ª Vara Cível. Sentença de homologação transitada em julgado.',
 'Em cumprimento ao alvará judicial expedido pelo Juízo da Vara de Família, procede-se ao ato.',
 'Nos termos do acórdão do Tribunal de Justiça, procede-se ao cancelamento do registro.',
 'Carta de alienação por iniciativa particular expedida pelo Juízo da execução.',
 'Auto de arrematação lavrado nos autos da execução perante o Juízo da Vara Cível.',
 'Termo de penhora extraído dos autos da execução do Juízo da Vara Cível.',
 'Carta precatória expedida pelo Juízo de Direito para registro da penhora.',
 'Em cumprimento à decisão interlocutória proferida pelo Juízo, registra-se a constrição.',
 'Em cumprimento à tutela provisória deferida pelo Juízo da Vara Cível, averba-se a ordem.',
 'Por força da sentença homologatória, averba-se a partilha judicial.',
 'Nos termos da decisão do Juízo da Vara de Família, averba-se o divórcio.',
 'Nos termos da ordem do MM. Juiz de Direito, cancela-se a hipoteca.',
 'Título: Carta de sentença. Expedida pelo Tribunal de Justiça nos autos do processo fictício.',
 'Mandado de imissão na posse expedido pelo Juízo da Vara Cível.',
 'Mandado de usucapião expedido pelo Juízo de Direito.',
 'Mandado de adjudicação compulsória expedido pelo Juízo da Vara Cível.',
 'Mandado de desapropriação expedido pelo Juízo Federal.',
 'Mandado de arresto expedido pelo Juízo de Direito.',
 'Mandado de sequestro expedido pelo Juízo Federal.',
 'Mandado de registro da servidão expedido pelo Juízo da Vara Cível.',
 'Carta rogatória com exequatur concedido pelo Superior Tribunal de Justiça, para averbação.',
 'Em cumprimento à ordem judicial, cancela-se a penhora do R.05.',
 'Título: sentença judicial de interdição, para averbação.',
 'Hipoteca judiciária constituída com base na sentença condenatória proferida pelo Juízo da Vara Cível.',
 'Certidão de sentença condenatória expedida pelo Juízo para registro da hipoteca judiciária.',
 'Formal de partilha homologado judicialmente pelo Juízo da Vara de Família.',
];
const negativos=[
 ['Conforme sentença arbitral, registra-se o título.',null],
 ['Em cumprimento à sentença arbitral proferida pela Câmara de Arbitragem.',null],
 ['Título: sentença arbitral. Referência a processo judicial.',null],
 ['Certidão de ajuizamento da execução expedida pelo Juízo, artigo 828 do CPC.',null],
 ['Ofício expedido pela Vara Cível solicitando informações sobre o imóvel.',null],
 ['Protocolo de pedido de alvará judicial ainda pendente de decisão.',null],
 ['Em cumprimento ao alvará judicial revogado, pretende-se registrar.',null],
 ['Nos termos do acórdão do Tribunal de Justiça, tornado sem efeito.',null],
 ['Não foi expedida carta de alienação por iniciativa particular pelo Juízo.',null],
 ['Termo de penhora não expedido pelo Juízo da execução.',null],
 ['Título anterior: formal de partilha homologado judicialmente pelo Juízo. Ato atual: atualização do CCIR.',null],
 ['Histórico: Nos termos do acórdão do Tribunal de Justiça. Ato atual: alteração de endereço.',null],
 ['Atualização cadastral. Referência ao R.12: auto de arrematação lavrado nos autos perante o Juízo.',null],
 ['Escritura pública de inventário autorizada por alvará judicial.',false],
 ['Escritura pública de compra e venda autorizada por alvará judicial.',false],
 ['Inventário extrajudicial. Referência à sentença do registro anterior.',null],
 ['Usucapião extrajudicial processada no registro de imóveis.',null],
 ['Adjudicação compulsória extrajudicial requerida pelas partes.',null],
 ['Hipoteca convencional constituída por escritura pública.',null],
 ['CNIB: consulta de indisponibilidade, sem indicação da origem da ordem.',null],
 ['Registro de formal de partilha sem indicação do título de origem.',null],
 ['Carta de adjudicação extrajudicial, sem sentença ou mandado.',null],
 ['Averbação de óbito. Não há informação sobre decisão judicial.',null],
 ['Escritura pública de divórcio. Histórico: em cumprimento à sentença judicial.',false],
 ['Carta precatória emitida pelo Juízo, posteriormente revogada.',null],
 ['Nos termos do acórdão do Tribunal de Justiça que foi revogado, solicita-se a alteração cadastral.',null],
 ['Histórico da matrícula. Formal de partilha. Juízo da 1ª Vara Cível. Sentença de homologação. O ato atual é atualização do CCIR.',null],
 ['Histórico: carta precatória emitida pelo Juízo. Ato atual: Origem: Extrajudicial.',false],
 ['Auto de arrematação extrajudicial lavrado pelo leiloeiro, sem homologação pelo Juízo.',null],
 ['Auto de arrematação lavrado pelo leiloeiro em execução extrajudicial, sem ordem do Juízo.',null],
 ['Carta precatória expedida pelo Juízo para prestar informações sobre o imóvel, sem ordem de registro.',null],
 ['Carta precatória expedida pelo Juízo para solicitar informações sobre o imóvel.',null],
];
const formas=[s=>s,s=>s.toUpperCase(),s=>s.normalize('NFD').replace(/[\u0300-\u036f]/g,''),s=>s.replace(/ /g,'\n  ')];
for(const [i,texto] of positivos.entries())for(const [j,forma] of formas.entries())test(`novo judicial ${i+1}, formato ${j}`,()=>{
 const r=c.detectorTeste(forma(texto));assert.equal(r.valor,true,texto);assert(r.trecho,'Exibir evidência da decisão');
});
for(const [i,[texto,valor]] of negativos.entries())for(const [j,forma] of formas.entries())test(`proteção ${i+1}, formato ${j}`,()=>{
 assert.equal(c.detectorTeste(forma(texto)).valor,valor,texto);
});
