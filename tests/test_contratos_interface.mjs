// Regressões da interface real: avisos ao gerar, comparação e cópia sem editor.
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const codigo=readFileSync(new URL('../backend/static/js/contratos.js',import.meta.url),'utf8')
    .replace(/^import .*;\r?\n/gm,'').replaceAll('export function','function');
function ambiente(){
    const ids=new Map(), selecoes=[], justificativas=[], campos=[];
    const elemento=id=>{
        if(!ids.has(id))ids.set(id,{id,value:'',checked:false,hidden:false,textContent:'',innerHTML:'',dataset:{},handlers:{},attrs:{},
            classList:{toggle(){}},setAttribute(k,v){this.attrs[k]=v;},removeAttribute(k){delete this.attrs[k];},
            focus(){this.focado=true;},scrollIntoView(){this.rolado=true;},replaceChildren(){},addEventListener(k,v){this.handlers[k]=v;}});
        return ids.get(id);
    };
    const chamadas=[],copiados=[];
    const ctx=vm.createContext({console,structuredClone,setTimeout,clearTimeout,AbortController,
        document:{getElementById:elemento,querySelectorAll:s=>s==='[data-decisao]'?selecoes:s==='[data-justificativa]'?justificativas:s==='[data-contrato-campo]'?campos:[]},
        navigator:{clipboard:{writeText:async texto=>copiados.push(texto)}},
        escaparHtml:t=>String(t).replaceAll('<','&lt;').replaceAll('>','&gt;'),
        requisicaoOriginal:async(...args)=>{chamadas.push(args);if(ctx.erro)throw ctx.erro;return ctx.resposta;}
    });
    vm.runInContext(codigo+'\niniciarContratos();',ctx);
    const rodar=code=>vm.runInContext(code,ctx);
    function trabalho(pendentes=false){
        ctx.entrada={id:'teste',versao:1,confrontoAtual:true,dados:{ficha:{matricula:{numero:'1'}},confronto:{comparacoes:pendentes?[{campo:'imovel.area',situacao:'REVISAR'}]:[]}}};
        rodar('trabalho=entrada');
    }
    const esperar=()=>new Promise(resolve=>setImmediate(resolve));
    async function clicar(id){const el=elemento('contratos-'+id);el.handlers.click({target:el});await esperar();await esperar();}
    return {ctx,rodar,trabalho,elemento,selecoes,justificativas,campos,chamadas,copiados,clicar};
}

