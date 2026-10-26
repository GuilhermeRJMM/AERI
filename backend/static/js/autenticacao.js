import {definirCsrfToken, requisicaoAeri} from './api.js?v=20260902-arquivo-v1';
import {mostrarPagina} from './navegacao.js?v=20261020-voltar-paginas-v1';

let autenticado = false;
let aoEntrar = () => {};
let aoSair = () => {};
let aoAtualizar = () => {};
let sincronizandoSessao = false;
let ultimaSincronizacao = 0;
// Apenas uma preferência visual por aba. Nunca guarda ticket, cookie,
// identidade ou permissão, nem substitui a validação de /api/sessao.
const CHAVE_ORIGEM = 'aeri:origem-login';
let origemAutenticacao = 'LOCAL';
try { origemAutenticacao = sessionStorage.getItem(CHAVE_ORIGEM) === 'HUB' ? 'HUB' : 'LOCAL'; } catch (_erro) {}

function definirOrigem(dados) {
    origemAutenticacao = dados.origemAutenticacao === 'HUB' ? 'HUB' : 'LOCAL';
    try { sessionStorage.setItem(CHAVE_ORIGEM, origemAutenticacao); } catch (_erro) {}
    const viaHub = origemAutenticacao === 'HUB';
    document.getElementById('btn-sair').hidden = viaHub;
    document.getElementById('btn-minha-senha').hidden = viaHub;
}

function solicitarEntradaHub() {
    // Notificação opcional ao host WebView2, sem credenciais. A interface
    // continua utilizável se o HUB ainda não implementou esse sinal.
    try { window.chrome?.webview?.postMessage({type: 'aeri:reauth-required', version: 1}); } catch (_erro) {}
}

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
    definirModuloVisivel('mapaonr', admin || Boolean(permissoes.acessar_mapa_onr));
    definirModuloVisivel('buscas', admin || Boolean(permissoes.acessar_buscas));
    definirModuloVisivel('incra', admin || Boolean(permissoes.processar_incra));
    definirModuloVisivel('livroproto', admin || Boolean(permissoes.acessar_livro_protocolos));
    definirModuloVisivel('poligonos', admin || Boolean(permissoes.acessar_poligonos));
    definirModuloVisivel('geradornotas', admin || Boolean(permissoes.acessar_gerador_notas));
    definirModuloVisivel('custas', admin || Boolean(permissoes.gerenciar_custas));
    definirModuloVisivel('regaux', admin || Boolean(permissoes.consultar_registro_auxiliar));
    definirModuloVisivel('rotina', admin || Boolean(permissoes.ver_intimacoes));
    definirModuloVisivel('usuarios', admin || Boolean(permissoes.gerenciar_usuarios));
    definirModuloVisivel('inicio', true);
    definirModuloVisivel('certidao', admin || Boolean(permissoes.acessar_certidao));
    definirModuloVisivel('rgi', admin || Boolean(permissoes.acessar_rgi));
    definirModuloVisivel('sistema', admin || Boolean(permissoes.gerenciar_usuarios || permissoes.configurar_sistema));
    definirModuloVisivel('integracoes', admin || Boolean(permissoes.configurar_sistema));
    definirModuloVisivel('contratos', admin || Boolean(permissoes.acessar_contratos));
    definirModuloVisivel('auditoria', admin || Boolean(permissoes.revisar_auditoria));
    for (const setor of ['certidao','rgi','sistema']) {
        document.getElementById(`card-setor-${setor}`).hidden = document.querySelector(`.nav-item[data-page="${setor}"]`).hidden;
    }
    document.getElementById('painel-sem-acesso').hidden = admin || Boolean(permissoes.acessar_certidao || permissoes.acessar_rgi || permissoes.gerenciar_usuarios || permissoes.configurar_sistema);

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
    if (autenticado) aoSair();
    autenticado = false;
    definirCsrfToken('');
    document.body.classList.add('auth-pending');
    const saudacao = document.getElementById('saudacao-usuario');
    if (saudacao) saudacao.textContent = '';
    document.getElementById('login-aeri').classList.add('aberto');
    const viaHub = origemAutenticacao === 'HUB';
    document.getElementById('form-login').hidden = viaHub;
    document.getElementById('login-hub').hidden = !viaHub;
    document.getElementById('login-titulo').textContent = viaHub ? 'Continue pelo Sync HUB' : 'Bem-vindo ao AERI';
    document.getElementById('login-orientacao').textContent = viaHub
        ? 'Não é necessário ter uma senha cadastrada no AERI.'
        : 'Entre com suas credenciais para acessar o sistema.';
    if (viaHub) solicitarEntradaHub();
    window.setTimeout(() => document.getElementById(viaHub ? 'btn-verificar-acesso-hub' : 'login-usuario').focus(), 80);
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
    saudacao.append('Bem Vindo, bom dia e ótimo trabalho, ', destaque, '!');
}

