/**
 * Módulo Polígonos: desenhar, medir e conferir limites sobre satélite.
 *
 * O desenho vive em WGS84 (lon, lat) do começo ao fim. A tela é só uma
 * projeção disso -- por isso arrastar o mapa não muda um único vértice,
 * e mudar o zoom não muda a área.
 */
import {requisicaoAeri} from './api.js';
import {escaparHtml} from './util.js';
import {CAMADAS, criarMapa} from './mapa/motor.js?v=20260819-poligonos-v7';
import {
    areaM2, azimuteGraus, centroide, destinoGeodesico, distanciaM,
    formatarArea, formatarDistancia, formatarGms, ladosDoAnel, perimetroM,
} from './mapa/geometria.js?v=20260819-poligonos-v7';
import {montarKml} from './mapa/kml.js?v=20260819-poligonos-v7';

const SVG = 'http://www.w3.org/2000/svg';

let mapa = null;
let permitido = false;
let salvos = [];
let sobreposicoes = new Map();

const rascunho = {
    ferramenta: 'navegar',   // navegar | poligono | linha | ponto
    anel: [],
    tipo: 'POLIGONO',
    editandoId: null,
    verticeArrastado: null,
    cor: '#f97316',
};

function elemento(id) {
    return document.getElementById(id);
}

export function configurarAcessoPoligonos(liberado) {
    // Só guarda o estado. Quem mostra ou esconde a aba é
    // aplicarPermissoesSidebar, em autenticacao.js: o CSS do index.html
    // esconde todo .nav-item que não tenha data-autorizado="true", então
    // mexer em `hidden` daqui não tem efeito nenhum e ainda daria a
    // impressão de que a permissão está sendo aplicada em dois lugares.
    permitido = Boolean(liberado);
}

// ---------------------------------------------------------------------------
// Desenho vetorial sobre o mapa
// ---------------------------------------------------------------------------

function criarNo(nome, atributos) {
    const no = document.createElementNS(SVG, nome);
    Object.entries(atributos).forEach(([chave, valor]) => {
        if (valor != null) no.setAttribute(chave, valor);
    });
    return no;
}

function caminhoDoAnel(anel, fechar) {
    if (!anel.length) return '';
    const partes = anel.map(([lon, lat], indice) => {
        const p = mapa.geoParaTela(lon, lat);
        return `${indice === 0 ? 'M' : 'L'}${p.x.toFixed(1)},${p.y.toFixed(1)}`;
    });
    return partes.join(' ') + (fechar && anel.length > 2 ? ' Z' : '');
}

function redesenharVetores() {
    if (!mapa) return;
    const camada = mapa.camadaVetor;
    camada.innerHTML = '';

    // Salvos primeiro, para o rascunho ficar por cima.
    salvos.forEach(item => {
        if (item.id === rascunho.editandoId) return;   // esse está sendo editado
        // Encostar na divisa não pinta de vermelho: só invasão de área,
        // ou sobreposição que este banco não soube medir.
        const invadido = sobreposicoes.get(item.id)?.apenasEncosta !== true
            && sobreposicoes.has(item.id);
        camada.appendChild(criarNo('path', {
            d: caminhoDoAnel(item.anel, item.tipo === 'POLIGONO'),
            fill: item.tipo === 'POLIGONO' ? item.cor : 'none',
            'fill-opacity': invadido ? 0.38 : 0.18,
            stroke: invadido ? '#dc2626' : item.cor,
            'stroke-width': invadido ? 3 : 2,
            'stroke-dasharray': invadido ? '7 4' : null,
            class: 'mapa-forma',
        }));
        if (item.tipo === 'PONTO' && item.anel[0]) {
            const p = mapa.geoParaTela(item.anel[0][0], item.anel[0][1]);
            camada.appendChild(criarNo('circle', {
                cx: p.x, cy: p.y, r: 6, fill: item.cor,
                stroke: '#fff', 'stroke-width': 2,
            }));
        }
    });

    if (!rascunho.anel.length) return;

    const fechar = rascunho.tipo === 'POLIGONO';
    camada.appendChild(criarNo('path', {
        d: caminhoDoAnel(rascunho.anel, fechar),
        fill: fechar ? rascunho.cor : 'none',
        'fill-opacity': 0.25,
        stroke: rascunho.cor,
        'stroke-width': 2.5,
        class: 'mapa-forma mapa-forma-rascunho',
    }));

    // Rótulo de cada lado com distância e azimute, como num memorial.
    if (rascunho.anel.length > 1 && mapa.estado().zoom >= 15) {
        ladosDoAnel(rascunho.anel, fechar).forEach(lado => {
            const a = rascunho.anel[lado.de - 1];
            const b = rascunho.anel[lado.para - 1];
            if (!a || !b) return;
            const pa = mapa.geoParaTela(a[0], a[1]);
            const pb = mapa.geoParaTela(b[0], b[1]);
            const texto = criarNo('text', {
                x: (pa.x + pb.x) / 2, y: (pa.y + pb.y) / 2 - 6,
                class: 'mapa-rotulo-lado', 'text-anchor': 'middle',
            });
            texto.textContent = `${lado.distancia.toFixed(2)} m · ${lado.azimute.toFixed(2)}°`;
            camada.appendChild(texto);
        });
    }

    // Alças de vértice: arrastar move o ponto, clique com Alt remove.
    rascunho.anel.forEach(([lon, lat], indice) => {
        const p = mapa.geoParaTela(lon, lat);
        const alca = criarNo('circle', {
            cx: p.x, cy: p.y, r: 7, class: 'mapa-alca',
            'data-alca': indice, fill: '#fff',
            stroke: rascunho.cor, 'stroke-width': 3,
        });
        camada.appendChild(alca);
    });
}

