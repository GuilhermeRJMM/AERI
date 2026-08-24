import {requisicaoAeri} from './api.js?v=20260820-robustez-v1';
import {escaparHtml} from './util.js';

let usuarios = [];
let divergenciasAnalise = [];
let catalogoPermissoes = [];
const CARGOS = [
    ['ADMIN', 'ADM'],
    ['SUBSTITUTO', 'Substituto'],
    ['AUDITOR', 'Auditor'],
    ['SUPERVISOR', 'Supervisor'],
    ['CONFERENTE', 'Conferente'],
    ['PRODUTOR', 'Produtor'],
];

function cargoAdministrativo(perfil) {
    return ['ADMIN', 'SUBSTITUTO'].includes(perfil);
}

function usuarioPodeCriarUsuarios() {
    return document.body.dataset.perfil === 'ADMIN';
}

function lerPermissoesFormulario() {
    return Object.fromEntries([...document.querySelectorAll('[data-permissao-form]')]
        .map(campo => [campo.dataset.permissaoForm, campo.checked]));
}

function renderizarAtribuicoes(item) {
    if (cargoAdministrativo(item.perfil)) return '<span class="usuario-status ativo">Todas</span>';
    const visiveis = item.perfil === 'AUDITOR'
        ? catalogoPermissoes.filter(permissao => permissao.auditorFixa || permissao.auditorOpcional)
        : catalogoPermissoes;
    return `<div class="usuario-atribuicoes-lista">${visiveis.map(permissao => `
        <label title="${escaparHtml(permissao.modulo)}"><input type="checkbox" data-acao="permissao"
            data-permissao="${permissao.chave}" data-usuario="${item.usuario}"
            ${item.permissoes?.[permissao.chave] ? 'checked' : ''}
            ${permissao.auditorFixa && item.perfil === 'AUDITOR' ? 'disabled' : ''}>
            ${escaparHtml(permissao.nome)}</label>
    `).join('')}</div>`;
}

function substituirUsuario(atualizado) {
    const indice = usuarios.findIndex(item => item.usuario === atualizado.usuario);
    if (indice >= 0) usuarios[indice] = atualizado;
}

function desenharPermissoesFormulario(marcadas = {}) {
    const alvo = document.getElementById('usuario-permissoes-catalogo');
    alvo.innerHTML = catalogoPermissoes.map(permissao => `<label title="${escaparHtml(permissao.modulo)}">
        <input type="checkbox" data-permissao-form="${permissao.chave}"
            ${marcadas[permissao.chave] !== false ? 'checked' : ''}>
        ${escaparHtml(permissao.nome)}
    </label>`).join('');
}

function atualizarAtribuicoesFormulario() {
    const perfil = document.getElementById('usuario-perfil').value;
    const admin = cargoAdministrativo(perfil);
    const auditor = perfil === 'AUDITOR';
    document.querySelectorAll('[data-permissao-form]').forEach(campo => {
        const chave = campo.dataset.permissaoForm;
        const definicao = catalogoPermissoes.find(item => item.chave === chave) || {};
        const opcional = Boolean(definicao.auditorOpcional);
        campo.disabled = admin || (auditor && !opcional);
        if (admin) campo.checked = true;
        // Só mexe no que o auditor não pode escolher. As opcionais ficam
        // como estão, para não desmarcar o que já foi concedido.
        if (auditor && !opcional) campo.checked = Boolean(definicao.auditorFixa);
    });
}

function senhaTemporaria() {
    const grupos = ['ABCDEFGHJKLMNPQRSTUVWXYZ', 'abcdefghijkmnopqrstuvwxyz', '23456789', '!@#$%&*_-'];
    const todos = grupos.join('');
    const bytes = crypto.getRandomValues(new Uint32Array(20));
    const senha = grupos.map((grupo, i) => grupo[bytes[i] % grupo.length]);
    for (let i = 4; i < 20; i++) senha.push(todos[bytes[i] % todos.length]);
    return senha.sort(() => crypto.getRandomValues(new Uint32Array(1))[0] / 2**32 - .5).join('');
}

