import {requisicaoAeri} from './api.js?v=20260902-arquivo-v1';
import {escaparHtml} from './util.js';
import {gerarAutuacao, gerarOficio, gerarConvocacao, proximoOficio} from './intimacao_modelos.js?v=20261030-v1';
export {gerarAutuacao, gerarOficio, gerarConvocacao, proximoOficio};

const FLUXO='tres-anexos-20261030';
const PAPEIS=['recibo','oficio','projecao'];
const ROTULOS={autuacao:'Autuação',oficio:'Ofício Contrafé',convocacao:'Convocação'};
const GERADORES={autuacao:gerarAutuacao,oficio:gerarOficio,convocacao:gerarConvocacao};
let atual=null, leitura=null, geracao=0, ocupado=false, origem='manual', trabalho=null, controlador=null;
const rascunhos=new Map();
const el=id=>document.getElementById(id);
const campo=id=>el(`doc-int-${id}`);
const valor=id=>campo(id).value.trim();
const digitos=s=>String(s || '').replace(/\D/g,'');
const esc=s=>escaparHtml(String(s ?? ''));
const status=s=>{el('documentos-intimacao-status').textContent=s;};
const hashTexto=async texto=>[...new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(texto)))].map(v=>v.toString(16).padStart(2,'0')).join('');

export function dataValida(v) {
    const m=String(v || '').match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
    if(!m)return false;
    const d=new Date(Date.UTC(+m[3],+m[2]-1,+m[1]));
    return d.getUTCFullYear()===+m[3] && d.getUTCMonth()===+m[2]-1 && d.getUTCDate()===+m[1];
}
const dataBr=v=>String(v).split('-').reverse().join('/');
const pontos=v=>digitos(v).replace(/\B(?=(\d{3})+(?!\d))/g,'.');
export function moedaLiteral(v) {
    const s=String(v || '').replace(/^R\$\s*/,'').trim();
    if(!/^(?:\d+|\d{1,3}(?:\.\d{3})+),\d{2}$/.test(s) && !/^\d+\.\d{2}$/.test(s))return '';
    const [inteiro,centavos]=s.includes(',')?s.replace(/\./g,'').split(','):s.split('.');
    return `R$ ${inteiro.replace(/\B(?=(\d{3})+(?!\d))/g,'.')},${centavos}`;
}

function invalidar(fontes=false) {
    geracao++;
    if(!fontes && leitura)el('btn-gerar-tres-documentos').hidden=false;
    ocupado=false;el('btn-analisar-documentos-intimacao').disabled=false;
    rascunhos.clear();
    el('documentos-intimacao-previa').hidden=true;
    el('documentos-intimacao-previa-conteudo').replaceChildren();
    if(fontes){
        leitura=null;controlador?.abort();
        el('documentos-intimacao-editor').hidden=true;
        el('documentos-intimacao-confirmar-origem').checked=false;
    }
}
async function descartarTrabalho() {
    const anterior=trabalho;trabalho=null;
    if(anterior)try{await requisicaoAeri(anterior,{method:'DELETE',background:true});}catch(_){/* expiração também remove o resultado */}
}
function fechar() {
    invalidar(true);descartarTrabalho();atual=null;
    for(const papel of PAPEIS)el(`documentos-intimacao-${papel}`).value='';
    el('documentos-intimacao-fontes').replaceChildren();
    el('documentos-intimacao-avisos').replaceChildren();
    el('documentos-intimacao-divergencias').replaceChildren();
    el('documentos-intimacao-arquivos-rede').replaceChildren();
    for(const entrada of el('modal-documentos-intimacao').querySelectorAll('input,textarea')){
        if(['checkbox','radio'].includes(entrada.type))entrada.checked=false;else entrada.value='';
    }
    campo('devedor-alvo').replaceChildren();
    el('documentos-intimacao-contexto').textContent='';
    el('doc-int-resumo-automatico').textContent='';el('doc-int-protocolo-aviso').textContent='';
    el('modal-documentos-intimacao').classList.remove('aberta');
}
export function abrirDocumentosIntimacao(item) {
    fechar();atual=item;origem='manual';ocupado=false;
    el('documentos-intimacao-contexto').textContent=`${item.protocolo} · prepare, revise e copie. Nada será enviado ou inserido na Tri7.`;
    campo('in').value=item.protocolo;
    const hoje=new Intl.DateTimeFormat('sv-SE',{timeZone:'America/Sao_Paulo'}).format(new Date());
    campo('data-geracao').value=hoje;
    campo('ultimo-oficio').value='';campo('numero-oficio').value='';
    el('documentos-intimacao-arquivos-rede').hidden=true;
    el('doc-int-modelo-conferido').checked=false;
    el('doc-int-divergencias-conferidas').checked=false;
    status('Informe o último ofício e selecione os três documentos deste IN.');
    el('modal-documentos-intimacao').classList.add('aberta');
    campo('ultimo-oficio').focus();
}
function numerar() {
    invalidar();
    try{campo('numero-oficio').value=proximoOficio(valor('ultimo-oficio'),valor('data-geracao').slice(0,4));status('Próximo número sugerido. Confira a sequência na Tri7; não houve reserva.');}
    catch(erro){campo('numero-oficio').value='';status(erro.message);}
}

