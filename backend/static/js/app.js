import {configurarAcessoAnaliseManual, iniciarAnalisador} from './analisador.js?v=20260821-controle-qualidade-v1';
import {iniciarAutenticacao} from './autenticacao.js?v=20260824-permissoes-v2';
import {carregarBuscas, iniciarBuscas, limparBuscas} from './buscas.js?v=20260820-robustez-v1';
import {iniciarIncra} from './incra.js?v=20260810-tri7-status-v1';
import {iniciarLivroProtocolos} from './livro_protocolos.js?v=20260826-data-v1';
import {configurarAcessoGeradorNotas, iniciarGeradorNotas} from './gerador_notas.js?v=20260825-legislacao-v1';
import {configurarAcessoMapaOnr, iniciarMapaOnr, limparMapaOnr} from './mapa_onr.js?v=20260815-permissao-v1';
import {carregarCustas, iniciarCustas, limparCustas} from './custas.js?v=20260820-robustez-v1';
import {carregarIntimacoes, iniciarIntimacoes, limparIntimacoes} from './intimacoes.js?v=20260820-robustez-v1';
import {iniciarNavegacao} from './navegacao.js?v=20260820-robustez-v1';
import {carregarPoligonos, configurarAcessoPoligonos, iniciarPoligonos, limparPoligonos} from './poligonos.js?v=20260819-poligonos-v13';
import {carregarRegistrosAuxiliares, iniciarRegistrosAuxiliares, limparRegistrosAuxiliares} from './registros_auxiliares.js?v=20260820-robustez-v1';
import {ativarStatusOnr, iniciarStatusOnr, pararStatusOnr} from './status_onr.js?v=20260820-robustez-v1';
import {carregarUsuarios, exigirTrocaSenha, iniciarUsuarios} from './usuarios.js?v=20260825-modal-v1';
import {iniciarAtualizacaoPeriodica} from './util.js?v=20260820-robustez-v1';
import {iniciarAtalhosGlobais} from './atalhos.js?v=20260821-atalhos-v1';

const INTERVALO_ATUALIZACAO_MS = 30_000;
let pararAtualizacoesPeriodicas = [];
let sessaoAtual = null;
let geracaoPagina = 0;

function pararAtualizacoesAoVivo() {
    pararAtualizacoesPeriodicas.forEach(parar => parar());
    pararAtualizacoesPeriodicas = [];
}

function paginaAtiva() {
    return document.querySelector('.nav-item.active')?.dataset.page || '';
}

function permitido(dados, permissao) {
    return cargoAdministrativo(dados?.perfil) || Boolean(dados?.permissoes?.[permissao]);
}

async function ativarPaginaAtual() {
    const geracao = ++geracaoPagina;
    pararAtualizacoesAoVivo();
    const dados = sessaoAtual;
    if (!dados || dados.deveTrocarSenha) return;
    const pagina = paginaAtiva();
    const periodicos = {
        rotina: permitido(dados, 'ver_intimacoes') ? carregarIntimacoes : null,
        custas: permitido(dados, 'gerenciar_custas') ? carregarCustas : null,
        regaux: permitido(dados, 'gerenciar_custas') ? carregarRegistrosAuxiliares : null,
        buscas: permitido(dados, 'acessar_buscas') ? carregarBuscas : null,
    };
    const carregar = periodicos[pagina];
    if (carregar) {
        await carregar();
        if (geracao !== geracaoPagina) return;
        pararAtualizacoesPeriodicas.push(
            iniciarAtualizacaoPeriodica(carregar, INTERVALO_ATUALIZACAO_MS),
        );
    } else if (pagina === 'poligonos' && permitido(dados, 'acessar_poligonos')) {
        await carregarPoligonos();
    } else if (pagina === 'usuarios' && cargoAdministrativo(dados.perfil)) {
        await carregarUsuarios();
    }
}

let splashEncerrada = false;

if (window.self !== window.top || new URLSearchParams(window.location.search).get('embedded') === '1') {
    document.body.classList.add('modo-incorporado');
}

function cargoAdministrativo(perfil) {
    return ['ADMIN', 'SUBSTITUTO'].includes(perfil);
}

function aplicarAcessosDaSessao(dados) {
    sessaoAtual = dados;
    configurarAcessoAnaliseManual(dados.perfil);
    configurarAcessoMapaOnr(
        !dados.deveTrocarSenha && permitido(dados, 'acessar_mapa_onr'),
    );
    configurarAcessoPoligonos(
        !dados.deveTrocarSenha && permitido(dados, 'acessar_poligonos'),
    );
    configurarAcessoGeradorNotas(
        !dados.deveTrocarSenha && permitido(dados, 'acessar_gerador_notas'),
    );
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
            aplicarAcessosDaSessao(dados);
            exigirTrocaSenha(dados.deveTrocarSenha);
            ativarPaginaAtual().catch(erro => console.error(erro));
            if (!dados.deveTrocarSenha) ativarStatusOnr();
        },
        aoAtualizar: dados => {
            aplicarAcessosDaSessao(dados);
            exigirTrocaSenha(dados.deveTrocarSenha);
        },
        aoSair: () => {
            sessaoAtual = null;
            geracaoPagina += 1;
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
            configurarAcessoGeradorNotas(false);
            pararStatusOnr();
        },
    });
}

iniciarNavegacao();
iniciarAtalhosGlobais();
iniciarStatusOnr();
iniciarAnalisador();
iniciarBuscas();
iniciarIncra();
iniciarLivroProtocolos();
iniciarGeradorNotas();
iniciarMapaOnr();
iniciarPoligonos();
iniciarCustas();
iniciarRegistrosAuxiliares();
iniciarIntimacoes();
iniciarUsuarios();
window.addEventListener('aeri:pagina-alterada', () => {
    ativarPaginaAtual().catch(erro => console.error(erro));
});
document.getElementById('btn-fechar-splash').addEventListener('click', fecharSplash);
window.setTimeout(fecharSplash, 2600);