/**
 * Mostra a senha temporária na própria página.
 *
 * Era window.prompt, que o Chrome bloqueia em iframe de outra origem
 * desde a versão 92 -- e o AERI roda dentro do SYNC. Ali o prompt
 * devolve null na hora, sem exibir nada: quem criava o usuário não via
 * senha alguma e não recebia aviso de que algo tinha falhado.
 */
function revelarSenha(titulo, senha) {
    document.getElementById('senha-gerada-titulo').textContent = titulo;
    document.getElementById('senha-gerada-valor').textContent = senha;
    document.getElementById('senha-gerada-status').textContent = '';
    document.getElementById('modal-senha-gerada').hidden = false;
}

async function copiarSenhaRevelada() {
    const senha = document.getElementById('senha-gerada-valor').textContent;
    const status = document.getElementById('senha-gerada-status');
    // execCommand antes da API assíncrona: dentro do iframe do SYNC a
    // segunda é bloqueada por permissão, como já vimos na Pesquisa
    // Qualificada e nas coordenadas do módulo Polígonos.
    const campo = document.createElement('textarea');
    campo.value = senha;
    campo.setAttribute('readonly', '');
    campo.style.cssText = 'position:fixed;top:-1000px;opacity:0';
    document.body.appendChild(campo);
    campo.select();
    let copiou = false;
    try { copiou = document.execCommand('copy'); } catch (_e) { copiou = false; }
    campo.remove();
    if (!copiou) {
        try { await navigator.clipboard.writeText(senha); copiou = true; } catch (_e) { copiou = false; }
    }
    status.textContent = copiou
        ? 'Senha copiada.'
        : 'Não foi possível copiar. Selecione a senha acima e use Ctrl+C.';
}

function renderizarUsuarios() {
    const tbody = document.getElementById('usuarios-tbody');
    document.getElementById('btn-novo-usuario').hidden = !usuarioPodeCriarUsuarios();
    tbody.innerHTML = usuarios.map(item => `
        <tr>
            <td><strong>${escaparHtml(item.nome)}</strong></td>
            <td>${escaparHtml(item.usuario)}</td>
            <td><select class="usuario-perfil-select" data-acao="perfil" data-usuario="${item.usuario}">
                ${CARGOS.map(([perfil, rotulo]) => `<option value="${perfil}" ${perfil === item.perfil ? 'selected' : ''}>${rotulo}</option>`).join('')}
            </select></td>
            <td>${renderizarAtribuicoes(item)}</td>
            <td><span class="usuario-status ${item.ativo ? 'ativo' : 'inativo'}">${item.ativo ? 'Ativo' : 'Bloqueado'}</span></td>
            <td>${item.deveTrocarSenha ? '<span class="usuario-status inativo">Troca pendente</span>' : 'Definida'}</td>
            <td><div class="rotina-row-actions">
                <button data-acao="senha" data-usuario="${item.usuario}">Redefinir senha</button>
                <button data-acao="ativo" data-usuario="${item.usuario}" class="${item.ativo ? 'perigo' : ''}">${item.ativo ? 'Bloquear' : 'Reativar'}</button>
            </div></td>
        </tr>`).join('') || '<tr><td colspan="7" class="rotina-vazio">Nenhum usuário encontrado.</td></tr>';
}

function renderizarDivergencias() {
    const tbody = document.getElementById('divergencias-tbody');
    if (!tbody) return;
    tbody.innerHTML = divergenciasAnalise.map(item => `
        <tr>
            <td><strong>${escaparHtml(item.numero_matricula)}</strong><small>Motor ${escaparHtml(item.motor_versao)}</small></td>
            <td>${(item.dominios || []).map(dominio => `<span class="usuario-status inativo">${escaparHtml(dominio)}</span>`).join(' ')}</td>
            <td>${escaparHtml(item.comentario || '—')}</td>
            <td>${escaparHtml(item.criado_por)}</td>
            <td>${new Intl.DateTimeFormat('pt-BR', {dateStyle:'short', timeStyle:'short'}).format(new Date(item.criado_em))}</td>
            <td><div class="rotina-row-actions">
                <button data-acao-divergencia="resolver" data-divergencia="${item.id}" class="rotina-check">Resolver</button>
                <button data-acao-divergencia="arquivar" data-divergencia="${item.id}" class="perigo">Arquivar</button>
            </div></td>
        </tr>`).join('') || '<tr><td colspan="6" class="rotina-vazio">Nenhuma divergência pendente.</td></tr>';
}

