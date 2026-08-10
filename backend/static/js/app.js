import {iniciarAnalisador} from './analisador.js?v=20260731-auditoria';
import {iniciarAutenticacao} from './autenticacao.js?v=20260731-auditoria';
import {iniciarIncra} from './incra.js?v=20260810-tri7-status-v1';
import {iniciarLivroProtocolos} from './livro_protocolos.js';
import {carregarCustas, iniciarCustas, limparCustas} from './custas.js?v=20260804-custas-fluido';
import {carregarIntimacoes, iniciarIntimacoes, limparIntimacoes} from './intimacoes.js?v=20260810-nota-desistencia-v2';
import {iniciarNavegacao} from './navegacao.js?v=20260706-sidebar-responsiva';
import {carregarRegistrosAuxiliares, iniciarRegistrosAuxiliares, limparRegistrosAuxiliares} from './registros_auxiliares.js?v=20260805-reg-aux-v5';
import {ativarStatusOnr, iniciarStatusOnr, pararStatusOnr} from './status_onr.js?v=20260706-status-onr';
import {carregarUsuarios, exigirTrocaSenha, iniciarUsuarios} from './usuarios.js?v=20260731-auditoria';
import {iniciarAtualizacaoPeriodica} from './util.js';

const INTERVALO_ATUALIZACAO_MS = 5000;
let pararAtualizacoesPeriodicas = [];

function pararAtualizacoesAoVivo() {
    pararAtualizacoesPeriodicas.forEach(parar => parar());
    pararAtualizacoesPeriodicas = [];
}

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
            pararAtualizacoesAoVivo();
            if (!dados.deveTrocarSenha && (cargoAdministrativo(dados.perfil) || dados.permissoes?.ver_intimacoes)) {
                carregarIntimacoes();
                pararAtualizacoesPeriodicas.push(iniciarAtualizacaoPeriodica(carregarIntimacoes, INTERVALO_ATUALIZACAO_MS));
            }
            if (!dados.deveTrocarSenha && (cargoAdministrativo(dados.perfil) || dados.permissoes?.gerenciar_custas)) {
                carregarCustas();
                pararAtualizacoesPeriodicas.push(iniciarAtualizacaoPeriodica(carregarCustas, INTERVALO_ATUALIZACAO_MS));
            }
            if (!dados.deveTrocarSenha && (cargoAdministrativo(dados.perfil) || dados.permissoes?.gerenciar_custas)) {
                carregarRegistrosAuxiliares();
                pararAtualizacoesPeriodicas.push(iniciarAtualizacaoPeriodica(carregarRegistrosAuxiliares, INTERVALO_ATUALIZACAO_MS));
            }
            if (cargoAdministrativo(dados.perfil) && !dados.deveTrocarSenha) carregarUsuarios();
            if (!dados.deveTrocarSenha) ativarStatusOnr();
        },
        aoSair: () => {
            pararAtualizacoesAoVivo();
            limparIntimacoes();
            limparCustas();
            limparRegistrosAuxiliares();
            pararStatusOnr();
        },
    });
}

iniciarNavegacao();
iniciarStatusOnr();
iniciarAnalisador();
iniciarIncra();
iniciarLivroProtocolos();
iniciarCustas();
iniciarRegistrosAuxiliares();
iniciarIntimacoes();
iniciarUsuarios();
document.getElementById('btn-fechar-splash').addEventListener('click', fecharSplash);
window.setTimeout(fecharSplash, 2600);
