import {iniciarAnalisador} from './analisador.js';
import {iniciarAutenticacao} from './autenticacao.js';
import {iniciarIncra} from './incra.js';
import {carregarIntimacoes, iniciarIntimacoes, limparIntimacoes} from './intimacoes.js?v=20260709-protocolo-local';
import {iniciarNavegacao} from './navegacao.js?v=20260706-sidebar-responsiva';
import {ativarStatusOnr, iniciarStatusOnr, pararStatusOnr} from './status_onr.js?v=20260706-status-onr';
import {carregarUsuarios, exigirTrocaSenha, iniciarUsuarios} from './usuarios.js';

let splashEncerrada = false;

function cargoAdministrativo(perfil) {
    return ['ADMIN', 'SUBSTITUTO'].includes(perfil);
}

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
            if (!dados.deveTrocarSenha && (cargoAdministrativo(dados.perfil) || dados.permissoes?.ver_intimacoes)) carregarIntimacoes();
            if (cargoAdministrativo(dados.perfil) && !dados.deveTrocarSenha) carregarUsuarios();
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