function preencher(dados) {
    leitura=dados;
    const conflitoProtocolo=(dados.inconsistencias || []).find(i=>i.campo==='protocoloTri7');
    el('doc-int-confirmacao-protocolo').hidden=!conflitoProtocolo;
    el('doc-int-protocolo-conferido').checked=false;
    el('doc-int-protocolo-aviso').textContent=conflitoProtocolo?`Conferi o recibo deste IN: usarei o protocolo ${conflitoProtocolo.fontes.recibo} nos documentos. O cadastro antigo contém ${conflitoProtocolo.fontes.cadastroAeri} e não será alterado por esta preparação.`:'';
    const campos={processo:dados.processoCredor,'protocolo-tri7':dados.protocoloTri7,'data-protocolo':dados.dataProtocolo,
        matricula:dados.matricula,'registro-garantia':dados.registroGarantia,credor:dados.credor?.nome,cnpj:dados.credor?.cnpj,
        titulo:dados.titulo,contrato:dados.contrato?.numero,'data-contrato':dados.contrato?.data,
        'data-titulo':dados.dataTituloAutuacao,'endereco-imovel':dados.enderecoImovel,
        enderecos:(dados.enderecos || []).join('\n'),devedores:(dados.devedores || []).map(p=>`${p.nome} | ${p.cpf || p.cnpj || ''}`).join('\n'),
        'data-projecao':dados.projecao?.data,'valor-projecao':dados.projecao?.valor,'valor-extenso':dados.projecao?.extenso,
        signatario:dados.signatario,selo:dados.selo,clausula:dados.clausula,'credor-encerramento':dados.credorEncerramento};
    for(const [id,v]of Object.entries(campos))campo(id).value=v || '';
    el('documentos-intimacao-fontes').innerHTML=(dados.fontes || []).map(f=>`<div><strong>${esc(f.papel)}:</strong> ${esc(f.nome)} · ${f.ocr?'OCR local — conferir':'texto extraído'}</div>`).join('');
    const detalhes=document.createElement('details');
    detalhes.innerHTML='<summary>Consultar a origem de cada dado extraído</summary>'+Object.entries(dados.origens || {}).map(([k,v])=>`<p><strong>${esc(k)}:</strong> ${esc(JSON.stringify(v))}</p>`).join('');
    el('documentos-intimacao-fontes').append(detalhes);
    el('documentos-intimacao-avisos').innerHTML=(dados.avisos || []).map(a=>`<p>${esc(a)}</p>`).join('');
    el('documentos-intimacao-divergencias').innerHTML=(dados.inconsistencias || []).map(i=>`<p><strong>Divergência em ${esc(i.campo)}:</strong> ${Object.entries(i.fontes).map(([f,v])=>`${esc(f)}: ${esc(typeof v==='string'?v:JSON.stringify(v))}`).join(' · ')}. Confira os originais e corrija o campo.</p>`).join('');
    el('doc-int-modelo-conferido').checked=false;el('doc-int-divergencias-conferidas').checked=false;
    atualizarAlvo();el('documentos-intimacao-editor').hidden=false;
    el('doc-int-mostrar-todos').checked=false;
    const ca=dados.consultaAutomatica || {};
    el('doc-int-resumo-automatico').textContent=`Matrícula: ${ca.matriculaConsultada?'consultada na Tri7':'consulta não confirmada'} · Garantia: ${ca.garantiaConfirmada?'vinculada ao contrato e às partes':'conferência necessária'} · Protocolo: ${ca.protocoloConsultado?'consultado na Tri7':'consulta não confirmada'}. O responsável sugerido pelo cadastro deve ser conferido; nenhum selo é emitido aqui.`;
    for(const label of el('doc-int-campos-extraidos').querySelectorAll('label')){
        const input=label.querySelector('input,textarea,select');
        const invalido=input.value.includes('\ufffd') || input.id.startsWith('doc-int-data-') && !dataValida(input.value) || input.id==='doc-int-cnpj' && digitos(input.value).length!==14 || input.id==='doc-int-valor-projecao' && !moedaLiteral(input.value);
        label.dataset.excecao=String(input.id!=='doc-int-credor-encerramento' && (!input.value.trim() || invalido || input.id==='doc-int-devedor-alvo' && pessoas().length>1 || input.id==='doc-int-devedores' && pessoas().some(p=>p.cpf.length!==11)));
    }
    mostrarCampos();
    el('doc-int-correcoes').open=[...el('doc-int-campos-extraidos').querySelectorAll('label')].some(l=>l.dataset.excecao==='true');
    gerar();
}
function mostrarCampos(){for(const label of el('doc-int-campos-extraidos').querySelectorAll('label'))label.hidden=!el('doc-int-mostrar-todos').checked && label.dataset.excecao!=='true';}
function pessoas(){return valor('devedores').split(/\r?\n/).filter(s=>s.trim()).map(s=>{const [nome,doc]=s.split('|');return{nome:nome.trim(),cpf:digitos(doc)};});}
function atualizarAlvo(){const s=campo('devedor-alvo'),anterior=s.value;s.innerHTML=pessoas().map((p,i)=>`<option value="${i}">${esc(p.nome)}</option>`).join('');if([...s.options].some(o=>o.value===anterior))s.value=anterior;}

