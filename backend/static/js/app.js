import {iniciarAnalisador} from './analisador.js';
import {iniciarAutenticacao} from './autenticacao.js';
import {iniciarIncra} from './incra.js';
import {carregarIntimacoes, iniciarIntimacoes, limparIntimacoes} from './intimacoes.js?v=20260702-3';
import {iniciarNavegacao} from './navegacao.js?v=20260706-sidebar-responsiva';
import {ativarStatusOnr, iniciarStatusOnr, pararStatusOnr} from './status_onr.js?v=20260706-status-onr';
import {carregarUsuarios, exigirTrocaSenha, iniciarUsuarios} from './usuarios.js';

let splashEncerrada = false;

function fecharSplash() {
    if (splashEncerrada) return;
    splashEncerrada = true;
    const splash = document.getElementById('splash-aeri');
    splash.classList.add('splash-saindo');
    document.body.classList.remove('splash-active');
    window.setTimeout(() => splash.remove(), 650);
    iniciarAutenticacao({
        aoEntrar: dados => {
            exigirTrocaSenha(dados.deveTrocarSenha);
            if (!dados.deveTrocarSenha && (dados.perfil === 'ADMIN' || dados.permissoes?.ver_intimacoes)) carregarIntimacoes();
            if (dados.perfil === 'ADMIN' && !dados.deveTrocarSenha) carregarUsuarios();
            if (!dados.deveTrocarSenha) ativarStatusOnr();
        },
        aoSair: () => {
            limparIntimacoes();
            pararStatusOnr();
        },
    });
}

iniciarNavegacao();
iniciarStatusOnr();
iniciarAnalisador();
iniciarIncra();
iniciarIntimacoes();
iniciarUsuarios();
document.getElementById('btn-fechar-splash').addEventListener('click', fecharSplash);
window.setTimeout(fecharSplash, 2600);