export async function carregarUsuarios() {
    if (!cargoAdministrativo(document.body.dataset.perfil)) return;
    const [lista, auditoria, divergencias, catalogo] = await Promise.all([
        requisicaoAeri('/api/usuarios'),
        requisicaoAeri('/api/usuarios/auditoria'),
        requisicaoAeri('/analisar/divergencias?status=PENDENTE'),
        requisicaoAeri('/api/usuarios/permissoes/catalogo'),
    ]);
    usuarios = lista;
    divergenciasAnalise = divergencias;
    catalogoPermissoes = catalogo;
    desenharPermissoesFormulario();
    renderizarUsuarios();
    renderizarDivergencias();
    document.getElementById('auditoria-tbody').innerHTML = auditoria.map(item => `<tr>
        <td>${new Intl.DateTimeFormat('pt-BR', {dateStyle:'short', timeStyle:'short'}).format(new Date(item.criada_em))}</td>
        <td>${escaparHtml(item.usuario || '—')}</td><td>${escaparHtml(item.acao)}</td>
        <td>${escaparHtml(item.recurso || '—')}</td><td>${escaparHtml(item.resultado)}</td><td>${escaparHtml(item.ip || '—')}</td>
    </tr>`).join('') || '<tr><td colspan="6" class="rotina-vazio">Nenhuma atividade registrada.</td></tr>';
}

function abrirNovoUsuario() {
    if (!usuarioPodeCriarUsuarios()) return;
    document.getElementById('form-usuario').reset();
    document.getElementById('usuario-senha').value = senhaTemporaria();
    desenharPermissoesFormulario();
    atualizarAtribuicoesFormulario();
    document.getElementById('modal-usuario').classList.add('aberta');
    document.getElementById('usuario-nome').focus();
}

function fecharNovoUsuario() { document.getElementById('modal-usuario').classList.remove('aberta'); }

async function salvarUsuario(evento) {
    evento.preventDefault();
    const dados = {
        nome: document.getElementById('usuario-nome').value.trim(),
        usuario: document.getElementById('usuario-login').value.trim(),
        perfil: document.getElementById('usuario-perfil').value,
        senha: document.getElementById('usuario-senha').value,
        permissoes: lerPermissoesFormulario(),
    };
    try {
        await requisicaoAeri('/api/usuarios', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(dados)});
        fecharNovoUsuario();
        await carregarUsuarios();
        revelarSenha(`Senha temporária de ${dados.usuario.toUpperCase()}`, dados.senha);
    } catch (erro) { alert(erro.message); }
}

async function atualizar(item, alteracoes) {
    const dados = {usuario:item.usuario, nome:item.nome, perfil:item.perfil, ativo:item.ativo, permissoes:item.permissoes || {}, ...alteracoes};
    const salvo = await requisicaoAeri(`/api/usuarios/${item.usuario}`, {method:'PUT', headers:{'Content-Type':'application/json'}, body:JSON.stringify(dados)});
    substituirUsuario(salvo);
    renderizarUsuarios();
    return salvo;
}

async function acaoTabela(evento) {
    const alvo = evento.target.closest('[data-acao]');
    if (!alvo) return;
    const item = usuarios.find(usuario => usuario.usuario === alvo.dataset.usuario);
    if (!item) return;
    try {
        if (alvo.dataset.acao === 'perfil' && evento.type === 'change') await atualizar(item, {perfil:alvo.value});
        if (alvo.dataset.acao === 'permissao' && evento.type === 'change') {
            alvo.disabled = true;
            const salvo = await requisicaoAeri(
                `/api/usuarios/${item.usuario}/permissoes/${alvo.dataset.permissao}`,
                {method:'PATCH', headers:{'Content-Type':'application/json'}, body:JSON.stringify({concedida:alvo.checked})},
            );
            substituirUsuario(salvo);
            renderizarUsuarios();
        }
        if (alvo.dataset.acao === 'ativo') await atualizar(item, {ativo:!item.ativo});
        if (alvo.dataset.acao === 'senha') {
            const senha = senhaTemporaria();
            if (!confirm(`Redefinir a senha de ${item.usuario}?`)) return;
            await requisicaoAeri(`/api/usuarios/${item.usuario}/redefinir-senha`, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({senha})});
            await carregarUsuarios();
            revelarSenha(`Nova senha temporária de ${item.usuario}`, senha);
        }
    } catch (erro) { alert(erro.message); await carregarUsuarios(); }
}