async function tarefaRede(acao,selecao) {
    const versao=geracao,item=atual;
    const base=`/api/intimacoes/${item.id}/preparar-documentos-rede`;
    const resposta=await requisicaoAeri(base,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({fluxo:FLUXO,acao,selecao,referencia:valor('data-geracao')})});
    const url=`${base}/${resposta.id}`;
    if(versao!==geracao){await requisicaoAeri(url,{method:'DELETE',background:true});return null;}
    trabalho=url;
    try{
        for(let n=0;n<420;n++){
            if(versao!==geracao)return null;
            await new Promise(r=>setTimeout(r,2000));
            if(versao!==geracao)return null;
            const r=await requisicaoAeri(url,{background:true});
            if(versao!==geracao)return null;
            if(r.estado==='PRONTO'){
                if(r.dados?.fluxo!==FLUXO)throw Error('O executor retornou uma leitura antiga. Atualize-o para a versão dos três anexos antes de continuar.');
                return r.dados;
            }
            if(r.estado==='ERRO')throw Error(r.erro || 'Não foi possível ler os anexos.');
            status(acao==='listar'?'Localizando arquivos na pasta autorizada deste IN…':'Lendo os três anexos no executor; PDFs digitalizados podem exigir OCR local…');
        }
        throw Error('O executor não concluiu a leitura. Confira a máquina e tente novamente.');
    } finally {if(trabalho===url)await descartarTrabalho();}
}

