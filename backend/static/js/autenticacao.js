import {definirCsrfToken, requisicaoAeri} from './api.js';

let autenticado = false;
let aoEntrar = () => {};
let aoSair = () => {};

function definirModuloVisivel(pageId, visivel) {
    const item = document.querySelector(`.nav-item[data-page="${pageId}"]`);
    if (!item) return;
    item.dataset.autorizado = String(visivel);
    item.hidden = !visivel;
}

function aplicarPermissoesSidebar(dados) {
    const admin = ['ADMIN', 'SUBSTITUTO'].includes(dados.perfil);
    const permissoes = dados.permissoes || {};
    definirModuloVisivel('onus', admin || Boolean(permissoes.processar_matricula));
    definirModuloVisivel('incra', admin || Boolean(permissoes.processar_incra));
    definirModuloVisivel('rotina', admin || Boolean(permissoes.ver_intimacoes));
    definirModuloVisivel('usuarios', admin);

    const ativo = document.querySelector('.nav-item.active');
    if (ativo?.hidden) {
        ativo.classList.remove('active');
        document.querySelectorAll('.page.active').forEach(pagina => pagina.classList.remove('active'));
        const proximo = [...document.querySelectorAll('.nav-item')].find(item => !item.hidden);
        if (proximo) {
            proximo.classList.add('active');
            document.getElementById(`page-${proximo.dataset.page}`)?.classList.add('active');
        }
    }
}

function abrirLogin() {
    document.body.classList.add('auth-pending');
    const saudacao = document.getElementById('saudacao-usuario');
    if (saudacao) saudacao.textContent = '';
    document.getElementById('login-aeri').classList.add('aberto');
    window.setTimeout(() => document.getElementById('login-usuario').focus(), 80);
}

function primeiroNome(valor) {
    const nome = String(valor || '').trim().split(/\s+/)[0] || 'Usuário';
    return nome.charAt(0).toLocaleUpperCase('pt-BR') + nome.slice(1).toLocaleLowerCase('pt-BR');
}

function atualizarSaudacaoUsuario(dados) {
    const saudacao = document.getElementById('saudacao-usuario');
    if (!saudacao) return;
    saudacao.textContent = '';
    const destaque = document.createElement('strong');
    destaque.textContent = primeiroNome(dados.nome || dados.usuario);
    saudacao.append('Bem-vindo, bom dia e ótimo trabalho, ', destaque);
}

function abrirAplicacao(dados) {
    autenticado = true;
    document.body.dataset.perfil = dados.perfil;
    window.aeriPermissoes = dados.permissoes || {};
    document.getElementById('usuario-logado').textContent = dados.nome || dados.usuario;
    document.getElementById('perfil-logado').textContent = dados.perfil;
    atualizarSaudacaoUsuario(dados);
    aplicarPermissoesSidebar(dados);
    document.getElementById('login-aeri').classList.remove('aberto');
    document.body.classList.remove('auth-pending');
    aoEntrar(dados);
}

async function verificarSessao() {
    try {
        const resposta = await fetch('/api/sessao');
        if (!resposta.ok) return abrirLogin();
        const dados = await resposta.json();
        definirCsrfToken(dados.csrfToken);
        abrirAplicacao(dados);
    } catch {
        abrirLogin();
    }
}

async function fazerLogin(evento) {
    evento.preventDefault();
    const botao = document.getElementById('btn-login');
    const erro = document.getElementById('login-erro');
    botao.disabled = true;
    erro.textContent = '';
    try {
        const resposta = await fetch('/api/login', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                usuario: document.getElementById('login-usuario').value.trim(),
                senha: document.getElementById('login-senha').value,
            }),
        });
        const dados = await resposta.json();
        if (!resposta.ok) throw new Error(dados.detail || 'Não foi possível entrar.');
        definirCsrfToken(dados.csrfToken);
        document.getElementById('form-login').reset();
        abrirAplicacao(dados);
    } catch (falha) {
        erro.textContent = falha.message;
    } finally {
        botao.disabled = false;
    }
}

async function sairAeri() {
    try {
        await requisicaoAeri('/api/logout', {method: 'POST'});
    } finally {
        definirCsrfToken('');
        autenticado = false;
        aoSair();
        abrirLogin();
    }
}

export function estaAutenticado() {
    return autenticado;
}

export function iniciarAutenticacao(opcoes = {}) {
    aoEntrar = opcoes.aoEntrar || aoEntrar;
    aoSair = opcoes.aoSair || aoSair;
    document.getElementById('form-login').addEventListener('submit', fazerLogin);
    document.getElementById('btn-sair').addEventListener('click', sairAeri);
    window.addEventListener('aeri:sessao-expirada', abrirLogin);
    verificarSessao();
}
