import {requisicaoAeri} from './api.js?v=20260902-arquivo-v1';
import {escaparHtml} from './util.js';

let captura = null;
let itens = new Map();
let geracao = 0;
let ultimaTentativa = 0;
let requisicao = null;
let redesenhar = () => {};
let contexto = 0;
let emCurso = false;
let trabalhoController = null;
let codigoTimer = null;

function informar(texto) {
    const aviso = document.getElementById('oficio-consulta-aviso');
    if (aviso) aviso.textContent = texto;
}

function dataHora(valor) {
    const data = new Date(valor);
    return Number.isFinite(data.getTime()) ? data.toLocaleString('pt-BR') : 'data não disponível';
}

function resumo() {
    if (!captura?.disponivel) return 'Nenhuma consulta realizada. Use Consultar agora; seus INs e conferências continuam preservados.';
    return `Consultado em ${dataHora(captura.consultadoEm)} · ${captura.totalConsultado} INs históricos lidos · ${captura.totalVinculado} vinculados aos cadastros ativos. Não é a contagem de pedidos em tratativa.`;
}

export function limparConsultaOficio() {
    contexto++;
    emCurso = false;
    trabalhoController?.abort();
    trabalhoController = null;
    clearTimeout(codigoTimer);
    const codigo = document.getElementById('oficio-conector-codigo');
    if (codigo) codigo.value = '';
    document.getElementById('oficio-conector-pareamento')?.setAttribute('hidden','');
    const botao = document.getElementById('oficio-consultar-agora');
    if (botao) botao.disabled = false;
    geracao++;
    requisicao?.abort();
    requisicao = null;
    ultimaTentativa = 0;
    captura = null;
    itens.clear();
    informar('');
}

export async function carregarConsultaOficio(forcar = false) {
    if (!forcar && Date.now() - ultimaTentativa < 60000) return;
    const atual = ++geracao;
    requisicao?.abort();
    const controller = new AbortController();
    requisicao = controller;
    ultimaTentativa = Date.now();
    try {
        const dados = await requisicaoAeri('/api/oficio-consultas', {background:true, signal:controller.signal});
        if (atual !== geracao) return;
        captura = dados;
        itens = new Map((dados.itens || []).map(item => [item.protocolo, item]));
        informar(resumo());
    } catch (erro) {
        if (atual !== geracao || erro.name === 'AbortError') return;
        // Nunca manter um status antigo como se a atualização tivesse funcionado.
        captura = null;
        itens.clear();
        informar(`Consulta do Ofício indisponível. ${erro.message} Seus cadastros não foram alterados.`);
    } finally {
        if (atual === geracao) { requisicao = null; redesenhar(); }
    }
}

export function statusOficioHtml(protocolo) {
    const item = itens.get(protocolo);
    const antigo = captura?.disponivel && Date.now() - new Date(captura.consultadoEm).getTime() > 86400000;
    const status = item?.status || (captura?.disponivel ? 'IN não localizado nesta captura' : 'Consulte antes de registrar');
    const detalhe = item ? `Data do status: ${item.dataStatus ? item.dataStatus.split('-').reverse().join('/') : 'não informada'} · Prenotação: ${item.prenotacao || 'não informada'}`
        : 'Ausência na captura não significa arquivamento ou ausência de andamento.';
    const pedido = item ? `<p>Pedido em ${escaparHtml(item.dataPedido ? item.dataPedido.split('-').reverse().join('/') : 'data não informada')}<br>Prazo de purga informado no portal: ${escaparHtml(item.prazoPurga || 'não informado')} (não recalculado).</p>` : '';
    return `<section class="mesa-consulta"><span class="mesa-rotulo">NO OFÍCIO ELETRÔNICO</span><strong>${escaparHtml(status)}</strong><p>${escaparHtml(detalhe)}</p>${pedido}${captura?.disponivel ? `<small>${antigo ? 'Consulta antiga — atualize antes de conferir. ' : ''}Captura de ${escaparHtml(dataHora(captura.consultadoEm))}</small>` : ''}<p>O status do portal não substitui a tarefa interna nem registra sua conferência.</p><a href="https://oficioeletronico.com.br/" target="_blank" rel="noopener noreferrer">Abrir Ofício Eletrônico ↗</a></section>`;
}