test('campos compatíveis não mostram decisão nem o aviso de outra operação',()=>{
    const a=ambiente();a.ctx.campo={campo:'imovel.quadra',contrato:'04',matricula:'4',situacao:'COMPATIVEL'};
    const html=a.rodar('quadroComparacao(campo)');
    assert.match(html,/Compatível/);assert.doesNotMatch(html,/data-decisao|operação anterior/);
});
test('confirmação ausente avisa junto ao botão e não chama API',async()=>{
    const a=ambiente();a.trabalho();await a.clicar('gerar');
    assert.match(a.elemento('contratos-geracao-status').textContent,/Marque a confirmação/);
    assert.equal(a.chamadas.length,0);assert.equal(a.elemento('contratos-gerar').disabled,false);
});
test('decisão e justificativa ausentes identificam o campo',()=>{
    const a=ambiente();a.trabalho(true);
    assert.match(a.rodar('pendenciaGeracao().texto'),/Imóvel · Área/);
    a.selecoes.push({dataset:{decisao:'imovel.area'},value:'CONTRATO'});
    assert.match(a.rodar('pendenciaGeracao().texto'),/justificativa/);
});
test('resultado antigo exige reconfrontar antes de gerar',async()=>{
    const a=ambiente();a.trabalho();a.rodar('trabalho.confrontoAtual=false');await a.clicar('gerar');
    assert.match(a.elemento('contratos-geracao-status').textContent,/regras anteriores/);
    assert.equal(a.chamadas.length,0);
});
test('erro HTTP é exibido junto ao botão e mantém botão utilizável',async()=>{
    const a=ambiente();a.trabalho();a.elemento('contratos-confirmacao').checked=true;
    a.ctx.erro=Object.assign(new Error('Falha de teste'),{identificador:'req-teste'});
    await a.clicar('gerar');assert.match(a.elemento('contratos-geracao-status').textContent,/Falha de teste.*req-teste/);
    assert.equal(a.elemento('contratos-gerar').disabled,false);
});
test('geração bem sucedida oferece cópia e prévia somente leitura',async()=>{
    const a=ambiente();a.trabalho();a.elemento('contratos-confirmacao').checked=true;
    a.ctx.resposta=structuredClone(a.ctx.entrada);a.ctx.resposta.dados.minutas={venda:{texto:'ATO VENDA',pendencias:[]},alienacao:{texto:'ATO ALIENACAO',pendencias:[]}};
    // O render completo é verificado no navegador; aqui isolamos a ação assíncrona.
    a.rodar('desenhar=()=>{}');await a.clicar('gerar');
    assert.match(a.elemento('contratos-geracao-status').textContent,/Minuta gerada/);
    assert.equal(a.chamadas.length,1);
    await a.clicar('copiar');assert.equal(a.copiados[0],'ATO VENDA\n\nATO ALIENACAO');
    const template=readFileSync(new URL('../backend/templates/contratos.html',import.meta.url),'utf8');
    assert.match(template,/contratos-minuta-venda-preview/);
    assert.match(template,/contratos-minuta-alienacao-preview/);
    assert.doesNotMatch(template,/<textarea|contratos-texto-btn|Salvar versão editada/);
});
test('ficha oculta campos técnicos e oferece escolhas controladas',()=>{
    const a=ambiente();
    a.ctx.obj={contrato:{numero:'1',modelo:'MO123',modalidade:'NOVO'},vendedores:[{tipo:'fisica',sexo:'F',estado_civil:'casado',documento:{tipo:'RG'}}]};
    const lista=a.rodar('campos(obj)');
    assert.deepEqual(Array.from(lista,x=>x.campo),['contrato.numero','vendedores.0.sexo','vendedores.0.estado_civil','vendedores.0.documento.tipo']);
    assert.match(a.rodar("campoFichaHtml({campo:'vendedores.0.sexo',valor:'F'},{evidencias:{}})"),/type="radio"[^>]*data-contrato-campo="vendedores\.0\.sexo"/);
    assert.match(a.rodar("campoFichaHtml({campo:'vendedores.0.documento.tipo',valor:'RG'},{evidencias:{}})"),/value="RG"[^>]*checked/);
});
test('desenho mostra prévia, representante e cadeia de procurações automáticos',()=>{
    const a=ambiente();
    a.ctx.entrada={id:'teste',confrontoAtual:true,dados:{ficha:{contrato:{},vendedores:[],compradores:[],credora:{representante:{nome:'ANA TESTE'},procuracoes:[{especie:'Procuração'}]},valores:{},financiamento:{},matricula:{numero:'1'}},alertasExtracao:[],evidencias:{},minutas:{venda:{texto:'MINUTA VENDA',pendencias:[]},alienacao:{texto:'MINUTA ALIENACAO',pendencias:[]}}}};
    a.rodar('trabalho=entrada;desenhar()');
    assert.equal(a.elemento('contratos-minuta-venda-preview').textContent,'MINUTA VENDA');
    assert.equal(a.elemento('contratos-minuta-alienacao-preview').textContent,'MINUTA ALIENACAO');
    assert.match(a.elemento('contratos-automatizacoes').innerHTML,/ANA TESTE[\s\S]*automaticamente[\s\S]*1 ato/);
    assert.doesNotMatch(a.elemento('contratos-alertas').innerHTML,/campos para conferência/);
});
test('resposta inválida nunca sinaliza sucesso de geração',async()=>{
    const a=ambiente();a.trabalho();a.elemento('contratos-confirmacao').checked=true;a.ctx.resposta=a.ctx.entrada;
    await a.clicar('gerar');assert.match(a.elemento('contratos-geracao-status').textContent,/não retornou os textos esperados/);
});
test('bloqueio do clipboard tem mensagem explícita, sem abrir editor',async()=>{
    const a=ambiente();a.trabalho();a.rodar("trabalho.dados.minutas={venda:{texto:'TESTE'},alienacao:{texto:'TESTE'}}");
    a.ctx.navigator.clipboard.writeText=async()=>{throw Object.assign(new Error(),{name:'NotAllowedError'});};
    await a.clicar('copiar');assert.match(a.elemento('contratos-copia-status').textContent,/bloqueou a cópia/);
});
test('edição posterior da ficha bloqueia copiar minuta desatualizada',async()=>{
    const a=ambiente();a.trabalho();a.campos.push({dataset:{contratoCampo:'matricula.numero'},type:'text',value:'2'});
    await a.clicar('copiar');assert.match(a.elemento('contratos-copia-status').textContent,/Ficha alterada/);assert.equal(a.copiados.length,0);
});