async function localizar() {
    if(ocupado || !atual)return;
    invalidar(true);ocupado=true;const versao=geracao;
    status('Localizando a pasta deste IN pelo executor…');
    try{
        const dados=await tarefaRede('listar');if(!dados || versao!==geracao)return;
        const arquivos=dados.arquivos || [];if(!arquivos.length)throw Error('A pasta está vazia ou não contém arquivos suportados.');
        const painel=el('documentos-intimacao-arquivos-rede');painel.hidden=false;
        painel.innerHTML=PAPEIS.map(p=>`<label><span>${esc(p)} · arquivo da pasta deste IN</span><select data-anexo-rede="${p}"><option value="">Selecione</option>${arquivos.map(a=>`<option value="${esc(a.id)}">${esc(a.nome)} · ${(a.tamanho/1024).toFixed(0)} KB</option>`).join('')}</select></label>`).join('');
        for(const p of PAPEIS){const candidatos=arquivos.filter(a=>a.sugerido===p);if(candidatos.length===1)painel.querySelector(`[data-anexo-rede="${p}"]`).value=candidatos[0].id;}
        origem='rede';status('Confira os três arquivos selecionados. Se houver mais de um candidato, escolha o documento correto.');
    }catch(e){if(versao===geracao)status(e.message);}finally{if(versao===geracao)ocupado=false;}
}
async function processar() {
    if(ocupado || !atual)return;
    if(!el('documentos-intimacao-confirmar-origem').checked){status('Confirme que os três anexos pertencem ao IN selecionado.');return;}
    try{proximoOficio(valor('ultimo-oficio'),valor('data-geracao').slice(0,4));}catch(e){status(e.message);return;}
    if(!/^INT\/\d{4}\/\d{3,6}$/.test(valor('numero-oficio'))){status('Confira o próximo número do ofício.');return;}
    const versao=++geracao;rascunhos.clear();el('documentos-intimacao-previa').hidden=true;leitura=null;
    ocupado=true;el('btn-analisar-documentos-intimacao').disabled=true;
    el('documentos-intimacao-editor').hidden=true;status('Processando os três anexos…');
    try{
        let dados;
        if(origem==='rede'){
            const selecao=Object.fromEntries(PAPEIS.map(p=>[p,document.querySelector(`[data-anexo-rede="${p}"]`)?.value || '']));
            if(Object.values(selecao).some(v=>!v) || new Set(Object.values(selecao)).size!==3)throw Error('Selecione três arquivos distintos na pasta do IN.');
            dados=await tarefaRede('ler',selecao);
        }else{
            const arquivos=PAPEIS.map(p=>el(`documentos-intimacao-${p}`).files?.[0]);
            if(arquivos.some(a=>!a))throw Error('Anexe o Recibo do Protocolo, o Ofício do Credor e a Planilha de Projeção.');
            if(arquivos.some(a=>a.size>8_000_000) || arquivos.reduce((s,a)=>s+a.size,0)>4_000_000)throw Error('Use o executor para arquivos acima de 4 MB no total. O envio pelo navegador tem esse limite.');
            const form=new FormData();PAPEIS.forEach((p,i)=>form.set(p,arquivos[i],arquivos[i].name));form.set('referencia',valor('data-geracao'));
            controlador=new AbortController();
            dados=await requisicaoAeri(`/api/intimacoes/${atual.id}/preparar-documentos`,{method:'POST',body:form,signal:controlador.signal});
        }
        if(dados && versao===geracao)preencher(dados);
    }catch(e){if(versao===geracao)status(e.name==='AbortError'?'Leitura cancelada.':e.message);}
    finally{if(versao===geracao){ocupado=false;el('btn-analisar-documentos-intimacao').disabled=false;}}
}