// ---------------------------------------------------------------------------
// Medidas ao vivo
// ---------------------------------------------------------------------------

function atualizarMedidas() {
    const anel = rascunho.anel;
    const fechado = rascunho.tipo === 'POLIGONO';
    const area = fechado ? areaM2(anel) : 0;
    const perimetro = perimetroM(anel, fechado);

    elemento('poligonos-area').textContent = formatarArea(area);
    elemento('poligonos-perimetro').textContent = formatarDistancia(perimetro);
    elemento('poligonos-vertices').textContent = String(anel.length);

    const tabela = elemento('poligonos-lados');
    if (anel.length < 2) {
        tabela.innerHTML = '<tr><td colspan="3">Clique no mapa para começar o desenho.</td></tr>';
        return;
    }
    // Mesma razão da tabela de coordenadas: reconstruir enquanto alguém
    // digita apagaria o que está sendo escrito.
    if (tabela.contains(document.activeElement)) return;

    const lados = ladosDoAnel(anel, fechado);
    tabela.innerHTML = lados.map((lado, i) => {
        // O último lado volta ao primeiro vértice. Ele não é editável:
        // mudá-lo exigiria mover o ponto de partida, e é justamente a
        // comparação entre ele e o memorial que revela o erro de
        // fechamento do caminhamento.
        const fechamento = fechado && i === lados.length - 1;
        const campo = (eixo, valor, casas) => (fechamento
            ? `${valor.toLocaleString('pt-BR', {minimumFractionDigits: casas, maximumFractionDigits: casas})}`
            : `<input class="poligonos-lado-campo" data-lado="${i}" data-grandeza="${eixo}"
                inputmode="decimal" value="${valor.toFixed(casas)}"
                aria-label="${eixo === 'd' ? 'Distância' : 'Azimute'} do lado ${lado.de} para ${lado.para}">`);
        return `
        <tr class="${fechamento ? 'poligonos-lado-fechamento' : ''}">
            <td>${lado.de} &rarr; ${lado.para}${fechamento ? ' <span title="Lado de fechamento: resulta dos demais">&#9679;</span>' : ''}</td>
            <td>${campo('d', lado.distancia, 2)}</td>
            <td>${campo('a', lado.azimute, 4)}</td>
        </tr>`;
    }).join('');
}

/**
 * Aplica ao desenho a distância ou o azimute digitados num lado.
 *
 * O vértice de chegada é recalculado a partir do de saída, e todos os
 * vértices seguintes andam junto, rigidamente. Isso é o que permite
 * lançar o memorial lado a lado: cada correção fixa aquele lado sem
 * desmanchar os que já foram acertados antes dele.
 */
function aplicarEdicaoDeLado(campo) {
    const indice = Number(campo.dataset.lado);
    const grandeza = campo.dataset.grandeza;
    const de = rascunho.anel[indice];
    const para = rascunho.anel[indice + 1];
    if (!de || !para) return;

    const valor = numeroDigitado(campo.value);
    const invalido = valor === null
        || (grandeza === 'd' && (valor <= 0 || valor > 500000))
        || (grandeza === 'a' && (valor < 0 || valor > 360));
    if (invalido) {
        campo.classList.add('poligonos-coord-invalida');
        elemento('poligonos-status').textContent = grandeza === 'd'
            ? 'Distância precisa ser maior que zero (limite de 500 km).'
            : 'Azimute precisa ficar entre 0 e 360 graus.';
        return;
    }
    campo.classList.remove('poligonos-coord-invalida');

    const distancia = grandeza === 'd' ? valor : distanciaM(de, para);
    const azimute = grandeza === 'a' ? valor : azimuteGraus(de, para);
    const novo = destinoGeodesico(de, azimute, distancia);

    const deslocamento = [novo[0] - para[0], novo[1] - para[1]];
    for (let i = indice + 1; i < rascunho.anel.length; i += 1) {
        rascunho.anel[i] = [
            rascunho.anel[i][0] + deslocamento[0],
            rascunho.anel[i][1] + deslocamento[1],
        ];
    }

    // Não reconstrói a tabela de lados, que é onde está o cursor.
    redesenharVetores();
    atualizarCoordenadas();
    atualizarPontoCentral();
    elemento('poligonos-area').textContent = formatarArea(
        rascunho.tipo === 'POLIGONO' ? areaM2(rascunho.anel) : 0);
    elemento('poligonos-perimetro').textContent = formatarDistancia(
        perimetroM(rascunho.anel, rascunho.tipo === 'POLIGONO'));
}

