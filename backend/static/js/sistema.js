import {requisicaoAeri} from './api.js?v=20260902-arquivo-v1';
import {escaparHtml} from './util.js';
let geracao=0;
export function limparSistema(){geracao++;document.getElementById('sistema-conteudo').replaceChildren();document.getElementById('sistema-mensagem').textContent='';}
export async function carregarSistema() {
    const atual=++geracao;
    const alvo = document.getElementById('sistema-conteudo');
    alvo.textContent = 'Carregando configurações…';
    try {
        const dados = await requisicaoAeri('/api/sistema/configuracao');
        if(atual!==geracao)return;
        alvo.innerHTML = `<section class="sistema-card"><h2>Integração — Ofício Eletrônico</h2><p>Status público e webhook existente preservados.</p><p>Webhook: ${dados.oficio.webhookConfigurado ? 'configurado' : 'não configurado'}. Credenciais permanecem exclusivamente no servidor.</p></section>
            <p class="contratos-aviso">${escaparHtml(dados.executor)}</p>` + dados.agendas.map(a => `<section class="sistema-card"><h2>${a.chave === 'intimacoes' ? 'Intimações' : 'Livro de Protocolos'}</h2>
            <form data-agenda="${a.chave}"><label>Execução<select name="habilitada"><option value="false">Desativada</option><option value="true" ${a.habilitada ? 'selected' : ''}>Ativada</option></select></label>
            <label>Intervalo (minutos)<input name="intervalo_minutos" type="number" min="15" max="1440" value="${a.intervalo_minutos}" required></label>
            <label>Das (hora)<input name="hora_inicio" type="number" min="0" max="23" value="${a.hora_inicio}" required></label>
            <label>Até (hora)<input name="hora_fim" type="number" min="1" max="24" value="${a.hora_fim}" required></label>
            <label>Dias (0=segunda, 6=domingo)<input name="dias_semana" value="${a.dias_semana.join(',')}" required></label><button type="submit" class="btn btn-primary">Salvar</button></form>
            <p>Último sucesso: ${a.ultimo_sucesso ? new Date(a.ultimo_sucesso).toLocaleString('pt-BR') : 'Ainda não executado'} · Horário de Brasília</p></section>`).join('') +
            `<section class="sistema-card"><h2>Últimas execuções</h2>${dados.execucoes.map(e => `<p>${escaparHtml(e.chave)} · ${new Date(e.inicio).toLocaleString('pt-BR')} · ${escaparHtml(e.estado)} · ${e.protocolos} protocolos · ${e.ocorrencias} ocorrências · ${e.duracao_ms || 0} ms ${e.erro ? '· '+escaparHtml(e.erro) : ''}</p>`).join('') || '<p>Nenhuma execução registrada.</p>'}</section>`;
    } catch (erro) { if(atual===geracao)alvo.textContent = erro.message; }
}
export function iniciarSistema() {
    document.getElementById('sistema-conteudo').addEventListener('submit',async e => {
        const form = e.target.closest('[data-agenda]'); if (!form) return; e.preventDefault();
        const b=form.querySelector('button'); b.disabled=true;
        try {
            const campos = Object.fromEntries(new FormData(form));
            const dados={habilitada:campos.habilitada==='true',intervalo_minutos:Number(campos.intervalo_minutos),hora_inicio:Number(campos.hora_inicio),hora_fim:Number(campos.hora_fim),dias_semana:campos.dias_semana.split(',').map(Number)};
            await requisicaoAeri(`/api/sistema/agendas/${form.dataset.agenda}`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(dados)});
            document.getElementById('sistema-mensagem').textContent='Salvo. A execução depende do worker operacional ativo.';
        } catch(erro) { document.getElementById('sistema-mensagem').textContent=erro.message; } finally {b.disabled=false;}
    });
}
