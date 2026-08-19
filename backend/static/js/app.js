import {configurarAcessoAnaliseManual, iniciarAnalisador} from './analisador.js?v=20260810-texto-manual-admin';
import {iniciarAutenticacao} from './autenticacao.js?v=20260819-poligonos-v12';
import {carregarBuscas, iniciarBuscas, limparBuscas} from './buscas.js?v=20260817-texto-pesquisa-v4';
import {iniciarIncra} from './incra.js?v=20260810-tri7-status-v1';
import {iniciarLivroProtocolos} from './livro_protocolos.js?v=20260817-reindexa-v1';
import {configurarAcessoMapaOnr, iniciarMapaOnr, limparMapaOnr} from './mapa_onr.js?v=20260815-permissao-v1';
import {carregarCustas, iniciarCustas, limparCustas} from './custas.js?v=20260804-custas-fluido';
import {carregarIntimacoes, iniciarIntimacoes, limparIntimacoes} from './intimacoes.js?v=20260810-nota-desistencia-v3';
import {iniciarNavegacao} from './navegacao.js?v=20260706-sidebar-responsiva';
import {carregarPoligonos, configurarAcessoPoligonos, iniciarPoligonos, limparPoligonos} from './poligonos.js?v=20260819-poligonos-v12';
import {carregarRegistrosAuxiliares, iniciarRegistrosAuxiliares, limparRegistrosAuxiliares} from './registros_auxiliares.js?v=20260811-reg-aux-sync-v1';
import {ativarStatusOnr, iniciarStatusOnr, pararStatusOnr} from './status_onr.js?v=20260706-status-onr';
import {carregarUsuarios, exigirTrocaSenha, iniciarUsuarios} from './usuarios.js?v=20260819-poligonos-v12';
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
            configurarAcessoAnaliseManual(dados.perfil);
            configurarAcessoMapaOnr(
                !dados.deveTrocarSenha && (
                    cargoAdministrativo(dados.perfil) || Boolean(dados.permissoes?.acessar_mapa_onr)
                ),
            );
            configurarAcessoPoligonos(
                !dados.deveTrocarSenha && (
                    cargoAdministrativo(dados.perfil) || Boolean(dados.permissoes?.acessar_poligonos)
                ),
            );
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
            if (!dados.deveTrocarSenha && (cargoAdministrativo(dados.perfil) || dados.permissoes?.processar_matricula)) {
                carregarBuscas();
                pararAtualizacoesPeriodicas.push(iniciarAtualizacaoPeriodica(carregarBuscas, INTERVALO_ATUALIZACAO_MS));
            }
            if (!dados.deveTrocarSenha && (cargoAdministrativo(dados.perfil) || dados.permissoes?.acessar_poligonos)) {
                // Sem atualização periódica: um desenho só muda quando
                // alguém o salva, e recarregar por cima do rascunho
                // apagaria o que o conferente está desenhando.
                carregarPoligonos();
            }
            if (cargoAdministrativo(dados.perfil) && !dados.deveTrocarSenha) carregarUsuarios();
            if (!dados.deveTrocarSenha) ativarStatusOnr();
        },
        aoSair: () => {
            configurarAcessoAnaliseManual();
            pararAtualizacoesAoVivo();
            limparIntimacoes();
            limparCustas();
            limparRegistrosAuxiliares();
            limparBuscas();
            limparMapaOnr();
            configurarAcessoMapaOnr(false);
            limparPoligonos();
            configurarAcessoPoligonos(false);
            pararStatusOnr();
        },
    });
}

iniciarNavegacao();
iniciarStatusOnr();
iniciarAnalisador();
iniciarBuscas();
iniciarIncra();
iniciarLivroProtocolos();
iniciarMapaOnr();
iniciarPoligonos();
iniciarCustas();
iniciarRegistrosAuxiliares();
iniciarIntimacoes();
iniciarUsuarios();
document.getElementById('btn-fechar-splash').addEventListener('click', fecharSplash);
window.setTimeout(fecharSplash, 2600);