async function acaoDivergencia(evento) {
    const alvo = evento.target.closest('[data-acao-divergencia]');
    if (!alvo) return;
    const acao = alvo.dataset.acaoDivergencia;
    const identificador = alvo.dataset.divergencia;
    if (!identificador || !['resolver', 'arquivar'].includes(acao)) return;
    const resolucao = window.prompt(
        acao === 'resolver' ? 'Como a divergência foi resolvida?' : 'Motivo do arquivamento:',
        '',
    );
    if (resolucao === null) return;
    try {
        await requisicaoAeri(`/analisar/divergencias/${identificador}/resolver`, {
            method:'POST', headers:{'Content-Type':'application/json'},
            body:JSON.stringify({status: acao === 'resolver' ? 'RESOLVIDA' : 'ARQUIVADA', resolucao}),
        });
        divergenciasAnalise = divergenciasAnalise.filter(item => item.id !== identificador);
        renderizarDivergencias();
    } catch (erro) {
        alert(erro.message);
        await carregarUsuarios();
    }
}

export function abrirTrocaSenha(obrigatoria = false) {
    document.getElementById('btn-fechar-troca-senha').hidden = obrigatoria;
    document.getElementById('modal-trocar-senha').classList.add('aberta');
}

export function exigirTrocaSenha(deveTrocar) {
    if (deveTrocar) abrirTrocaSenha(true);
    else document.getElementById('modal-trocar-senha').classList.remove('aberta');
}

async function trocarSenha(evento) {
    evento.preventDefault();
    const atual = document.getElementById('senha-atual').value;
    const nova = document.getElementById('senha-nova').value;
    const confirmar = document.getElementById('senha-confirmar').value;
    const erro = document.getElementById('troca-senha-erro');
    if (nova !== confirmar) { erro.textContent = 'As novas senhas não coincidem.'; return; }
    try {
        await requisicaoAeri('/api/usuarios/minha-senha/trocar', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({senhaAtual:atual, novaSenha:nova})});
        document.getElementById('form-trocar-senha').reset();
        erro.textContent = '';
        exigirTrocaSenha(false);
        window.location.reload();
    } catch (falha) { erro.textContent = falha.message; }
}

export function iniciarUsuarios() {
    document.getElementById('btn-novo-usuario').addEventListener('click', abrirNovoUsuario);
    document.getElementById('btn-fechar-usuario').addEventListener('click', fecharNovoUsuario);
    document.getElementById('btn-cancelar-usuario').addEventListener('click', fecharNovoUsuario);
    document.getElementById('btn-gerar-senha').addEventListener('click', () => { document.getElementById('usuario-senha').value = senhaTemporaria(); });
    document.getElementById('usuario-perfil').addEventListener('change', atualizarAtribuicoesFormulario);
    document.getElementById('form-usuario').addEventListener('submit', salvarUsuario);
    document.getElementById('usuarios-tbody').addEventListener('change', acaoTabela);
    document.getElementById('usuarios-tbody').addEventListener('click', acaoTabela);
    document.getElementById('divergencias-tbody')?.addEventListener('click', acaoDivergencia);
    document.getElementById('form-trocar-senha').addEventListener('submit', trocarSenha);
    document.getElementById('btn-minha-senha').addEventListener('click', () => abrirTrocaSenha(false));
    document.getElementById('btn-fechar-troca-senha').addEventListener('click', () => exigirTrocaSenha(false));
    document.getElementById('btn-copiar-senha-gerada').addEventListener('click', copiarSenhaRevelada);
    document.getElementById('btn-fechar-senha-gerada').addEventListener('click', () => {
        document.getElementById('modal-senha-gerada').hidden = true;
        document.getElementById('senha-gerada-valor').textContent = '';
    });
}
