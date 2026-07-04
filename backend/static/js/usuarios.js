import {requisicaoAeri} from './api.js';
import {escaparHtml} from './util.js';

let usuarios = [];

function senhaTemporaria() {
    const grupos = ['ABCDEFGHJKLMNPQRSTUVWXYZ', 'abcdefghijkmnopqrstuvwxyz', '23456789', '!@#$%&*_-'];
    const todos = grupos.join('');
    const bytes = crypto.getRandomValues(new Uint32Array(20));
    const senha = grupos.map((grupo, i) => grupo[bytes[i] % grupo.length]);
    for (let i = 4; i < 20; i++) senha.push(todos[bytes[i] % todos.length]);
    return senha.sort(() => crypto.getRandomValues(new Uint32Array(1))[0] / 2**32 - .5).join('');
}

function renderizarUsuarios() {
    const tbody = document.getElementById('usuarios-tbody');
    tbody.innerHTML = usuarios.map(item => `
        <tr>
            <td><strong>${escaparHtml(item.nome)}</strong></td>
            <td>${escaparHtml(item.usuario)}</td>
            <td><select class="usuario-perfil-select" data-acao="perfil" data-usuario="${item.usuario}">
                ${['ADMIN','OPERADOR','CONSULTA'].map(perfil => `<option value="${perfil}" ${perfil === item.perfil ? 'selected' : ''}>${perfil}</option>`).join('')}
            </select></td>
            <td><span class="usuario-status ${item.ativo ? 'ativo' : 'inativo'}">${item.ativo ? 'Ativo' : 'Bloqueado'}</span></td>
            <td>${item.deveTrocarSenha ? '<span class="usuario-status inativo">Troca pendente</span>' : 'Definida'}</td>
            <td><div class="rotina-row-actions">
                <button data-acao="senha" data-usuario="${item.usuario}">Redefinir senha</button>
                <button data-acao="ativo" data-usuario="${item.usuario}" class="${item.ativo ? 'perigo' : ''}">${item.ativo ? 'Bloquear' : 'Reativar'}</button>
            </div></td>
        </tr>`).join('') || '<tr><td colspan="6" class="rotina-vazio">Nenhum usuário encontrado.</td></tr>';
}

export async function carregarUsuarios() {
    if (document.body.dataset.perfil !== 'ADMIN') return;
    const [lista, auditoria] = await Promise.all([
        requisicaoAeri('/api/usuarios'), requisicaoAeri('/api/usuarios/auditoria'),
    ]);
    usuarios = lista;
    renderizarUsuarios();
    document.getElementById('auditoria-tbody').innerHTML = auditoria.map(item => `<tr>
        <td>${new Intl.DateTimeFormat('pt-BR', {dateStyle:'short', timeStyle:'short'}).format(new Date(item.criada_em))}</td>
        <td>${escaparHtml(item.usuario || '—')}</td><td>${escaparHtml(item.acao)}</td>
        <td>${escaparHtml(item.recurso || '—')}</td><td>${escaparHtml(item.resultado)}</td><td>${escaparHtml(item.ip || '—')}</td>
    </tr>`).join('') || '<tr><td colspan="6" class="rotina-vazio">Nenhuma atividade registrada.</td></tr>';
}

function abrirNovoUsuario() {
    document.getElementById('form-usuario').reset();
    document.getElementById('usuario-senha').value = senhaTemporaria();
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
    };
    try {
        await requisicaoAeri('/api/usuarios', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(dados)});
        fecharNovoUsuario();
        await carregarUsuarios();
        window.prompt(`Usuário ${dados.usuario.toUpperCase()} criado. Copie a senha temporária:`, dados.senha);
    } catch (erro) { alert(erro.message); }
}

async function atualizar(item, alteracoes) {
    const dados = {usuario:item.usuario, nome:item.nome, perfil:item.perfil, ativo:item.ativo, ...alteracoes};
    await requisicaoAeri(`/api/usuarios/${item.usuario}`, {method:'PUT', headers:{'Content-Type':'application/json'}, body:JSON.stringify(dados)});
    await carregarUsuarios();
}

async function acaoTabela(evento) {
    const alvo = evento.target.closest('[data-acao]');
    if (!alvo) return;
    const item = usuarios.find(usuario => usuario.usuario === alvo.dataset.usuario);
    if (!item) return;
    try {
        if (alvo.dataset.acao === 'perfil' && evento.type === 'change') await atualizar(item, {perfil:alvo.value});
        if (alvo.dataset.acao === 'ativo') await atualizar(item, {ativo:!item.ativo});
        if (alvo.dataset.acao === 'senha') {
            const senha = senhaTemporaria();
            if (!confirm(`Redefinir a senha de ${item.usuario}?`)) return;
            await requisicaoAeri(`/api/usuarios/${item.usuario}/redefinir-senha`, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({senha})});
            await carregarUsuarios();
            window.prompt(`Copie a nova senha temporária de ${item.usuario}:`, senha);
        }
    } catch (erro) { alert(erro.message); await carregarUsuarios(); }
}

export function exigirTrocaSenha(deveTrocar) {
    document.getElementById('modal-trocar-senha').classList.toggle('aberta', Boolean(deveTrocar));
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
    document.getElementById('form-usuario').addEventListener('submit', salvarUsuario);
    document.getElementById('usuarios-tbody').addEventListener('change', acaoTabela);
    document.getElementById('usuarios-tbody').addEventListener('click', acaoTabela);
    document.getElementById('form-trocar-senha').addEventListener('submit', trocarSenha);
}
