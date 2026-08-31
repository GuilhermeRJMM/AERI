import {requisicaoAeri as requisicaoOriginal} from './api.js?v=20260824-csrf-v1';
import {escaparHtml} from './util.js';
let trabalho=null, protocolo=null, timer=null, geracao=0;
async function requisicaoAeri(...args){const g=geracao;const r=await requisicaoOriginal(...args);if(g!==geracao)throw new Error('Fluxo encerrado.');return r;}
const $=id=>document.getElementById(`contratos-${id}`);
const json=(method,body)=>({method,headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
function mensagem(texto){$('mensagem').textContent=texto;}
function avisoGeracao(texto,erro=false){const el=$('geracao-status');el.textContent=texto;el.classList.toggle('contratos-erro',erro);}
function decisoesDaTela(){
    const decisoes={};document.querySelectorAll('[data-decisao]').forEach(el=>{
        if(el.value){const c=el.dataset.decisao;const justificativa=[...document.querySelectorAll('[data-justificativa]')].find(i=>i.dataset.justificativa===c)?.value||'';decisoes[c]={acao:el.value,justificativa};}
    });return decisoes;
}
function pendenciaGeracao(){
    if(!trabalho?.confrontoAtual)return {texto:'Esta comparação foi feita com regras anteriores. Clique em Confrontar com a matrícula novamente.',alvo:$('matricula')};
    if(!trabalho?.dados?.confronto)return {texto:'Confronte os dados com a matrícula antes de gerar.',alvo:$('matricula')};
    if(JSON.stringify(lerFicha())!==JSON.stringify(trabalho.dados.ficha))return {texto:'Você editou a ficha. Clique em Confrontar com a matrícula novamente.',alvo:$('matricula')};
    for(const c of trabalho.dados.confronto.comparacoes){
        if(c.situacao==='COMPATIVEL')continue;
        const el=[...document.querySelectorAll('[data-decisao]')].find(i=>i.dataset.decisao===c.campo);
        if(!el?.value)return {texto:`Selecione uma decisão em ${rotuloCampo(c.campo)}.`,alvo:el};
        const justificativa=[...document.querySelectorAll('[data-justificativa]')].find(i=>i.dataset.justificativa===c.campo);
        if(!justificativa?.value.trim())return {texto:`Informe a justificativa em ${rotuloCampo(c.campo)}.`,alvo:justificativa};
    }
    if(!$('confirmacao').checked)return {texto:'Marque a confirmação de conferência dos dados antes de gerar.',alvo:$('confirmacao')};
    return null;
}
function quadroComparacao(c){
    const compativel=c.situacao==='COMPATIVEL';
    const operacao=['compradores','credora','valores','financiamento'].includes(c.campo);
    const valores=operacao?`<p class="contratos-orientacao">Dados da nova operação: confira no contrato, sem compará-los com valores de um financiamento anterior.</p><details class="contratos-dados-operacao"><summary>Ver dados do contrato</summary>${c.camposConferencia?`<dl>${c.camposConferencia.map(i=>`<div><dt>${escaparHtml(rotuloCampo(i.campo))}</dt><dd>${escaparHtml(i.valor===''||i.valor==null?'NÃO CONSTA':typeof i.valor==='boolean'?(i.valor?'Sim':'Não'):String(i.valor))}</dd></div>`).join('')}</dl>`:`<p>${escaparHtml(c.contrato)}</p>`}</details>`:`<div class="contratos-comparacao"><div><small>CONTRATO</small><p>${escaparHtml(c.contrato)}</p></div><div><small>MATRÍCULA</small><p>${escaparHtml(c.matricula)}</p></div></div>`;
    return `<div class="confronto-linha ${compativel?'compativel':'revisar'}"><strong>${escaparHtml(rotuloCampo(c.campo))} <span class="contratos-situacao">${compativel?'Compatível':operacao?'Conferir no contrato':'Revisar'}</span></strong>${valores}${compativel?'':`<div class="contratos-decisao"><label>Decisão<select data-decisao="${escaparHtml(c.campo)}"><option value="">Selecione…</option><option value="CONTRATO">Manter dados do contrato conferidos</option>${c.permiteMatricula?'<option value="MATRICULA">Usar o valor da matrícula na minuta</option>':''}<option value="MANUAL">Conferência manual na ficha</option></select></label><label>Justificativa / observação<input data-justificativa="${escaparHtml(c.campo)}" maxlength="2000" placeholder="Registre o que foi conferido"></label></div>`}</div>`;
}
function rotuloCampo(campo){
    const nomes={contrato:'Contrato',vendedores:'Vendedor',compradores:'Comprador',credora:'Credora',valores:'Valores',financiamento:'Financiamento',matricula:'Matrícula',imovel:'Imóvel',numero:'Número',cpf:'CPF',cnpj:'CNPJ',razao_social:'Razão social',nome:'Nome',profissao:'Profissão',conjuge:'Cônjuge',descricao:'Descrição',orgao:'Órgão emissor',endereco:'Endereço',anuente:'Interveniente anuente',area:'Área',lote:'Lote',quadra:'Quadra',data:'Data',sexo:'Sexo (M/F)',documento:'Documento',estado_civil:'Estado civil',regime_bens:'Regime de bens',proximo_ato:'Próximo ato'};
    return campo.split('.').map(k=>/^\d+$/.test(k)?String(Number(k)+1):nomes[k]||k.replaceAll('_',' ')).join(' · ');
}
function campos(obj,prefixo='') {
    if(obj===null || obj===undefined) return [];
    if(typeof obj !== 'object') return [{campo:prefixo,valor:obj}];
    return Object.entries(obj).filter(([k])=>!['origens','brutos'].includes(k)).flatMap(([k,v])=>campos(v,prefixo?`${prefixo}.${k}`:k));
}
function lerFicha(){
    const ficha=structuredClone(trabalho.dados.ficha);
    document.querySelectorAll('[data-contrato-campo]').forEach(el=>{
        const partes=el.dataset.contratoCampo.split('.');const ultimo=partes.pop();let alvo=ficha;
        for(const p of partes) alvo=alvo[p];
        alvo[ultimo]=el.type==='checkbox'?el.checked:el.type==='number'?Number(el.value):el.value;
    }); return ficha;
}
function desenhar(){
    const dados=trabalho.dados;
    if(!dados.ficha) return;
    $('extraido').hidden=false;
    $('original').href=`/api/contratos/${trabalho.id}/documento`;
    $('ficha').innerHTML=['contrato','vendedores','compradores','credora','valores','financiamento','matricula'].map(grupo=>`<details ${['contrato','vendedores','compradores'].includes(grupo)?'open':''}><summary>${escaparHtml(grupo.replaceAll('_',' '))}</summary><div class="contratos-campos">${campos(dados.ficha[grupo],grupo).map(c=>`<label>${escaparHtml(rotuloCampo(c.campo))}<input data-contrato-campo="${escaparHtml(c.campo)}" type="${typeof c.valor==='number'?'number':typeof c.valor==='boolean'?'checkbox':'text'}" ${typeof c.valor==='number'?'step="any" min="0"':''} ${typeof c.valor==='boolean'?(c.valor?'checked':''):`value="${escaparHtml(String(c.valor))}"`}><small>${escaparHtml(dados.evidencias?.[c.campo]?.origem || 'Conferência manual')} ${dados.evidencias?.[c.campo]?.paginas?.length ? '· p. '+dados.evidencias[c.campo].paginas.join(', ') : ''}</small></label>`).join('')}</div></details>`).join('');
    $('alertas').innerHTML=`<details><summary>${dados.alertasExtracao?.length || 0} campos para conferência</summary>${(dados.alertasExtracao||[]).map(a=>`<p>${escaparHtml(a.campo)} — ${escaparHtml(a.motivo)}</p>`).join('')}</details>`;
    $('matricula').value=dados.confronto?.numero || dados.ficha.matricula.numero || '';
    $('conferencia').hidden=!dados.confronto;
    if(dados.confronto){
        $('exigencias').innerHTML=dados.confronto.exigencias.map(e=>`<details class="confronto-linha revisar"><summary>${escaparHtml(e.titulo)}</summary><p>${escaparHtml(e.detalhe)}</p></details>`).join('');
        const certas=dados.confronto.comparacoes.filter(c=>c.situacao==='COMPATIVEL');
        const pendentes=dados.confronto.comparacoes.filter(c=>c.situacao!=='COMPATIVEL');
        $('comparacoes').innerHTML=`<details class="contratos-compativeis"><summary>${certas.length} campos compatíveis — sem decisão obrigatória</summary>${certas.map(quadroComparacao).join('')}</details><p>${pendentes.length} itens para conferir antes de gerar.</p>`+pendentes.map(quadroComparacao).join('');
        for(const d of dados.decisoes||[]){
            const el=[...document.querySelectorAll('[data-decisao]')].find(i=>i.dataset.decisao===d.campo);
            const obs=[...document.querySelectorAll('[data-justificativa]')].find(i=>i.dataset.justificativa===d.campo);
            if(el)el.value=d.acao;if(obs)obs.value=d.justificativa;
        }
        avisoGeracao(trabalho.confrontoAtual?'':'Regras atualizadas: clique em Confrontar com a matrícula novamente.',!trabalho.confrontoAtual);
    }
    $('confirmacao').checked=false;
    $('minutas').hidden=!dados.minutas||!trabalho.confrontoAtual;
    if(dados.minutas){
        $('pendencias-minuta').innerHTML=Object.values(dados.minutas).flatMap(m=>m.pendencias).map(p=>`<p class="contratos-aviso">${escaparHtml(p.campo)} — ${escaparHtml(p.motivo)}</p>`).join('');
    }
}
async function acompanhar(id,ate=Date.now()+95000){
    clearTimeout(timer);const atual=geracao;
    try{
        const r=await requisicaoAeri(`/api/contratos/${id}`,{background:true});if(atual!==geracao)return;trabalho=r;
        if(['AGUARDANDO','PROCESSANDO','FALHA'].includes(r.estado)){
            for(const s of ['extraido','conferencia','minutas'])$(s).hidden=true;
        }
        $('retomar').hidden=!['AGUARDANDO','PROCESSANDO','FALHA'].includes(r.estado);
        if(r.estado==='AGUARDANDO'){
            mensagem('Este trabalho ainda não foi extraído. Clique em Retomar extração; não é necessário um executor para PDFs com texto.');
        }else if(r.estado==='PROCESSANDO'){
            if(Date.now()<ate){mensagem(`Extraindo o documento: ${r.progresso}%. Aguarde a conclusão desta requisição.`);timer=setTimeout(()=>acompanhar(id,ate),2500);}
            else mensagem('A extração não confirmou a conclusão no prazo. Retome este mesmo trabalho para verificar ou tentar novamente.');
        }else if(r.estado==='FALHA'){mensagem(r.erro || 'Falha na extração.');}
        else {desenhar();mensagem('Trabalho carregado. Confira os campos antes de prosseguir.');}
    }catch(e){mensagem(e.message);}
}
async function extrairSelecionado(id){
    clearTimeout(timer);
    for(const s of ['extraido','conferencia','minutas','retomar'])$(s).hidden=true;
    mensagem('Obtendo o contrato no GED e extraindo o texto… Isso pode levar alguns segundos.');
    $('mensagem').setAttribute('aria-busy','true');
    const g=geracao;
    const controller=new AbortController();
    const limite=setTimeout(()=>controller.abort(),70000);
    try{
        trabalho=await requisicaoAeri(`/api/contratos/${id}/extrair`,{...json('POST',{}),signal:controller.signal});
        await acompanhar(id);
    }catch(e){
        if(g!==geracao)return;
        $('retomar').hidden=false;
        mensagem(e.name==='AbortError'?'A requisição excedeu o tempo de espera. Aguarde alguns segundos e retome este mesmo trabalho, sem criar outro.':e.message);
    }finally{clearTimeout(limite);if(g===geracao)$('mensagem').setAttribute('aria-busy','false');}
}
export function limparContratos(){geracao++;clearTimeout(timer);trabalho=null;protocolo=null;for(const s of ['extraido','conferencia','minutas','retomar'])$(s).hidden=true;for(const s of ['documentos','recentes','ficha','historico','comparacoes','exigencias','alertas','pendencias-minuta'])$(s).replaceChildren();$('matricula').value='';$('original').removeAttribute('href');$('confirmacao').checked=false;$('mensagem').setAttribute('aria-busy','false');avisoGeracao('');$('copia-status').textContent='';mensagem('');}
async function acao(botao,executar){botao.disabled=true;try{await executar();}catch(e){if(e.message!=='Fluxo encerrado.')mensagem(e.message);}finally{botao.disabled=false;}}
export function iniciarContratos(){
    $('ficha').addEventListener('input',()=>{$('minutas').hidden=true;avisoGeracao('Ficha alterada: confronte novamente com a matrícula antes de gerar.');});
    $('comparacoes').addEventListener('input',()=>{$('minutas').hidden=true;});
    $('protocolo-form').addEventListener('submit',e=>{e.preventDefault();acao(e.submitter,async()=>{
        limparContratos();const r=await requisicaoAeri(`/api/contratos/protocolo/${encodeURIComponent($('protocolo').value)}`);protocolo=r.protocolo;
        $('documentos').innerHTML=`<h3>${escaparHtml(r.titulo||'Documentos do protocolo')}</h3><p>${escaparHtml(r.mensagem)}</p>`+r.documentos.map(d=>`<div class="confronto-linha"><strong>${escaparHtml(d.tipo_documento||d.categoria||'Documento')} · versão ${escaparHtml(String(d.versao||''))}</strong><p>${escaparHtml(d.descricao||'Sem descrição')}</p><button type="button" class="btn" data-ged="${escaparHtml(String(d.ged_documento_id))}">Selecionar e extrair</button></div>`).join('');
        if(!r.documentos.length) mensagem('Nenhum documento GED vinculado ao protocolo.');
    });});
    $('documentos').addEventListener('click',e=>{const b=e.target.closest('[data-ged]');if(b)acao(b,async()=>{geracao++;clearTimeout(timer);mensagem('Preparando extração do documento escolhido…');trabalho=await requisicaoAeri('/api/contratos',json('POST',{protocolo,documentoId:b.dataset.ged}));await extrairSelecionado(trabalho.id);});});
    $('retomar').addEventListener('click',e=>acao(e.target,async()=>{if(trabalho)await extrairSelecionado(trabalho.id);}));
    $('recentes-btn').addEventListener('click',e=>acao(e.target,async()=>{const r=await requisicaoAeri('/api/contratos');$('recentes').innerHTML=r.map(t=>`<button class="btn" data-trabalho="${t.id}">Protocolo ${escaparHtml(t.protocolo)} · ${escaparHtml(t.estado)}</button>`).join('')||'<p>Nenhum trabalho anterior.</p>';}));
    $('recentes').addEventListener('click',e=>{const b=e.target.closest('[data-trabalho]');if(b){geracao++;acompanhar(b.dataset.trabalho);}});
    $('matricula-form').addEventListener('submit',e=>{e.preventDefault();acao(e.submitter,async()=>{
        mensagem('Consultando o texto da matrícula e confrontando…');
        trabalho=await requisicaoAeri(`/api/contratos/${trabalho.id}/matricula`,json('POST',{versao:trabalho.versao,matricula:$('matricula').value,ficha:lerFicha()}));desenhar();mensagem('Confrontação concluída. Registre suas decisões.');
    });});
    $('gerar').addEventListener('click',e=>acao(e.target,async()=>{
        const pendencia=pendenciaGeracao();
        document.querySelectorAll('[aria-invalid="true"]').forEach(el=>el.removeAttribute('aria-invalid'));
        if(pendencia){avisoGeracao(pendencia.texto,true);pendencia.alvo?.setAttribute('aria-invalid','true');pendencia.alvo?.focus();pendencia.alvo?.scrollIntoView({block:'center',behavior:'smooth'});return;}
        const g=geracao;avisoGeracao('Gerando minuta… Aguarde.');
        const controller=new AbortController();const limite=setTimeout(()=>controller.abort(),60000);
        try{
            const resultado=await requisicaoAeri(`/api/contratos/${trabalho.id}/gerar`,{...json('POST',{versao:trabalho.versao,ficha:lerFicha(),decisoes:decisoesDaTela(),extracaoConferida:$('confirmacao').checked}),signal:controller.signal});
            if(!resultado?.dados?.minutas?.venda?.texto||!resultado?.dados?.minutas?.alienacao?.texto)throw new Error('O servidor não retornou os textos esperados. Recarregue o trabalho antes de tentar novamente.');
            trabalho=resultado;
            desenhar();avisoGeracao('Minuta gerada. Copie os atos abaixo e confira o texto na Tri7.');$('minutas').scrollIntoView({block:'start',behavior:'smooth'});
        }catch(erro){if(g===geracao)avisoGeracao((erro.name==='AbortError'?'Tempo de espera excedido. Consulte Meus trabalhos antes de tentar novamente.':erro.message)+(erro.identificador?` Código para suporte: ${erro.identificador}`:''),true);}
        finally{clearTimeout(limite);}
    }));
    for(const [botao,chaves] of [['copiar-venda',['venda']],['copiar-alienacao',['alienacao']],['copiar',['venda','alienacao']]]){
        $(botao).addEventListener('click',e=>acao(e.target,async()=>{
            try{
                if(!trabalho?.confrontoAtual)throw new Error('Atualize a comparação e gere a minuta novamente antes de copiar.');
                if(JSON.stringify(lerFicha())!==JSON.stringify(trabalho.dados.ficha))throw new Error('Ficha alterada: confronte e gere novamente antes de copiar.');
                const textos=chaves.map(c=>trabalho?.dados?.minutasFinais?.[c]??trabalho?.dados?.minutas?.[c]?.texto);
                if(textos.some(t=>!t))throw new Error('Gere a minuta antes de copiar.');
                if(!navigator.clipboard?.writeText)throw new Error('A cópia não está disponível neste navegador. Abra o AERI diretamente em HTTPS.');
                await navigator.clipboard.writeText(textos.join('\n\n'));
                $('copia-status').textContent='Copiado. Cole e confira o texto na Tri7.';
            }catch(erro){$('copia-status').textContent=erro.name==='NotAllowedError'?'O navegador bloqueou a cópia. Abra o AERI diretamente, fora do iframe, e tente novamente.':erro.message;}
        }));
    }
    $('historico-btn').addEventListener('click',e=>acao(e.target,async()=>{const h=await requisicaoAeri(`/api/contratos/${trabalho.id}/historico`);$('historico').innerHTML=h.map(v=>`<p>Versão ${v.versao} · ${escaparHtml(v.etapa)} · ${escaparHtml(v.usuario||'Executor')} · ${new Date(v.criado_em).toLocaleString('pt-BR')}</p>`).join('');}));
}