function ligarEdicaoDeLados() {
    const tabela = elemento('poligonos-lados');

    tabela.addEventListener('input', evento => {
        const campo = evento.target.closest('[data-lado]');
        if (campo) aplicarEdicaoDeLado(campo);
    });

    tabela.addEventListener('keydown', evento => {
        if (evento.key !== 'Enter' || !evento.target.closest('[data-lado]')) return;
        evento.preventDefault();
        evento.target.blur();
        atualizarTudo();
    });

    tabela.addEventListener('blur', evento => {
        if (evento.target.closest('[data-lado]')) atualizarTudo();
    }, true);
}

// ---------------------------------------------------------------------------
// Coordenadas do desenho
// ---------------------------------------------------------------------------

// Longitude primeiro, latitude depois -- a ordem do GeoJSON, e a mesma em
// que o anel é guardado. Vale registrar que ela é o inverso da que o
// Google Maps mostra, que é a origem da maioria das coordenadas coladas.
const CASAS_DECIMAIS = 8;   // ~1 mm no equador

function linhasDeCoordenadas() {
    return rascunho.anel.map(([lon, lat], indice) => ({
        ordem: indice + 1,
        lon: lon.toFixed(CASAS_DECIMAIS),
        lat: lat.toFixed(CASAS_DECIMAIS),
    }));
}

function textoDasCoordenadas() {
    // O cabeçalho não é enfeite: sem ele, colar de volta um par como
    // "-49.10, -17.73" é ambíguo, porque os dois valores cabem numa
    // latitude. A importação lê essa linha para saber a ordem.
    return ['# longitude, latitude']
        .concat(linhasDeCoordenadas().map(l => `${l.lon}, ${l.lat}`))
        .join('\n');
}

function atualizarCoordenadas() {
    const caixa = elemento('poligonos-coord-caixa');
    const aviso = elemento('poligonos-coord-aviso');
    const copiar = elemento('poligonos-copiar-coordenadas');
    const corpo = elemento('poligonos-coordenadas');

    // Três vértices já fecham um polígono; o caso comum do balcão é o
    // lote de quatro, e a lista aparece sozinha ao chegar lá.
    const fechado = rascunho.tipo === 'POLIGONO' && rascunho.anel.length >= 3;
    const temPontos = rascunho.anel.length > 0;
    caixa.hidden = !temPontos;
    copiar.hidden = !temPontos;

    if (!temPontos) {
        aviso.hidden = false;
        aviso.textContent = 'Feche um polígono para gerar as coordenadas.';
        corpo.innerHTML = '';
        return;
    }
    aviso.hidden = fechado || rascunho.tipo !== 'POLIGONO';
    aviso.textContent = `Faltam ${3 - rascunho.anel.length} vértice(s) para fechar o polígono.`;

    // Redesenhar a tabela enquanto alguém digita apagaria o que está
    // sendo escrito e roubaria o cursor. Enquanto o foco está aqui
    // dentro, quem manda é o campo, não o estado do desenho.
    if (corpo.contains(document.activeElement)) return;

    const ultimo = rascunho.anel.length - 1;
    corpo.innerHTML = linhasDeCoordenadas().map((l, i) => `
        <tr>
            <td>${l.ordem}</td>
            <td><input class="poligonos-coord-campo" data-vertice="${i}" data-eixo="0"
                inputmode="decimal" value="${l.lon}" aria-label="Longitude do vértice ${l.ordem}"></td>
            <td><input class="poligonos-coord-campo" data-vertice="${i}" data-eixo="1"
                inputmode="decimal" value="${l.lat}" aria-label="Latitude do vértice ${l.ordem}"></td>
            <td class="poligonos-coord-acoes">
                <button type="button" data-mover="${i}" data-passo="-1" title="Subir"
                    ${i === 0 ? 'disabled' : ''}>&uarr;</button>
                <button type="button" data-mover="${i}" data-passo="1" title="Descer"
                    ${i === ultimo ? 'disabled' : ''}>&darr;</button>
                <button type="button" data-remover="${i}" title="Remover vértice">&times;</button>
            </td>
        </tr>`).join('');
}

/** Lê número aceitando vírgula decimal, que é como se digita aqui. */
function numeroDigitado(texto) {
    const limpo = String(texto).trim().replace(/\s+/g, '').replace(',', '.');
    if (!/^[-+]?\d*\.?\d+$/.test(limpo)) return null;
    const valor = Number(limpo);
    return Number.isFinite(valor) ? valor : null;
}