function dadosFormulario() {
    const ps=pessoas();
    return{in:atual.protocolo,dataGeracao:dataBr(valor('data-geracao')),oficio:valor('numero-oficio'),
        processo:valor('processo'),protocolo:valor('protocolo-tri7'),dataProtocolo:valor('data-protocolo'),
        matricula:pontos(valor('matricula')),registro:valor('registro-garantia'),credor:valor('credor'),
        credorEncerramento:valor('credor-encerramento'),cnpj:valor('cnpj').replace(/^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})$/,'$1.$2.$3/$4-$5'),
        titulo:valor('titulo'),contrato:valor('contrato'),dataContrato:valor('data-contrato'),
        dataTituloAutuacao:valor('data-titulo'),pessoas:ps,alvo:ps[+valor('devedor-alvo')],
        enderecoImovel:valor('endereco-imovel'),enderecos:valor('enderecos').split(/\r?\n/).map(s=>s.trim()).filter(Boolean),
        dataProjecao:valor('data-projecao'),valorProjecao:moedaLiteral(valor('valor-projecao')),
        valorExtenso:valor('valor-extenso'),signatario:valor('signatario'),selo:valor('selo'),clausula:valor('clausula')};
}
export function pendencias(d,tipo=null) {
    const nomes={processo:'processo do credor',protocolo:'protocolo RGI',matricula:'matrícula',registro:'registro da garantia',
        credor:'credor',titulo:'título completo',contrato:'contrato',enderecoImovel:'endereço do imóvel',
        valorProjecao:'valor projetado com duas casas decimais',valorExtenso:'valor por extenso',signatario:'escrevente',selo:'selo existente',clausula:'cláusula contratual'};
    const campos={autuacao:['processo','protocolo','credor','titulo','contrato','enderecoImovel','signatario'],
        oficio:Object.keys(nomes),convocacao:['titulo','contrato','registro','matricula','enderecoImovel','signatario']};
    const exigidos=tipo?campos[tipo]:Object.keys(nomes);
    const faltas=Object.entries(nomes).filter(([k])=>exigidos.includes(k) && !d[k]).map(([,v])=>v);
    const datas={autuacao:['dataGeracao','dataProtocolo','dataTituloAutuacao'],oficio:['dataGeracao','dataProtocolo','dataContrato','dataProjecao'],convocacao:['dataGeracao','dataContrato']};
    for(const k of tipo?datas[tipo]:['dataGeracao','dataProtocolo','dataContrato','dataTituloAutuacao','dataProjecao'])if(!dataValida(d[k]))faltas.push(k);
    if((!tipo || tipo==='oficio') && d.dataProjecao!==d.dataGeracao)faltas.push('projeção para a data da preparação');
    if(!d.pessoas.length || d.pessoas.some(p=>!p.nome || p.cpf.length!==11))faltas.push('nome e CPF de cada devedor');
    if((!tipo || tipo==='oficio') && digitos(d.cnpj).length!==14)faltas.push('CNPJ do credor');
    if((!tipo || tipo==='oficio') && !d.enderecos.length)faltas.push('endereços para notificação');
    if((!tipo || tipo==='oficio') && !/^INT\/\d{4}\/\d{3,6}$/.test(d.oficio))faltas.push('número do ofício');
    if(JSON.stringify(d).includes('\ufffd'))faltas.push('caracteres ilegíveis');
    return faltas;
}