function abrirAplicacao(dados) {
    definirOrigem(dados);
    autenticado = true;
    document.body.dataset.perfil = dados.perfil;
    window.aeriPermissoes = dados.permissoes || {};
    document.getElementById('usuario-logado').textContent = dados.nome || dados.usuario;
    document.getElementById('perfil-logado').textContent = dados.perfil;
    atualizarSaudacaoUsuario(dados);
    aplicarPermissoesSidebar(dados);
    mostrarPagina('inicio');
    document.getElementById('btn-meu-mfa').hidden = !['ADMIN', 'SUBSTITUTO'].includes(dados.perfil);
    document.getElementById('btn-meu-mfa').textContent = dados.mfaAtivo ? 'Reconfigurar MFA' : 'Ativar MFA';
    document.getElementById('login-aeri').classList.remove('aberto');
    document.body.classList.remove('auth-pending');
    aoEntrar(dados);
}

async function verificarSessao() {
    try {
        const resposta = await fetch('/api/sessao');
        if (!resposta.ok) {
            document.getElementById('login-hub-status').textContent = resposta.status === 401
                ? 'Aguardando um novo acesso pelo HUB.' : 'Não foi possível verificar o acesso. Tente novamente.';
            return abrirLogin();
        }
        const dados = await resposta.json();
        definirCsrfToken(dados.csrfToken);
        abrirAplicacao(dados);
    } catch {
        document.getElementById('login-hub-status').textContent = 'Não foi possível conectar. Verifique sua conexão e tente novamente.';
        abrirLogin();
    }
}

async function sincronizarSessao() {
    const agora = Date.now();
    if ((!autenticado && origemAutenticacao !== 'HUB') || sincronizandoSessao || agora - ultimaSincronizacao < 2_000) return;
    sincronizandoSessao = true;
    ultimaSincronizacao = agora;
    try {
        const resposta = await fetch('/api/sessao', {headers: {'X-AERI-Background': '1'}});
        if (resposta.status === 401) {
            window.dispatchEvent(new CustomEvent('aeri:sessao-expirada'));
            return;
        }
        if (!resposta.ok) return;
        const dados = await resposta.json();
        definirCsrfToken(dados.csrfToken);
        if (!autenticado) return abrirAplicacao(dados);
        definirOrigem(dados);
        document.body.dataset.perfil = dados.perfil;
        window.aeriPermissoes = dados.permissoes || {};
        aplicarPermissoesSidebar(dados);
        aoAtualizar(dados);
    } catch (_erro) {
        // Perda momentânea de rede não deve expulsar o usuário. A próxima
        // troca de foco tenta sincronizar novamente.
    } finally {
        sincronizandoSessao = false;
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
                codigoMfa: document.getElementById('login-mfa').value,
            }),
        });
        const dados = await resposta.json();
        if (resposta.status === 428) {
            const grupo = document.getElementById('login-mfa-grupo');
            grupo.hidden = false;
            document.getElementById('login-mfa').required = true;
            document.getElementById('login-mfa').focus();
            throw new Error(dados.detail);
        }
        if (!resposta.ok) throw new Error(dados.detail || 'Não foi possível entrar.');
        definirCsrfToken(dados.csrfToken);
        document.getElementById('login-mfa-grupo').hidden = true;
        document.getElementById('login-mfa').required = false;
        document.getElementById('form-login').reset();
        abrirAplicacao(dados);
    } catch (falha) {
        erro.textContent = falha.message;
    } finally {
        botao.disabled = false;
    }
}

async function sairAeri() {
    if (origemAutenticacao === 'HUB') return;
    try {
        await requisicaoAeri('/api/logout', {method: 'POST'});
    } finally {
        definirCsrfToken('');
        autenticado = false;
        aoSair();
        abrirLogin();
    }
}

async function configurarMeuMfa() {
    try {
        if (document.getElementById('btn-meu-mfa').textContent.includes('Reconfigurar')
            && !confirm('Reconfigurar o MFA invalidará imediatamente a chave atual. Continuar?')) return;
        const dados = await requisicaoAeri('/api/usuarios/minha-seguranca/mfa/iniciar', {method:'POST'});
        const codigo = prompt(`Adicione esta chave no Microsoft/Google Authenticator:\n\n${dados.segredo}\n\nDigite o código de 6 dígitos gerado:`);
        if (!codigo) return;
        await requisicaoAeri('/api/usuarios/minha-seguranca/mfa/confirmar', {
            method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({codigo}),
        });
        alert('MFA ativado. Os próximos logins exigirão o código do autenticador.');
        document.getElementById('btn-meu-mfa').textContent = 'MFA ativo';
    } catch (erro) { alert(erro.message); }
}

export function estaAutenticado() {
    return autenticado;
}

export function iniciarAutenticacao(opcoes = {}) {
    aoEntrar = opcoes.aoEntrar || aoEntrar;
    aoSair = opcoes.aoSair || aoSair;
    aoAtualizar = opcoes.aoAtualizar || aoAtualizar;
    document.getElementById('form-login').addEventListener('submit', fazerLogin);
    document.getElementById('btn-sair').addEventListener('click', sairAeri);
    document.getElementById('btn-verificar-acesso-hub').addEventListener('click', verificarSessao);
    document.getElementById('btn-meu-mfa').addEventListener('click', configurarMeuMfa);
    window.addEventListener('aeri:sessao-expirada', abrirLogin);
    window.addEventListener('focus', sincronizarSessao);
    document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'visible') sincronizarSessao();
    });
    verificarSessao();
}
