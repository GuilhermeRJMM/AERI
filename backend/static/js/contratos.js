import {requisicaoAeri as requisicaoOriginal} from './api.js?v=20260824-csrf-v1';
import {escaparHtml} from './util.js';
let trabalho=null, protocolo=null, timer=null, geracao=0;
async function requisicaoAeri(...args){const g=geracao;const r=await requisicaoOriginal(...args);if(g!==geracao)throw new Error('Fluxo encerrado.');return r;}
const $=id=>document.getElementById(`contratos-${id}`);
const json=(method,body)=>({method,headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
function mensagem(texto){$('mensagem').textContent=texto;}
function rotuloCampo(campo){
    const nomes={contrato:'Contrato',vendedores:'Vendedor',compradores:'Comprador',credora:'Credora',valores:'Valores',financiamento:'Financiamento',matricula:'Matrícula',imovel:'Imóvel',numero:'Número',cpf:'CPF',cnpj:'CNPJ',razao_social:'Razão social',nome:'Nome',profissao:'Profissão',conjuge:'Cônjuge',descricao:'Descrição',orgao:'Órgão emissor',endereco:'Endereço',anuente:'Interveniente anuente',area:'Área',data:'Data',sexo:'Sexo (M/F)',documento:'Documento',estado_civil:'Estado civil',regime_bens:'Regime de bens',proximo_ato:'Próximo ato'};
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
        $('comparacoes').innerHTML=dados.confronto.comparacoes.map(c=>`<div class="confronto-linha ${c.situacao==='COMPATIVEL'?'':'revisar'}"><strong>${escaparHtml(rotuloCampo(c.campo))} · ${c.situacao==='COMPATIVEL'?'Compatível':'Revisar'}</strong><div class="contratos-comparacao"><div><small>CONTRATO</small><p>${escaparHtml(c.contrato)}</p></div><div><small>MATRÍCULA / CONTEXTO</small><p>${escaparHtml(c.matricula)}</p></div></div>${c.somenteConferencia?'<p>Item de conferência. Uma operação anterior não substitui os dados do contrato novo.</p>':''}<label>Decisão<select data-decisao="${escaparHtml(c.campo)}"><option value="">Selecione…</option><option value="CONTRATO">Manter dados do contrato conferidos</option>${c.permiteMatricula?'<option value="MATRICULA">Usar o valor da matrícula na minuta</option>':''}<option value="MANUAL">Conferência manual na ficha</option></select></label><label>Justificativa / observação<input data-justificativa="${escaparHtml(c.campo)}" maxlength="2000" placeholder="Registre a decisão tomada"></label></div>`).join('');
    }
    $('confirmacao').checked=false;
    $('minutas').hidden=!dados.minutas;
    if(dados.minutas){
        for(const chave of ['venda','alienacao']) $(`minuta-${chave}`).value=dados.minutasFinais?.[chave] ?? dados.minutas[chave].texto;
        $('pendencias-minuta').innerHTML=Object.values(dados.minutas).flatMap(m=>m.pendencias).map(p=>`<p class="contratos-aviso">${escaparHtml(p.campo)} — ${escaparHtml(p.motivo)}</p>`).join('');
    }
}
async function acompanhar(id){
    clearTimeout(timer);const atual=geracao;
    try{
        const r=await requisicaoAeri(`/api/contratos/${id}`,{background:true});if(atual!==geracao)return;trabalho=r;
        if(['AGUARDANDO','PROCESSANDO'].includes(r.estado)){
            mensagem(r.estado==='AGUARDANDO'?'Na fila do servidor. Se não avançar, verifique se o worker operacional está ativo.':`Extraindo o documento: ${r.progresso}%`);
            timer=setTimeout(()=>acompanhar(id),2500);
        }else if(r.estado==='FALHA'){mensagem(r.erro || 'Falha na extração.');}
        else {desenhar();mensagem('Trabalho carregado. Confira os campos antes de prosseguir.');}
    }catch(e){mensagem(e.message);}
}
export function limparContratos(){geracao++;clearTimeout(timer);trabalho=null;protocolo=null;for(const s of ['extraido','conferencia','minutas'])$(s).hidden=true;for(const s of ['documentos','recentes','ficha','texto','historico','comparacoes','exigencias','alertas','pendencias-minuta'])$(s).replaceChildren();for(const s of ['minuta-venda','minuta-alienacao','matricula'])$(s).value='';$('original').removeAttribute('href');$('confirmacao').checked=false;mensagem('');}
async function acao(botao,executar){botao.disabled=true;try{await executar();}catch(e){if(e.message!=='Fluxo encerrado.')mensagem(e.message);}finally{botao.disabled=false;}}
export function iniciarContratos(){
    $('protocolo-form').addEventListener('submit',e=>{e.preventDefault();acao(e.submitter,async()=>{
        limparContratos();const r=await requisicaoAeri(`/api/contratos/protocolo/${encodeURIComponent($('protocolo').value)}`);protocolo=r.protocolo;
        $('documentos').innerHTML=`<h3>${escaparHtml(r.titulo||'Documentos do protocolo')}</h3><p>${escaparHtml(r.mensagem)}</p>`+r.documentos.map(d=>`<div class="confronto-linha"><strong>${escaparHtml(d.tipo_documento||d.categoria||'Documento')} · versão ${escaparHtml(String(d.versao||''))}</strong><p>${escaparHtml(d.descricao||'Sem descrição')}</p><button type="button" class="btn" data-ged="${escaparHtml(String(d.ged_documento_id))}">Selecionar e extrair</button></div>`).join('');
        if(!r.documentos.length) mensagem('Nenhum documento GED vinculado ao protocolo.');
    });});
    $('documentos').addEventListener('click',e=>{const b=e.target.closest('[data-ged]');if(b)acao(b,async()=>{trabalho=await requisicaoAeri('/api/contratos',json('POST',{protocolo,documentoId:b.dataset.ged}));await acompanhar(trabalho.id);});});
    $('recentes-btn').addEventListener('click',e=>acao(e.target,async()=>{const r=await requisicaoAeri('/api/contratos');$('recentes').innerHTML=r.map(t=>`<button class="btn" data-trabalho="${t.id}">Protocolo ${escaparHtml(t.protocolo)} · ${escaparHtml(t.estado)}</button>`).join('')||'<p>Nenhum trabalho anterior.</p>';}));
    $('recentes').addEventListener('click',e=>{const b=e.target.closest('[data-trabalho]');if(b){geracao++;acompanhar(b.dataset.trabalho);}});
    $('matricula-form').addEventListener('submit',e=>{e.preventDefault();acao(e.submitter,async()=>{
        mensagem('Consultando o texto da matrícula e confrontando…');
        trabalho=await requisicaoAeri(`/api/contratos/${trabalho.id}/matricula`,json('POST',{versao:trabalho.versao,matricula:$('matricula').value,ficha:lerFicha()}));desenhar();mensagem('Confrontação concluída. Registre suas decisões.');
    });});
    $('texto-btn').addEventListener('click',e=>acao(e.target,async()=>{const r=await requisicaoAeri(`/api/contratos/${trabalho.id}/texto`);$('texto').innerHTML=(r.paginas||[]).map(p=>`<details><summary>Página ${p.pagina} · ${escaparHtml(p.metodo)} · confiança ${p.confianca??'não fornecida'}</summary><pre style="white-space:pre-wrap">${escaparHtml(p.texto)}</pre></details>`).join('');}));
    $('gerar').addEventListener('click',e=>acao(e.target,async()=>{
        const decisoes={};document.querySelectorAll('[data-decisao]').forEach(el=>{if(el.value){const c=el.dataset.decisao;const justificativa=[...document.querySelectorAll('[data-justificativa]')].find(i=>i.dataset.justificativa===c)?.value||'';decisoes[c]={acao:el.value,justificativa};}});
        trabalho=await requisicaoAeri(`/api/contratos/${trabalho.id}/gerar`,json('POST',{versao:trabalho.versao,ficha:lerFicha(),decisoes,extracaoConferida:$('confirmacao').checked}));desenhar();mensagem('Minuta gerada. Confira também os marcadores e dados faltantes.');
    }));
    $('salvar').addEventListener('click',e=>acao(e.target,async()=>{trabalho=await requisicaoAeri(`/api/contratos/${trabalho.id}/minuta`,json('PUT',{versao:trabalho.versao,textos:{venda:$('minuta-venda').value,alienacao:$('minuta-alienacao').value}}));mensagem('Versão editada salva no histórico.');}));
    $('copiar').addEventListener('click',e=>acao(e.target,async()=>{await navigator.clipboard.writeText($('minuta-venda').value+'\n\n'+$('minuta-alienacao').value);mensagem('Atos copiados.');}));
    $('historico-btn').addEventListener('click',e=>acao(e.target,async()=>{const h=await requisicaoAeri(`/api/contratos/${trabalho.id}/historico`);$('historico').innerHTML=h.map(v=>`<p>Versão ${v.versao} · ${escaparHtml(v.etapa)} · ${escaparHtml(v.usuario||'Executor')} · ${new Date(v.criado_em).toLocaleString('pt-BR')}</p>`).join('');}));
}