function aplicarEdicaoDeCoordenada(campo) {
    const indice = Number(campo.dataset.vertice);
    const eixo = Number(campo.dataset.eixo);
    const ponto = rascunho.anel[indice];
    if (!ponto) return;

    const valor = numeroDigitado(campo.value);
    const limite = eixo === 0 ? 180 : 90;
    if (valor === null || Math.abs(valor) > limite) {
        // Não corrige sozinho: devolve o valor anterior e marca o campo.
        // Um vértice que "quase" foi editado é pior do que um que
        // visivelmente não foi.
        campo.classList.add('poligonos-coord-invalida');
        campo.value = ponto[eixo].toFixed(CASAS_DECIMAIS);
        elemento('poligonos-status').textContent = eixo === 0
            ? 'Longitude precisa ficar entre -180 e 180.'
            : 'Latitude precisa ficar entre -90 e 90.';
        return;
    }
    campo.classList.remove('poligonos-coord-invalida');
    ponto[eixo] = valor;
    // Só o mapa e as medidas: a tabela é a origem da edição e
    // reconstruí-la aqui tiraria o cursor de onde ele está.
    redesenharVetores();
    atualizarMedidas();
    atualizarPontoCentral();
}

function ligarEdicaoDeCoordenadas() {
    const corpo = elemento('poligonos-coordenadas');

    corpo.addEventListener('input', evento => {
        const campo = evento.target.closest('[data-vertice]');
        if (campo) aplicarEdicaoDeCoordenada(campo);
    });

    corpo.addEventListener('keydown', evento => {
        if (evento.key !== 'Enter') return;
        const campo = evento.target.closest('[data-vertice]');
        if (!campo) return;
        // Enter confirma e sai: aí a tabela pode se reconstruir e mostrar
        // o valor já formatado com as oito casas.
        evento.preventDefault();
        campo.blur();
        atualizarTudo();
    });

    corpo.addEventListener('blur', evento => {
        if (evento.target.closest('[data-vertice]')) atualizarTudo();
    }, true);

    // pointerdown, e não click: sair de um campo dispara blur, que
    // reconstrói a tabela e remove estes botões do DOM. O clique então
    // não teria em que elemento acontecer e se perderia -- exatamente na
    // situação mais comum, que é ajustar um valor e logo reordenar.
    // preventDefault mantém o foco onde está e o blur nem chega a ocorrer.
    corpo.addEventListener('pointerdown', evento => {
        const acao = evento.target.closest('[data-mover], [data-remover]');
        if (!acao || acao.disabled) return;
        evento.preventDefault();

        const mover = evento.target.closest('[data-mover]');
        if (mover) {
            // Reordenar importa: a sequência dos vértices é o caminho do
            // perímetro, e trocar dois de lugar muda a forma do imóvel.
            const de = Number(mover.dataset.mover);
            const para = de + Number(mover.dataset.passo);
            if (para < 0 || para >= rascunho.anel.length) return;
            [rascunho.anel[de], rascunho.anel[para]] =
                [rascunho.anel[para], rascunho.anel[de]];
            atualizarTudo();
            return;
        }
        const remover = evento.target.closest('[data-remover]');
        if (remover) {
            rascunho.anel.splice(Number(remover.dataset.remover), 1);
            atualizarTudo();
        }
    });
}

async function copiarCoordenadas() {
    const texto = textoDasCoordenadas();
    // execCommand, e não navigator.clipboard: o AERI roda dentro de um
    // iframe no SYNC, onde a API assíncrona de área de transferência é
    // bloqueada por permissão. Já passamos por isso na Pesquisa
    // Qualificada.
    const campo = document.createElement('textarea');
    campo.value = texto;
    campo.setAttribute('readonly', '');
    campo.style.cssText = 'position:fixed;top:-1000px;opacity:0';
    document.body.appendChild(campo);
    campo.select();
    let copiou = false;
    try {
        copiou = document.execCommand('copy');
    } catch (_erro) {
        copiou = false;
    }
    campo.remove();
    if (!copiou) {
        try {
            await navigator.clipboard.writeText(texto);
            copiou = true;
        } catch (_erro) {
            copiou = false;
        }
    }
    elemento('poligonos-status').textContent = copiou
        ? `${rascunho.anel.length} coordenada(s) copiada(s), longitude primeiro.`
        : 'Não foi possível copiar. Selecione a tabela e use Ctrl+C.';
}

// ---------------------------------------------------------------------------
// Dados de identificação do imóvel (Mapa do ONR)
// ---------------------------------------------------------------------------

