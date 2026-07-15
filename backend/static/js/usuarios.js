import {requisicaoAeri} from './api.js';
import {escaparHtml} from './util.js';

let usuarios = [];
let regrasAprendizado = [];
const salvamentosUsuarios = new Map();
const CARGOS = [
    ['ADMIN', 'ADM'],
    ['SUBSTITUTO', 'Substituto'],
    ['SUPERVISOR', 'Supervisor'],
    ['CONFERENTE', 'Conferente'],
    ['PRODUTOR', 'Produtor'],
];
const ATRIBUICOES = [
    ['processar_matricula', 'Matrículas'],
    ['processar_incra', 'INCRA'],
    ['ver_intimacoes', 'Ver intimações'],
    ['criar_intimacoes', 'Criar/importar'],
    ['alterar_intimacoes', 'Alterar'],
    ['conferir_intimacoes', 'Check'],
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
    return `<div class="usuario-atribuicoes-lista">${ATRIBUICOES.map(([chave, rotulo]) => `
        <label><input type="checkbox" data-acao="permissao" data-permissao="${chave}" data-usuario="${item.usuario}" ${item.permissoes?.[chave] ? 'checked' : ''}> ${rotulo}</label>
    `).join('')}</div>`;
}

function substituirUsuario(atualizado) {
    const indice = usuarios.findIndex(item => item.usuario === atualizado.usuario);
    if (indice >= 0) usuarios[indice] = atualizado;
}

function atualizarAtribuicoesFormulario() {
    const admin = cargoAdministrativo(document.getElementById('usuario-perfil').value);
    document.querySelectorAll('[data-permissao-form]').forEach(campo => {
        campo.disabled = admin;
        if (admin) campo.checked = true;
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

function renderizarAprendizado() {
    const tbody = document.getElementById('aprendizado-tbody');
    if (!tbody) return;
    tbody.innerHTML = regrasAprendizado.map(item => `
        <tr>
            <td><strong>${escaparHtml(item.expressao)}</strong><small>${escaparHtml(item.criado_por)}</small></td>
            <td><span class="usuario-status ativo">${escaparHtml(item.categoria)}</span></td>
            <td>${escaparHtml(item.tipo_onus || '—')}</td>
            <td>${item.votos}</td>
            <td>${escaparHtml(item.justificativa || '—')}</td>
            <td><div class="rotina-row-actions">
                <button data-acao-aprendizado="aprovar" data-regra="${item.id}" class="rotina-check">Aprovar</button>
                <button data-acao-aprendizado="rejeitar" data-regra="${item.id}" class="perigo">Rejeitar</button>
            </div></td>
        </tr>`).join('') || '<tr><td colspan="6" class="rotina-vazio">Nenhuma regra pendente.</td></tr>';
}

export async function carregarUsuarios() {
    if (!cargoAdministrativo(document.body.dataset.perfil)) return;
    const [lista, auditoria, aprendizado] = await Promise.all([
        requisicaoAeri('/api/usuarios'),
        requisicaoAeri('/api/usuarios/auditoria'),
        requisicaoAeri('/analisar/aprendizado/sugestoes?status=PENDENTE'),
    ]);
    usuarios = lista;
    regrasAprendizado = aprendizado;
    renderizarUsuarios();
    renderizarAprendizado();
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
    document.querySelectorAll('[data-permissao-form]').forEach(campo => { campo.checked = true; campo.disabled = false; });
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
        window.prompt(`Usuário ${dados.usuario.toUpperCase()} criado. Copie a senha temporária:`, dados.senha);
    } catch (erro) { alert(erro.message); }
}

async function atualizar(item, alteracoes) {
    const dados = {usuario:item.usuario, nome:item.nome, perfil:item.perfil, ativo:item.ativo, permissoes:item.permissoes || {}, ...alteracoes};
    const salvo = await requisicaoAeri(`/api/usuarios/${item.usuario}`, {method:'PUT', headers:{'Content-Type':'application/json'}, body:JSON.stringify(dados)});
    substituirUsuario(salvo);
    renderizarUsuarios();
    return salvo;
}

async function salvarUsuarioSerializado(usuario) {
    const estado = salvamentosUsuarios.get(usuario) || {salvando:false, pendente:false};
    if (estado.salvando) {
        estado.pendente = true;
        salvamentosUsuarios.set(usuario, estado);
        return;
    }
    estado.salvando = true;
    salvamentosUsuarios.set(usuario, estado);
    try {
        do {
            estado.pendente = false;
            const item = usuarios.find(atual => atual.usuario === usuario);
            if (!item) return;
            const salvo = await requisicaoAeri(`/api/usuarios/${usuario}`, {
                method:'PUT',
                headers:{'Content-Type':'application/json'},
                body:JSON.stringify({
                    usuario:item.usuario,
                    nome:item.nome,
                    perfil:item.perfil,
                    ativo:item.ativo,
                    permissoes:item.permissoes || {},
                }),
            });
            substituirUsuario(salvo);
        } while (estado.pendente);
    } catch (erro) {
        alert(erro.message);
        await carregarUsuarios();
    } finally {
        salvamentosUsuarios.delete(usuario);
        renderizarUsuarios();
    }
}

async function acaoTabela(evento) {
    const alvo = evento.target.closest('[data-acao]');
    if (!alvo) return;
    const item = usuarios.find(usuario => usuario.usuario === alvo.dataset.usuario);
    if (!item) return;
    try {
        if (alvo.dataset.acao === 'perfil' && evento.type === 'change') await atualizar(item, {perfil:alvo.value});
        if (alvo.dataset.acao === 'permissao' && evento.type === 'change') {
            item.permissoes = {...(item.permissoes || {}), [alvo.dataset.permissao]:alvo.checked};
            salvarUsuarioSerializado(item.usuario);
        }
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

async function acaoAprendizado(evento) {
    const alvo = evento.target.closest('[data-acao-aprendizado]');
    if (!alvo) return;
    const acao = alvo.dataset.acaoAprendizado;
    const regra = alvo.dataset.regra;
    if (!regra || !['aprovar', 'rejeitar'].includes(acao)) return;
    try {
        await requisicaoAeri(`/analisar/aprendizado/sugestoes/${regra}/${acao}`, {method:'POST'});
        regrasAprendizado = regrasAprendizado.filter(item => item.id !== regra);
        renderizarAprendizado();
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
    document.getElementById('aprendizado-tbody')?.addEventListener('click', acaoAprendizado);
    document.getElementById('form-trocar-senha').addEventListener('submit', trocarSenha);
    document.getElementById('btn-minha-senha').addEventListener('click', () => abrirTrocaSenha(false));
    document.getElementById('btn-fechar-troca-senha').addEventListener('click', () => exigirTrocaSenha(false));
}
