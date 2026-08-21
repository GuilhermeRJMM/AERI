import {requisicaoAeri} from './api.js?v=20260820-robustez-v1';
import {escaparHtml} from './util.js';

let usuarios = [];
let divergenciasAnalise = [];
const salvamentosUsuarios = new Map();
const CARGOS = [
    ['ADMIN', 'ADM'],
    ['SUBSTITUTO', 'Substituto'],
    ['AUDITOR', 'Auditor'],
    ['SUPERVISOR', 'Supervisor'],
    ['CONFERENTE', 'Conferente'],
    ['PRODUTOR', 'Produtor'],
];
const ATRIBUICOES = [
    ['processar_matricula', 'Matrículas'],
    ['revisar_auditoria', 'Auditoria registral'],
    ['acessar_mapa_onr', 'MAPA-ONR'],
    ['acessar_livro_protocolos', 'Livro de Protocolos'],
    ['acessar_buscas', 'Buscas'],
    ['acessar_poligonos', 'Polígonos'],
    ['processar_incra', 'INCRA'],
    ['gerenciar_custas', 'Informar Custas'],
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
    if (item.perfil === 'AUDITOR') return `<div class="usuario-atribuicoes-lista">
        <span class="usuario-status ativo">Matrículas e auditoria registral</span>
        <label><input type="checkbox" data-acao="permissao" data-permissao="acessar_mapa_onr" data-usuario="${item.usuario}" ${item.permissoes?.acessar_mapa_onr ? 'checked' : ''}> MAPA-ONR</label>
        <label><input type="checkbox" data-acao="permissao" data-permissao="acessar_livro_protocolos" data-usuario="${item.usuario}" ${item.permissoes?.acessar_livro_protocolos ? 'checked' : ''}> Livro de Protocolos</label>
        <label><input type="checkbox" data-acao="permissao" data-permissao="acessar_buscas" data-usuario="${item.usuario}" ${item.permissoes?.acessar_buscas ? 'checked' : ''}> Buscas</label>
        <label><input type="checkbox" data-acao="permissao" data-permissao="acessar_poligonos" data-usuario="${item.usuario}" ${item.permissoes?.acessar_poligonos ? 'checked' : ''}> Polígonos</label>
    </div>`;
    return `<div class="usuario-atribuicoes-lista">${ATRIBUICOES.map(([chave, rotulo]) => `
        <label><input type="checkbox" data-acao="permissao" data-permissao="${chave}" data-usuario="${item.usuario}" ${item.permissoes?.[chave] ? 'checked' : ''}> ${rotulo}</label>
    `).join('')}</div>`;
}

function substituirUsuario(atualizado) {
    const indice = usuarios.findIndex(item => item.usuario === atualizado.usuario);
    if (indice >= 0) usuarios[indice] = atualizado;
}

// Espelham PERMISSOES_AUDITOR e PERMISSOES_OPCIONAIS_AUDITOR do
// autenticacao.py. Há teste exigindo que as listas sejam idênticas.
//
// Antes, esta tela tratava MAPA-ONR como a única opcional do AUDITOR, e
// as três criadas depois (Livro, Buscas, Polígonos) ficavam desmarcadas e
// travadas no formulário. Como salvar reenvia todas as permissões de uma
// vez, abrir o cadastro de um auditor por qualquer motivo e salvar
// apagava as três -- sem erro e sem aviso.
const PERMISSOES_FIXAS_DO_AUDITOR = ['processar_matricula', 'revisar_auditoria'];
const PERMISSOES_OPCIONAIS_DO_AUDITOR = [
    'acessar_mapa_onr', 'acessar_livro_protocolos', 'acessar_buscas',
    'acessar_poligonos',
];

function atualizarAtribuicoesFormulario() {
    const perfil = document.getElementById('usuario-perfil').value;
    const admin = cargoAdministrativo(perfil);
    const auditor = perfil === 'AUDITOR';
    document.querySelectorAll('[data-permissao-form]').forEach(campo => {
        const chave = campo.dataset.permissaoForm;
        const opcional = PERMISSOES_OPCIONAIS_DO_AUDITOR.includes(chave);
        campo.disabled = admin || (auditor && !opcional);
        if (admin) campo.checked = true;
        // Só mexe no que o auditor não pode escolher. As opcionais ficam
        // como estão, para não desmarcar o que já foi concedido.
        if (auditor && !opcional) campo.checked = PERMISSOES_FIXAS_DO_AUDITOR.includes(chave);
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
    const [lista, auditoria, divergencias] = await Promise.all([
        requisicaoAeri('/api/usuarios'),
        requisicaoAeri('/api/usuarios/auditoria'),
        requisicaoAeri('/analisar/divergencias?status=PENDENTE'),
    ]);
    usuarios = lista;
    divergenciasAnalise = divergencias;
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
}
