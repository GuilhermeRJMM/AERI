import {requisicaoAeri} from './api.js?v=20260902-arquivo-v1';
import {escaparHtml} from './util.js';
import {mostrarPagina} from './navegacao.js?v=20260831-setores-v1';

let versao = 0;
export async function carregarPainel() {
    const atual = ++versao;
    try {
        const dados = await requisicaoAeri('/api/painel');
        if (atual !== versao) return;
        for (const setor of ['certidao','rgi','sistema']) {
            const modulos = dados.modulos.filter(m => m.setor === setor);
            const grade = document.getElementById(`grade-${setor}`);
            grade.innerHTML = modulos.map(m => `<button class="ferramenta-card" type="button" data-destino="${m.id}">
                <span class="card-grupo">${escaparHtml(m.grupo)}</span><h3>${escaparHtml(m.nome)}</h3>
                <p>${escaparHtml(m.descricao)}</p><span class="card-abrir">Abrir ferramenta <span aria-hidden="true">↗</span></span></button>`).join('') || '<p class="painel-vazio">Nenhuma ferramenta liberada neste setor. Solicite acesso à administração.</p>';
            const contador = document.getElementById(`total-${setor}`);
            if (contador) contador.textContent = `${modulos.length} ferramentas disponíveis`;
        }
        const alertas = document.getElementById('painel-alertas');
        alertas.innerHTML = dados.alertas.map(a => `<button type="button" class="painel-alerta ${a.total || (a.estado && a.estado !== 'CONCLUIDO') ? 'com-alerta' : ''}" data-alerta="${a.modulo}">
            <strong>${escaparHtml(a.titulo)}</strong><span>${escaparHtml(a.mensagem)}</span>
            <small>${a.atualizadoEm ? `Verificado em ${new Date(a.atualizadoEm).toLocaleString('pt-BR')}` : 'Aguardando primeira verificação'}</small></button>`).join('');
        document.getElementById('painel-erro').textContent = '';
    } catch (erro) {
        if (atual === versao) document.getElementById('painel-erro').textContent = erro.message;
    }
}
export function limparPainel() {
    versao++;
    for (const id of ['grade-certidao','grade-rgi','grade-sistema','painel-alertas']) document.getElementById(id).replaceChildren();
}
export function iniciarPainel() {
    document.addEventListener('click', e => {
        const botao = e.target.closest('[data-alerta]');
        if (!botao) return;
        mostrarPagina(botao.dataset.alerta);
        window.dispatchEvent(new CustomEvent('aeri:abrir-alerta', {detail:{modulo:botao.dataset.alerta}}));
    });
}