export function sanitizarHtml(html) {
    const t=document.createElement('template');t.innerHTML=html;
    const permitidas=new Set(['DIV','SECTION','P','SPAN','STRONG','B','EM','I','U','BR','TABLE','TBODY','TR','TD','UL','OL','LI']);
    const estilos=new Set(['font-family','font-size','font-weight','line-height','color','background','text-align','text-indent','text-decoration','margin','margin-top','margin-bottom','width','max-width','height','vertical-align','border','border-collapse','padding','page-break-after','break-after']);
    function limpar(n){
        if(n.nodeType===3)return document.createTextNode(n.textContent);
        if(n.nodeType!==1 || ['SCRIPT','STYLE','IFRAME','OBJECT','SVG','IMG'].includes(n.tagName))return document.createTextNode('');
        if(!permitidas.has(n.tagName))return document.createTextNode(n.textContent);
        const novo=document.createElement(n.tagName.toLowerCase());
        for(const p of n.style)if(estilos.has(p) && !/url\(|expression|javascript|var\(/i.test(n.style.getPropertyValue(p)))novo.style.setProperty(p,n.style.getPropertyValue(p));
        for(const filho of n.childNodes)novo.append(limpar(filho));
        return novo;
    }
    const saida=document.createElement('div');for(const n of t.content.childNodes)saida.append(limpar(n));return saida.innerHTML;
}
function trocarAba(tipo){for(const t of Object.keys(ROTULOS)){el(`doc-int-painel-${t}`).hidden=t!==tipo;el(`doc-int-aba-${t}`).setAttribute('aria-selected',String(t===tipo));}}
function gerar() {
    if(!leitura || leitura.fontes?.length!==3){status('Processe os três anexos novamente.');return;}
    const d=dadosFormulario();
    rascunhos.clear();
    el('documentos-intimacao-abas').innerHTML=Object.entries(ROTULOS).map(([t,n])=>`<button type="button" role="tab" id="doc-int-aba-${t}" aria-controls="doc-int-painel-${t}" aria-selected="false" data-aba-documento="${t}">${n}</button>`).join('');
    el('documentos-intimacao-previa-conteudo').innerHTML=Object.entries(ROTULOS).map(([t,n])=>{
        const faltas=pendencias(d,t);
        rascunhos.set(t,{aprovado:false,geracao,faltas});
        const previa={...d};for(const k of Object.keys(previa))if(typeof previa[k]==='string' && !previa[k])previa[k]=`[PENDENTE: ${k}]`;
        if(!previa.pessoas.length)previa.pessoas=[{nome:'[DEVEDOR A CONFERIR]',cpf:''}];
        previa.alvo=previa.alvo || previa.pessoas[0];if(!previa.enderecos.length)previa.enderecos=['[ENDEREÇO PARA NOTIFICAÇÃO PENDENTE]'];
        return `<section id="doc-int-painel-${t}" role="tabpanel" aria-labelledby="doc-int-aba-${t}" hidden>${faltas.length?`<p class="doc-int-divergencias">Rascunho incompleto · ${faltas.map(esc).join(', ')}. Cópia bloqueada; corrija as exceções.</p>`:''}<p class="doc-int-limite">Fontes: ${leitura.fontes.map(f=>esc(f.nome)).join(' · ')}${leitura.consultaAutomatica?.garantiaConfirmada?' · matrícula/garantia conferida na Tri7':''}</p><article class="doc-int-papel" id="doc-int-texto-${t}" contenteditable="true" role="textbox" aria-multiline="true" aria-label="Texto de ${n}">${GERADORES[t](previa)}</article><div class="doc-int-revisao-acoes"><label class="doc-int-confirmacao"><input type="checkbox" data-aprovar-documento="${t}" ${faltas.length?'disabled':''}> Revisei integralmente esta versão de ${n} e conferi a numeração na Tri7.</label><button type="button" class="btn btn-primary" data-copiar-documento="${t}" disabled>Copiar ${n}</button><button type="button" class="rotina-btn-secondary" data-copiar-simples="${t}" disabled>Copiar texto simples</button></div><p id="doc-int-revisao-${t}" role="status">${faltas.length?'Há campos pendentes.':'Revisão pendente.'}</p></section>`;
    }).join('');
    el('documentos-intimacao-previa').hidden=false;trocarAba('autuacao');
    el('btn-gerar-tres-documentos').hidden=true;
    const completos=[...rascunhos.values()].filter(r=>!r.faltas.length).length;
    status(`Três textos preparados automaticamente; ${completos} completos para revisão. Os demais indicam as exceções, sem inventar dados. A cópia exige aprovação individual.`);
}
function bloquear(tipo){const r=rascunhos.get(tipo);if(r)r.aprovado=false;el(`doc-int-painel-${tipo}`).querySelector('[data-aprovar-documento]').checked=false;for(const b of el(`doc-int-painel-${tipo}`).querySelectorAll('button'))b.disabled=true;el(`doc-int-revisao-${tipo}`).textContent='Texto alterado: revise novamente.';}
function consentimentosOk(){return el('doc-int-modelo-conferido').checked && el('doc-int-divergencias-conferidas').checked && (!(leitura.inconsistencias || []).some(i=>i.campo==='protocoloTri7') || el('doc-int-protocolo-conferido').checked);}
function eventoDocumento(tipo,acao){return requisicaoAeri(`/api/intimacoes/${atual.id}/documentos-evento`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({tipo,acao,revisado:true,numeroOficio:valor('numero-oficio'),rascunhoHash:rascunhos.get(tipo)?.hash,fontes:leitura.fontes.map(f=>f.sha256)})});}
async function aprovar(tipo,checkbox){
    const r=rascunhos.get(tipo);if(!r)return;
    if(!checkbox.checked){bloquear(tipo);return;}
    if(r.faltas.length || !consentimentosOk()){checkbox.checked=false;status('Confira as exceções, a aplicabilidade do modelo e a divergência do protocolo antes de aprovar esta versão.');return;}
    const v=geracao,html=el(`doc-int-texto-${tipo}`).innerHTML;
    checkbox.disabled=true;
    try{r.hash=await hashTexto(sanitizarHtml(html));if(v!==geracao)return;
        await eventoDocumento(tipo,'revisao');if(v!==geracao || !rascunhos.has(tipo))return;
        if(html!==el(`doc-int-texto-${tipo}`).innerHTML || !consentimentosOk()){bloquear(tipo);return;}
        r.aprovado=true;r.html=html;for(const b of el(`doc-int-painel-${tipo}`).querySelectorAll('button'))b.disabled=false;
        el(`doc-int-revisao-${tipo}`).textContent='Revisão registrada. Cópia liberada para esta versão; número não reservado.';
    }catch(e){checkbox.checked=false;status(e.message);}finally{checkbox.disabled=false;}
}
async function copiar(tipo,simples=false){
    const r=rascunhos.get(tipo),artigo=el(`doc-int-texto-${tipo}`);
    if(!r?.aprovado || r.geracao!==geracao || r.html!==artigo.innerHTML || !consentimentosOk()){status('Revise a versão atual antes de copiar.');return;}
    const v=geracao;
    try{
        if(simples){if(!navigator.clipboard?.writeText)throw Error('Área de transferência indisponível neste navegador.');await navigator.clipboard.writeText(artigo.innerText);}
        else{
            if(!navigator.clipboard?.write || !globalThis.ClipboardItem)throw Error('Cópia formatada indisponível. Use o botão explícito de texto simples e ajuste a formatação na Tri7.');
            const html=sanitizarHtml(artigo.innerHTML);
            await navigator.clipboard.write([new ClipboardItem({'text/html':new Blob([html],{type:'text/html'}),'text/plain':new Blob([artigo.innerText],{type:'text/plain'})})]);
        }
        if(v!==geracao)return;
        status(`${ROTULOS[tipo]} copiada${simples?' em texto simples, sem formatação':''}. Cole na Tri7 e confira antes de salvar. Nenhum envio foi feito.`);
        try{await eventoDocumento(tipo,'copia');}catch(e){status(`O texto foi copiado, mas o registro da cópia não foi confirmado: ${e.message}`);}
    }catch(e){status(`Não foi possível copiar: ${e.message}`);}
}

// Compatibilidade com o envio RTD existente; esta bancada não o aciona.
function enderecoParaRtd(original) {
    const cepMatch = original.match(/\bCEP\s*:?\s*(\d{5})[-.]?(\d{3})\b/i);
    const semCep = (cepMatch ? original.slice(0, cepMatch.index) : original).replace(/[,;\s]+$/, '');
    const cidadeMatch = semCep.match(/,\s*([^,]+?)\s*[/\-]\s*([A-Za-z]{2})$/);
    const antesCidade = cidadeMatch ? semCep.slice(0, cidadeMatch.index) : semCep;
    const numeroMatch = antesCidade.match(/(?:,\s*|\s+n[ºo°.]?\s*)(\d{1,6}[A-Za-z]?(?:[-/][A-Za-z0-9]+)?)\b/i);
    const logradouro = numeroMatch ? antesCidade.slice(0, numeroMatch.index).replace(/,\s*/g, ' ').trim() : '';
    const restante = numeroMatch ? antesCidade.slice(numeroMatch.index + numeroMatch[0].length).replace(/^,\s*/, '') : '';
    const partes = restante.split(',').map(parte => parte.trim()).filter(Boolean);
    return {
        CEP:cepMatch ? `${cepMatch[1]}${cepMatch[2]}` : '',
        Logradouro:logradouro, Numero:numeroMatch?.[1] || '',
        Complemento:partes.length > 1 ? partes.slice(0,-1).join(', ') : '',
        Bairro:partes.length ? partes.at(-1) : '',
        Cidade:cidadeMatch?.[1]?.trim() || '', UF:cidadeMatch?.[2]?.toUpperCase() || '',
    };
}
export function montarParesRtd(pessoas, enderecos) {
    return pessoas.flatMap(pessoa => enderecos
        .filter(endereco => /MORRINHOS/i.test(endereco))
        .map(original => ({pessoa, endereco:enderecoParaRtd(original)})));
}

export function iniciarDocumentosIntimacao(_abrirRtdComPares){
    el('btn-fechar-documentos-intimacao').addEventListener('click',fechar);
    // Não fechar ao soltar o mouse fora do painel durante uma seleção de texto.
    campo('ultimo-oficio').addEventListener('input',numerar);
    campo('data-geracao').addEventListener('change',()=>{invalidar(true);numerar();});
    campo('numero-oficio').addEventListener('input',()=>invalidar());
    el('btn-abrir-pasta-documentos-intimacao').addEventListener('click',()=>{if(atual)window.location.href=`aeri-intimacao://abrir/${encodeURIComponent(atual.protocolo)}`;});
    el('btn-ler-documentos-intimacao-rede').addEventListener('click',localizar);
    el('documentos-intimacao-arquivos-rede').addEventListener('change',()=>{invalidar(true);origem='rede';});
    for(const p of PAPEIS)el(`documentos-intimacao-${p}`).addEventListener('change',()=>{invalidar(true);origem='manual';});
    el('btn-analisar-documentos-intimacao').addEventListener('click',processar);
    el('btn-gerar-tres-documentos').addEventListener('click',()=>gerar());
    el('doc-int-mostrar-todos').addEventListener('change',mostrarCampos);
    el('documentos-intimacao-editor').addEventListener('input',e=>{if(e.target.type==='checkbox'){if(e.target.id!=='doc-int-mostrar-todos' && !e.target.checked)for(const [tipo,r] of rascunhos)if(r.aprovado)bloquear(tipo);return;}if(e.target.matches('input,textarea,select')){invalidar();if(e.target.id==='doc-int-devedores')atualizarAlvo();if(e.target.id==='doc-int-valor-projecao')campo('valor-extenso').value='';}});
    el('documentos-intimacao-editor').addEventListener('change',e=>{if(e.target.matches('select'))invalidar();});
    el('documentos-intimacao-abas').addEventListener('click',e=>{const t=e.target.closest('[data-aba-documento]')?.dataset.abaDocumento;if(t)trocarAba(t);});
    const previa=el('documentos-intimacao-previa-conteudo');
    previa.addEventListener('input',e=>{const artigo=e.target.closest('.doc-int-papel');if(artigo)bloquear(artigo.id.replace('doc-int-texto-',''));});
    previa.addEventListener('paste',e=>{if(!e.target.closest('.doc-int-papel'))return;e.preventDefault();document.execCommand('insertText',false,e.clipboardData.getData('text/plain'));});
    previa.addEventListener('drop',e=>e.preventDefault());
    previa.addEventListener('change',e=>{const t=e.target.dataset.aprovarDocumento;if(t)aprovar(t,e.target);});
    previa.addEventListener('click',e=>{const b=e.target.closest('button');if(b?.dataset.copiarDocumento)copiar(b.dataset.copiarDocumento);if(b?.dataset.copiarSimples)copiar(b.dataset.copiarSimples,true);});
}