// A chave é o nome do campo em dadosMapa; o valor, o id do input.
const CAMPOS_DO_MAPA = {
    cns: 'poligonos-cns',
    municipio: 'poligonos-municipio',
    uf: 'poligonos-uf',
    proprietarios: 'poligonos-proprietarios',
    documentos: 'poligonos-documentos',
    endereco: 'poligonos-endereco',
    numero: 'poligonos-numero',
    cep: 'poligonos-cep',
    motivo: 'poligonos-motivo',
};

function lerDadosMapa() {
    return Object.fromEntries(
        Object.entries(CAMPOS_DO_MAPA).map(([chave, id]) =>
            [chave, elemento(id).value.trim()]),
    );
}

function escreverDadosMapa(dados = {}) {
    Object.entries(CAMPOS_DO_MAPA).forEach(([chave, id]) => {
        elemento(id).value = dados[chave] || '';
    });
}

function atualizarPontoCentral() {
    const alvo = elemento('poligonos-centro');
    if (rascunho.anel.length < 3 || rascunho.tipo !== 'POLIGONO') {
        alvo.textContent = '—';
        return;
    }
    const [lon, lat] = centroide(rascunho.anel);
    // O Mapa pede "longitude e latitude do ponto central, separados por
    // vírgula" (item 3.4.5.1), nessa ordem.
    alvo.textContent = `${lon.toFixed(8)}, ${lat.toFixed(8)}`;
}

function atualizarTudo() {
    redesenharVetores();
    atualizarMedidas();
    atualizarCoordenadas();
    atualizarPontoCentral();
}

// ---------------------------------------------------------------------------
// Ferramentas
// ---------------------------------------------------------------------------

function definirFerramenta(nome) {
    rascunho.ferramenta = nome;
    rascunho.tipo = nome === 'linha' ? 'LINHA' : nome === 'ponto' ? 'PONTO' : 'POLIGONO';
    document.querySelectorAll('[data-ferramenta]').forEach(botao => {
        botao.classList.toggle('ativo', botao.dataset.ferramenta === nome);
    });
    elemento('poligonos-mapa').dataset.ferramenta = nome;
}

function limparRascunho() {
    rascunho.anel = [];
    rascunho.editandoId = null;
    elemento('poligonos-nome').value = '';
    elemento('poligonos-matricula').value = '';
    elemento('poligonos-observacao').value = '';
    escreverDadosMapa({});
    elemento('poligonos-excluir').hidden = true;
    atualizarTudo();
}

function aoClicarNoMapa(geo) {
    if (rascunho.ferramenta === 'navegar') return;
    if (rascunho.ferramenta === 'ponto') rascunho.anel = [[geo.lon, geo.lat]];
    else rascunho.anel.push([geo.lon, geo.lat]);
    atualizarTudo();
}

function ligarArrasteDeVertices() {
    const area = elemento('poligonos-mapa');

    area.addEventListener('pointerdown', evento => {
        const alca = evento.target.closest('[data-alca]');
        if (!alca) return;
        const indice = Number(alca.dataset.alca);
        if (evento.altKey) {
            // Alt+clique remove o vértice -- o gesto do Scribble Maps.
            rascunho.anel.splice(indice, 1);
            atualizarTudo();
            return;
        }
        rascunho.verticeArrastado = indice;
        evento.preventDefault();
        evento.stopPropagation();
    });

    area.addEventListener('pointermove', evento => {
        if (rascunho.verticeArrastado == null) return;
        const caixa = area.getBoundingClientRect();
        const geo = mapa.telaParaGeo(evento.clientX - caixa.left, evento.clientY - caixa.top);
        rascunho.anel[rascunho.verticeArrastado] = [geo.lon, geo.lat];
        atualizarTudo();
    });

    const soltar = () => { rascunho.verticeArrastado = null; };
    area.addEventListener('pointerup', soltar);
    area.addEventListener('pointercancel', soltar);
}

// ---------------------------------------------------------------------------
// Persistência
// ---------------------------------------------------------------------------

async function carregarSalvos() {
    salvos = await requisicaoAeri('/api/poligonos');
    renderizarLista();
    atualizarTudo();
}

function renderizarLista() {
    const lista = elemento('poligonos-lista');
    if (!salvos.length) {
        lista.innerHTML = '<li class="poligonos-vazio">Nenhum desenho salvo ainda.</li>';
        return;
    }
    lista.innerHTML = salvos.map(item => `
        <li class="poligonos-item ${sobreposicoes.get(item.id)?.apenasEncosta === false || (sobreposicoes.has(item.id) && sobreposicoes.get(item.id)?.apenasEncosta == null) ? 'poligonos-item-invadido' : ''}">
            <button type="button" class="poligonos-abrir" data-id="${escaparHtml(item.id)}">
                <span class="poligonos-cor" style="background:${escaparHtml(item.cor)}"></span>
                <span class="poligonos-nome">${escaparHtml(item.nome)}</span>
                <span class="poligonos-medida">
                    ${item.tipo === 'POLIGONO' ? formatarArea(item.areaM2) : formatarDistancia(item.perimetroM)}
                </span>
                ${item.matricula ? `<span class="poligonos-matricula">Mat. ${escaparHtml(item.matricula)}</span>` : ''}
            </button>
            <button type="button" class="poligonos-enquadrar" data-enquadrar="${escaparHtml(item.id)}" title="Centralizar no mapa">⌖</button>
        </li>`).join('');
}

