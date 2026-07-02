import {iniciarAnalisador} from './analisador.js';
import {iniciarAutenticacao} from './autenticacao.js';
import {iniciarIncra} from './incra.js';
import {carregarIntimacoes, iniciarIntimacoes, limparIntimacoes} from './intimacoes.js?v=20260702-2';
import {iniciarNavegacao} from './navegacao.js';

let splashEncerrada = false;

function fecharSplash() {
    if (splashEncerrada) return;
    splashEncerrada = true;
    const splash = document.getElementById('splash-aeri');
    splash.classList.add('splash-saindo');
    document.body.classList.remove('splash-active');
    window.setTimeout(() => splash.remove(), 650);
    iniciarAutenticacao({aoEntrar: carregarIntimacoes, aoSair: limparIntimacoes});
}

iniciarNavegacao();
iniciarAnalisador();
iniciarIncra();
iniciarIntimacoes();
document.getElementById('btn-fechar-splash').addEventListener('click', fecharSplash);
window.setTimeout(fecharSplash, 2600);