export function iniciarConsultaOficio(aoAtualizar, podeConsultar) {
    redesenhar = aoAtualizar;
    const botao = document.getElementById('oficio-consultar-agora');
    if (!botao || botao.dataset.iniciado) return;
    botao.dataset.iniciado = '1';
    document.getElementById('oficio-consulta-acoes').hidden = !podeConsultar();
    botao.addEventListener('click', async () => {
        if (emCurso || !podeConsultar()) return;
        emCurso = true;
        botao.disabled = true;
        const atual = contexto;
        const controller = new AbortController();
        trabalhoController = controller;
        informar('Solicitando consulta ao computador autorizado…');
        try {
            const trabalho = await requisicaoAeri('/api/oficio-consultas/trabalhos', {method:'POST',signal:controller.signal});
            const limite = Date.now() + 310000;
            while (atual === contexto && Date.now() < limite) {
                const estado = await requisicaoAeri(`/api/oficio-consultas/trabalhos/${encodeURIComponent(trabalho.id)}`,
                    {background:true,signal:controller.signal});
                if (atual !== contexto) return;
                if (estado.estado === 'PRONTO') break;
                if (estado.estado === 'ERRO') throw new Error(estado.mensagem || 'Consulta não concluída.');
                informar(estado.estado === 'LENDO' ? 'Lendo as páginas do Ofício… Nenhum andamento será alterado.'
                    : 'Aguardando o conector local. Autorize a conexão no Chrome, se solicitado.');
                await new Promise(resolve => setTimeout(resolve,2000));
            }
            if (atual !== contexto) return;
            if (Date.now() >= limite) throw new Error('Consulta expirou. Verifique se o conector está aberto.');
            await carregarConsultaOficio(true);
        } catch (erro) {
            if (atual === contexto && erro.name !== 'AbortError') informar(`Consulta não concluída. ${erro.message}`);
        } finally {
            if (atual === contexto) { emCurso = false; botao.disabled = false; trabalhoController = null; }
        }
    });
    document.getElementById('oficio-conectar-computador').addEventListener('click', async () => {
        const atual = contexto;
        try {
            const dados = await requisicaoAeri('/api/oficio-consultas/conectores',{method:'POST'});
            if (atual !== contexto) return;
            document.getElementById('oficio-conector-codigo').value = dados.codigo;
            document.getElementById('oficio-conector-pareamento').hidden = false;
            clearTimeout(codigoTimer);
            codigoTimer = setTimeout(() => {
                document.getElementById('oficio-conector-codigo').value = '';
                document.getElementById('oficio-conector-pareamento').hidden = true;
            },300000);
        } catch (erro) { if (atual === contexto) informar(erro.message); }
    });
    document.getElementById('oficio-copiar-codigo').addEventListener('click', async () => {
        try {
            await navigator.clipboard.writeText(document.getElementById('oficio-conector-codigo').value);
            informar('Código copiado. Cole somente no conector local; ele expira em 5 minutos.');
        } catch (_) { informar('Selecione e copie o código de conexão para o conector local.'); }
    });
    document.getElementById('oficio-revogar-conector').addEventListener('click', async () => {
        const atual = contexto;
        try {
            await requisicaoAeri('/api/oficio-consultas/conectores',{method:'DELETE'});
            if (atual !== contexto) return;
            limparConsultaOficio();
            informar('Conector desconectado. Nenhum pedido do Ofício foi alterado.');
            redesenhar();
        } catch (erro) { if (atual === contexto) informar(erro.message); }
    });
}