async function salvar() {
    const nome = elemento('poligonos-nome').value.trim();
    if (!nome) { alert('Dê um nome ao desenho antes de salvar.'); return; }
    if (!rascunho.anel.length) { alert('Desenhe algo no mapa antes de salvar.'); return; }

    const corpo = {
        nome,
        matricula: elemento('poligonos-matricula').value.trim() || null,
        tipo: rascunho.tipo,
        anel: rascunho.anel,
        cor: rascunho.cor,
        observacao: elemento('poligonos-observacao').value.trim() || null,
        dadosMapa: lerDadosMapa(),
    };
    const opcoes = {
        method: rascunho.editandoId ? 'PUT' : 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(corpo),
    };
    const url = rascunho.editandoId
        ? `/api/poligonos/${rascunho.editandoId}` : '/api/poligonos';
    try {
        const salvo = await requisicaoAeri(url, opcoes);
        // A área que vale é a que o servidor calculou, não a da tela.
        elemento('poligonos-area').textContent = formatarArea(salvo.areaM2);
        await carregarSalvos();
        await conferirSobreposicoes(salvo.id);
        limparRascunho();
        elemento('poligonos-status').textContent = `"${salvo.nome}" salvo.`;
    } catch (falha) {
        alert(falha.message);
    }
}

function abrirSalvo(id) {
    const item = salvos.find(p => p.id === id);
    if (!item) return;
    rascunho.anel = item.anel.map(p => [p[0], p[1]]);
    rascunho.tipo = item.tipo;
    rascunho.cor = item.cor;
    rascunho.editandoId = item.id;
    elemento('poligonos-nome').value = item.nome;
    elemento('poligonos-matricula').value = item.matricula || '';
    elemento('poligonos-observacao').value = item.observacao || '';
    escreverDadosMapa(item.dadosMapa);
    elemento('poligonos-excluir').hidden = false;
    definirFerramenta(item.tipo === 'LINHA' ? 'linha' : item.tipo === 'PONTO' ? 'ponto' : 'poligono');
    mapa.ajustarPara(item.anel);
    conferirSobreposicoes(item.id);
    atualizarTudo();
}

async function conferirSobreposicoes(id) {
    sobreposicoes = new Map();
    try {
        const achados = await requisicaoAeri(`/api/poligonos/${id}/sobreposicoes`);
        achados.forEach(item => sobreposicoes.set(item.id, item));
        const aviso = elemento('poligonos-sobreposicao');
        if (!achados.length) { aviso.hidden = true; return; }

        // Encostar na divisa é o normal entre vizinhos; invadir não é. O
        // aviso separa os dois para o conferente não perder o que importa
        // no meio do que é esperado.
        const invadem = achados.filter(a => a.apenasEncosta === false);
        const encostam = achados.filter(a => a.apenasEncosta === true);
        const semMedida = achados.filter(a => a.apenasEncosta == null);

        const descrever = item => escaparHtml(item.nome)
            + (item.areaInvadidaM2 ? ` (${escaparHtml(formatarArea(item.areaInvadidaM2))})` : '');

        const partes = [];
        if (invadem.length) {
            partes.push(`<strong>Invasão de área</strong> com ${invadem.length} desenho(s): `
                + invadem.map(descrever).join(', ') + '.');
        }
        if (encostam.length) {
            partes.push(`Encosta na divisa de ${encostam.length} desenho(s): `
                + encostam.map(a => escaparHtml(a.nome)).join(', ') + '.');
        }
        if (semMedida.length) {
            partes.push(`<strong>Sobreposição detectada</strong> com ${semMedida.length} desenho(s): `
                + semMedida.map(a => escaparHtml(a.nome)).join(', ')
                + '. Este banco não calcula a área invadida; confira no desenho.');
        }
        aviso.hidden = false;
        aviso.innerHTML = partes.join('<br>');
        aviso.classList.toggle('poligonos-alerta-leve', !invadem.length && !semMedida.length);
    } catch (_falha) {
        // Sobreposição é conferência auxiliar; falhar aqui não pode
        // impedir o usuário de continuar desenhando.
    }
    renderizarLista();
    redesenharVetores();
}

async function excluir() {
    if (!rascunho.editandoId) return;
    if (!confirm('Excluir este desenho?')) return;
    await requisicaoAeri(`/api/poligonos/${rascunho.editandoId}`, {method: 'DELETE'});
    sobreposicoes = new Map();
    elemento('poligonos-sobreposicao').hidden = true;
    await carregarSalvos();
    limparRascunho();
}

