import {definirCsrfToken, requisicaoAeri} from './api.js';

let autenticado = false;
let aoEntrar = () => {};
let aoSair = () => {};

function abrirLogin() {
    document.body.classList.add('auth-pending');
    document.getElementById('login-aeri').classList.add('aberto');
    window.setTimeout(() => document.getElementById('login-usuario').focus(), 80);
}

function abrirAplicacao(dados) {
    autenticado = true;
    document.body.dataset.perfil = dados.perfil;
    document.getElementById('usuario-logado').textContent = dados.nome || dados.usuario;
    document.getElementById('perfil-logado').textContent = dados.perfil;
    document.getElementById('nav-usuarios').hidden = dados.perfil !== 'ADMIN';
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
