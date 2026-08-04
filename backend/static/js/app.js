import {iniciarAnalisador} from './analisador.js?v=20260731-auditoria';
import {iniciarAutenticacao} from './autenticacao.js?v=20260731-auditoria';
import {iniciarIncra} from './incra.js';
import {carregarCustas, iniciarCustas, limparCustas} from './custas.js?v=20260804-custas-fluido';
import {carregarIntimacoes, iniciarIntimacoes, limparIntimacoes} from './intimacoes.js?v=20260731-auditoria';
import {iniciarNavegacao} from './navegacao.js?v=20260706-sidebar-responsiva';
import {ativarStatusOnr, iniciarStatusOnr, pararStatusOnr} from './status_onr.js?v=20260706-status-onr';
import {carregarUsuarios, exigirTrocaSenha, iniciarUsuarios} from './usuarios.js?v=20260731-auditoria';

let splashEncerrada = false;

if (window.self !== window.top || new URLSearchParams(window.location.search).get('embedded') === '1') {
    document.body.classList.add('modo-incorporado');
}

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
            if (!dados.deveTrocarSenha && (cargoAdministrativo(dados.perfil) || dados.permissoes?.gerenciar_custas)) carregarCustas();
            if (cargoAdministrativo(dados.perfil) && !dados.deveTrocarSenha) carregarUsuarios();
            if (!dados.deveTrocarSenha) ativarStatusOnr();
        },
        aoSair: () => {
            limparIntimacoes();
            limparCustas();
            pararStatusOnr();
        },
    });
}

iniciarNavegacao();
iniciarStatusOnr();
iniciarAnalisador();
iniciarIncra();
iniciarCustas();
iniciarIntimacoes();
iniciarUsuarios();
document.getElementById('btn-fechar-splash').addEventListener('click', fecharSplash);
window.setTimeout(fecharSplash, 2600);