// ---------------------------------------------------------------------------
// Importar e exportar
// ---------------------------------------------------------------------------

async function importarTexto() {
    const texto = elemento('poligonos-importar-texto').value;
    if (!texto.trim()) return;
    try {
        const resultado = await requisicaoAeri('/api/poligonos/importar', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({texto}),
        });
        rascunho.anel = resultado.anel;
        rascunho.editandoId = null;
        mapa.ajustarPara(rascunho.anel);
        atualizarTudo();
        elemento('poligonos-status').textContent =
            `${resultado.vertices} vértice(s) importado(s).`;
    } catch (falha) {
        alert(falha.message);
    }
}

function baixar(nomeArquivo, conteudo, tipo) {
    // Blob em vez de data: URL porque o memorial de uma fazenda passa
    // fácil do limite de tamanho que os navegadores impõem a data:.
    const url = URL.createObjectURL(new Blob([conteudo], {type: tipo}));
    const link = document.createElement('a');
    link.href = url;
    link.download = nomeArquivo;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
}

function nomeBase() {
    return (elemento('poligonos-nome').value.trim() || 'poligono')
        .replace(/[^\p{L}\p{N}._-]+/gu, '_');
}

function exportarGeoJson() {
    if (!rascunho.anel.length) return;
    const fechar = rascunho.tipo === 'POLIGONO';
    const coordenadas = fechar
        ? [[...rascunho.anel, rascunho.anel[0]]]
        : rascunho.anel;
    const geometria = {
        POLIGONO: {type: 'Polygon', coordinates: coordenadas},
        LINHA: {type: 'LineString', coordinates: coordenadas},
        PONTO: {type: 'Point', coordinates: rascunho.anel[0]},
    }[rascunho.tipo];
    baixar(`${nomeBase()}.geojson`, JSON.stringify({
        type: 'FeatureCollection',
        features: [{
            type: 'Feature',
            properties: {
                nome: elemento('poligonos-nome').value.trim(),
                matricula: elemento('poligonos-matricula').value.trim() || null,
                area_m2: fechar ? areaM2(rascunho.anel) : null,
                perimetro_m: perimetroM(rascunho.anel, fechar),
            },
            geometry: geometria,
        }],
    }, null, 2), 'application/geo+json');
}

function exportarKml() {
    if (!rascunho.anel.length) return;
    if (rascunho.tipo !== 'POLIGONO') {
        // O Mapa do ONR aceita apenas polígonos fechados (Manual Técnico
        // Operacional, 3.4.3). Linha e ponto continuam exportáveis, mas
        // quem for enviar precisa saber que não serão aceitos.
        elemento('poligonos-status').textContent =
            'Atenção: o Mapa do ONR só aceita polígonos fechados. '
            + 'Este arquivo serve para outros usos.';
    }
    baixar(
        `${nomeBase()}.kml`,
        montarKml({
            nome: elemento('poligonos-nome').value.trim(),
            matricula: elemento('poligonos-matricula').value.trim(),
            observacao: elemento('poligonos-observacao').value.trim(),
            dadosMapa: lerDadosMapa(),
            anel: rascunho.anel,
            tipo: rascunho.tipo,
        }),
        'application/vnd.google-earth.kml+xml',
    );
}

async function exportarMemorial() {
    if (rascunho.anel.length < 3) { alert('O memorial precisa de um polígono fechado.'); return; }
    let utm;
    try {
        utm = await requisicaoAeri('/api/poligonos/utm', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({anel: rascunho.anel}),
        });
    } catch (falha) { alert(falha.message); return; }

    const lados = ladosDoAnel(rascunho.anel, true);
    const linhas = [
        `MEMORIAL DESCRITIVO — ${elemento('poligonos-nome').value.trim() || 'sem nome'}`,
        elemento('poligonos-matricula').value.trim()
            ? `Matrícula: ${elemento('poligonos-matricula').value.trim()}` : '',
        `Sistema: SIRGAS 2000 / UTM fuso ${utm.fuso}S`,
        `Área: ${formatarArea(areaM2(rascunho.anel))}`,
        `Perímetro: ${formatarDistancia(perimetroM(rascunho.anel, true))}`,
        '',
        'VÉRTICES',
        'Nº'.padEnd(6) + 'ESTE'.padEnd(16) + 'NORTE'.padEnd(17) + 'LATITUDE'.padEnd(18) + 'LONGITUDE',
        ...utm.vertices.map((v, i) => {
            const [lon, lat] = rascunho.anel[i];
            return `P-${String(v.ordem).padStart(2, '0')}`.padEnd(6)
                + v.leste.toFixed(3).padEnd(16)
                + v.norte.toFixed(3).padEnd(17)
                + formatarGms(lat, 'lat').padEnd(18)
                + formatarGms(lon, 'lon');
        }),
        '',
        'LADOS',
        'DE→PARA'.padEnd(12) + 'DISTÂNCIA'.padEnd(16) + 'AZIMUTE',
        ...lados.map(l => `P-${String(l.de).padStart(2, '0')}→P-${String(l.para).padStart(2, '0')}`.padEnd(12)
            + `${l.distancia.toFixed(3)} m`.padEnd(16)
            + `${l.azimute.toFixed(4)}°`),
    ].filter(Boolean);
    baixar(`${nomeBase()}_memorial.txt`, linhas.join('\n'), 'text/plain;charset=utf-8');
}

// ---------------------------------------------------------------------------
// Início
// ---------------------------------------------------------------------------

export function iniciarPoligonos() {
    const area = elemento('poligonos-mapa');
    if (!area) return;

    mapa = criarMapa(area, {camada: 'satelite', zoom: 15});
    mapa.ao('clicou', aoClicarNoMapa);
    mapa.ao('mudou', redesenharVetores);
    mapa.ao('moveu', geo => {
        // Longitude primeiro aqui também, para a leitura do cursor não
        // contradizer a tabela de coordenadas logo ao lado.
        elemento('poligonos-cursor').textContent =
            `${formatarGms(geo.lon, 'lon')}  ${formatarGms(geo.lat, 'lat')}`;
    });
    ligarArrasteDeVertices();
    ligarEdicaoDeCoordenadas();
    ligarEdicaoDeLados();

    document.querySelectorAll('[data-ferramenta]').forEach(botao => {
        botao.addEventListener('click', () => definirFerramenta(botao.dataset.ferramenta));
    });
    document.querySelectorAll('[data-camada]').forEach(botao => {
        botao.addEventListener('click', () => {
            mapa.definirCamada(botao.dataset.camada);
            document.querySelectorAll('[data-camada]').forEach(outro => {
                outro.classList.toggle('ativo', outro === botao);
            });
        });
    });
    document.querySelectorAll('[data-cor]').forEach(botao => {
        botao.style.background = botao.dataset.cor;
        botao.addEventListener('click', () => {
            rascunho.cor = botao.dataset.cor;
            document.querySelectorAll('[data-cor]').forEach(outro => {
                outro.classList.toggle('ativo', outro === botao);
            });
            atualizarTudo();
        });
    });

    elemento('poligonos-desfazer').addEventListener('click', () => {
        rascunho.anel.pop();
        atualizarTudo();
    });
    elemento('poligonos-limpar').addEventListener('click', limparRascunho);
    elemento('poligonos-salvar').addEventListener('click', salvar);
    elemento('poligonos-excluir').addEventListener('click', excluir);
    elemento('poligonos-importar').addEventListener('click', importarTexto);
    elemento('poligonos-copiar-coordenadas').addEventListener('click', copiarCoordenadas);
    elemento('poligonos-exportar-geojson').addEventListener('click', exportarGeoJson);
    elemento('poligonos-exportar-kml').addEventListener('click', exportarKml);
    elemento('poligonos-exportar-memorial').addEventListener('click', exportarMemorial);
    elemento('poligonos-mais').addEventListener('click', () => mapa.aproximar(1));
    elemento('poligonos-menos').addEventListener('click', () => mapa.aproximar(-1));

    elemento('poligonos-lista').addEventListener('click', evento => {
        const abrir = evento.target.closest('[data-id]');
        if (abrir) { abrirSalvo(abrir.dataset.id); return; }
        const enquadrar = evento.target.closest('[data-enquadrar]');
        if (enquadrar) {
            const item = salvos.find(p => p.id === enquadrar.dataset.enquadrar);
            if (item) mapa.ajustarPara(item.anel);
        }
    });

    // Abrir a aba é o momento em que o mapa deixa de ter tamanho zero.
    // Redesenhar aqui garante a primeira pintura sem depender de o
    // navegador entregar a notificação de redimensionamento.
    //
    // O adiamento não é decorativo: quem marca a página como ativa é o
    // ouvinte delegado da navegação, na barra lateral, que só roda depois
    // deste (o evento sobe do item para o contêiner). Medir agora daria
    // zero de novo. setTimeout, e não requestAnimationFrame, porque a
    // fila de tarefas roda mesmo quando a aba está em segundo plano e
    // nenhum quadro é composto.
    document.querySelector('.nav-item[data-page="poligonos"]')
        ?.addEventListener('click', () => {
            window.setTimeout(() => mapa.redesenhar(), 0);
        });

    definirFerramenta('poligono');
    atualizarTudo();
}

export async function carregarPoligonos() {
    if (!permitido) return;
    try {
        await carregarSalvos();
    } catch (falha) {
        elemento('poligonos-status').textContent = falha.message;
    }
}

export function limparPoligonos() {
    salvos = [];
    sobreposicoes = new Map();
    rascunho.anel = [];
    rascunho.editandoId = null;
}
