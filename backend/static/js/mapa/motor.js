/**
 * Motor de mapa deslizante (slippy map) do módulo Polígonos.
 *
 * Escrito à mão, sem biblioteca, porque a política de segurança do AERI
 * traz `script-src 'self'` -- nenhuma CDN carrega, e o projeto não tem
 * etapa de build para empacotar uma dependência. O que precisamos daqui
 * é pequeno e bem definido: projetar, mostrar tiles, arrastar, aproximar
 * e converter coordenada de tela para geográfica.
 *
 * Projeção: Web Mercator (EPSG:3857), a mesma dos tiles. Ela distorce
 * área, então NENHUMA medida sai deste arquivo -- área e distância são
 * calculadas sobre o elipsoide, em geometria.js e, com a palavra final,
 * no servidor.
 */

const TAMANHO_TILE = 256;
const ZOOM_MINIMO = 3;
const ZOOM_MAXIMO = 21;

export const CAMADAS = {
    satelite: {
        rotulo: 'Satélite',
        url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        creditos: 'Esri, Maxar, Earthstar Geographics',
        zoomMaximo: 19,
    },
    ruas: {
        rotulo: 'Ruas',
        url: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
        creditos: '© OpenStreetMap',
        zoomMaximo: 19,
    },
};

// ---------------------------------------------------------------------------
// Projeção
// ---------------------------------------------------------------------------

/** Longitude/latitude -> pixel do mundo, no zoom informado. */
export function geoParaMundo(lon, lat, zoom) {
    const escala = TAMANHO_TILE * Math.pow(2, zoom);
    // A latitude é travada no limite do Mercator: além disso a projeção
    // vai para o infinito, e um ponto fora de faixa levaria o mapa junto.
    const latTravada = Math.max(-85.05112878, Math.min(85.05112878, lat));
    const seno = Math.sin((latTravada * Math.PI) / 180);
    return {
        x: escala * (lon / 360 + 0.5),
        y: escala * (0.5 - Math.log((1 + seno) / (1 - seno)) / (4 * Math.PI)),
    };
}

/** Pixel do mundo -> longitude/latitude. */
export function mundoParaGeo(x, y, zoom) {
    const escala = TAMANHO_TILE * Math.pow(2, zoom);
    const n = Math.PI - (2 * Math.PI * y) / escala;
    return {
        lon: (x / escala - 0.5) * 360,
        lat: (180 / Math.PI) * Math.atan(Math.sinh(n)),
    };
}

// ---------------------------------------------------------------------------
// Mapa
// ---------------------------------------------------------------------------

export function criarMapa(elemento, opcoes = {}) {
    const estado = {
        centro: opcoes.centro || { lon: -49.1003, lat: -17.7305 }, // Morrinhos-GO
        zoom: opcoes.zoom ?? 14,
        camada: opcoes.camada || 'satelite',
        largura: 0,
        altura: 0,
    };

    elemento.classList.add('mapa-motor');
    elemento.innerHTML = '';

    const camadaTiles = document.createElement('div');
    camadaTiles.className = 'mapa-tiles';
    const camadaVetor = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    camadaVetor.setAttribute('class', 'mapa-vetor');
    const creditos = document.createElement('div');
    creditos.className = 'mapa-creditos';
    elemento.append(camadaTiles, camadaVetor, creditos);

    const ouvintes = { mudou: [], clicou: [], moveu: [] };
    const tilesVivos = new Map();

    function medir() {
        const caixa = elemento.getBoundingClientRect();
        estado.largura = caixa.width;
        estado.altura = caixa.height;
    }

    /** Pixel do mundo do canto superior esquerdo da viewport. */
    function origem() {
        const centro = geoParaMundo(estado.centro.lon, estado.centro.lat, estado.zoom);
        return { x: centro.x - estado.largura / 2, y: centro.y - estado.altura / 2 };
    }

    function geoParaTela(lon, lat) {
        const p = geoParaMundo(lon, lat, estado.zoom);
        const o = origem();
        return { x: p.x - o.x, y: p.y - o.y };
    }

    function telaParaGeo(x, y) {
        const o = origem();
        return mundoParaGeo(o.x + x, o.y + y, estado.zoom);
    }

    function desenharTiles() {
        const definicao = CAMADAS[estado.camada];
        // Tiles existem só em zoom inteiro. Acima do zoom máximo da fonte,
        // reaproveitamos o último nível disponível e ampliamos por CSS --
        // a imagem borra, mas o desenho vetorial continua nítido, que é o
        // que importa para conferir um limite.
        const zoomTile = Math.min(Math.round(estado.zoom), definicao.zoomMaximo);
        const escalaExtra = Math.pow(2, estado.zoom - zoomTile);

        const o = origem();
        // Converte a origem para o sistema de pixels do nível do tile.
        const fator = Math.pow(2, zoomTile - estado.zoom);
        const origemTile = { x: o.x * fator, y: o.y * fator };
        const larguraTile = estado.largura * fator;
        const alturaTile = estado.altura * fator;

        const total = Math.pow(2, zoomTile);
        const primeiroX = Math.floor(origemTile.x / TAMANHO_TILE);
        const primeiroY = Math.floor(origemTile.y / TAMANHO_TILE);
        const ultimoX = Math.floor((origemTile.x + larguraTile) / TAMANHO_TILE);
        const ultimoY = Math.floor((origemTile.y + alturaTile) / TAMANHO_TILE);

        const usados = new Set();
        for (let tx = primeiroX; tx <= ultimoX; tx += 1) {
            for (let ty = primeiroY; ty <= ultimoY; ty += 1) {
                if (ty < 0 || ty >= total) continue;      // fora dos polos
                const txCiclico = ((tx % total) + total) % total;  // dá a volta no globo
                const chave = `${zoomTile}/${txCiclico}/${ty}/${estado.camada}`;
                usados.add(chave);

                let img = tilesVivos.get(chave);
                if (!img) {
                    img = new Image();
                    img.className = 'mapa-tile';
                    img.alt = '';
                    img.decoding = 'async';
                    img.loading = 'eager';
                    // Sem referrer: não vaza a URL interna do AERI (que
                    // carrega token de sessão na query em alguns fluxos)
                    // para o servidor de tiles.
                    img.referrerPolicy = 'no-referrer';
                    img.src = definicao.url
                        .replace('{z}', zoomTile)
                        .replace('{x}', txCiclico)
                        .replace('{y}', ty);
                    tilesVivos.set(chave, img);
                    camadaTiles.appendChild(img);
                }
                const esquerda = (tx * TAMANHO_TILE - origemTile.x) * escalaExtra;
                const topo = (ty * TAMANHO_TILE - origemTile.y) * escalaExtra;
                img.style.transform = `translate(${esquerda}px, ${topo}px)`;
                img.style.width = `${TAMANHO_TILE * escalaExtra}px`;
                img.style.height = `${TAMANHO_TILE * escalaExtra}px`;
            }
        }

        for (const [chave, img] of tilesVivos) {
            if (!usados.has(chave)) {
                img.remove();
                tilesVivos.delete(chave);
            }
        }
        creditos.textContent = definicao.creditos;
    }

    function redesenhar() {
        // Mede sempre, e não só quando ainda não há medida. O mapa nasce
        // dentro de uma página oculta, de tamanho zero, e só ganha altura
        // quando a aba é aberta -- se dependesse do ResizeObserver para
        // descobrir isso, qualquer quadro não entregue deixaria o mapa em
        // branco de forma permanente. Um getBoundingClientRect por
        // redesenho não pesa perto do custo dos tiles.
        medir();
        camadaVetor.setAttribute('width', estado.largura);
        camadaVetor.setAttribute('height', estado.altura);
        camadaVetor.setAttribute('viewBox', `0 0 ${estado.largura} ${estado.altura}`);
        desenharTiles();
        ouvintes.mudou.forEach(f => f(instantaneo()));
    }

    function instantaneo() {
        return {
            centro: { ...estado.centro },
            zoom: estado.zoom,
            camada: estado.camada,
            largura: estado.largura,
            altura: estado.altura,
        };
    }

    function irPara(centro, zoom) {
        estado.centro = { lon: centro.lon, lat: centro.lat };
        if (zoom != null) estado.zoom = Math.max(ZOOM_MINIMO, Math.min(ZOOM_MAXIMO, zoom));
        redesenhar();
    }

    /** Enquadra um conjunto de pontos com folga nas bordas. */
    function ajustarPara(pontos, folga = 48) {
        const validos = (pontos || []).filter(p => Array.isArray(p) && p.length >= 2);
        if (!validos.length) return;
        if (!estado.largura) medir();

        const lons = validos.map(p => p[0]);
        const lats = validos.map(p => p[1]);
        const centro = {
            lon: (Math.min(...lons) + Math.max(...lons)) / 2,
            lat: (Math.min(...lats) + Math.max(...lats)) / 2,
        };
        if (validos.length === 1) { irPara(centro, 18); return; }

        // Procura o maior zoom em que a extensão ainda cabe na tela.
        let melhor = ZOOM_MINIMO;
        for (let z = ZOOM_MINIMO; z <= ZOOM_MAXIMO; z += 1) {
            const cantos = validos.map(p => geoParaMundo(p[0], p[1], z));
            const larg = Math.max(...cantos.map(c => c.x)) - Math.min(...cantos.map(c => c.x));
            const alt = Math.max(...cantos.map(c => c.y)) - Math.min(...cantos.map(c => c.y));
            if (larg <= estado.largura - folga * 2 && alt <= estado.altura - folga * 2) melhor = z;
            else break;
        }
        irPara(centro, melhor);
    }

    function definirCamada(nome) {
        if (!CAMADAS[nome] || nome === estado.camada) return;
        estado.camada = nome;
        // Tiles da camada anterior não servem: descarta tudo de uma vez.
        tilesVivos.forEach(img => img.remove());
        tilesVivos.clear();
        redesenhar();
    }

    function aplicarZoom(novoZoom, ancoraX, ancoraY) {
        const alvo = Math.max(ZOOM_MINIMO, Math.min(ZOOM_MAXIMO, novoZoom));
        if (alvo === estado.zoom) return;
        // Mantém sob o cursor o mesmo ponto do terreno: converte antes,
        // troca o zoom, e move o centro pela diferença.
        const geoAncora = telaParaGeo(ancoraX, ancoraY);
        estado.zoom = alvo;
        const depois = geoParaTela(geoAncora.lon, geoAncora.lat);
        const o = origem();
        const corrigido = mundoParaGeo(
            o.x + estado.largura / 2 + (depois.x - ancoraX),
            o.y + estado.altura / 2 + (depois.y - ancoraY),
            estado.zoom,
        );
        estado.centro = corrigido;
        redesenhar();
    }

    // --- interação -------------------------------------------------------
    let arrastando = null;

    function posicaoLocal(evento) {
        const caixa = elemento.getBoundingClientRect();
        return { x: evento.clientX - caixa.left, y: evento.clientY - caixa.top };
    }

    elemento.addEventListener('pointerdown', evento => {
        if (evento.button !== 0) return;
        // Alças de vértice tratam o próprio arrasto; o mapa não se move.
        if (evento.target.closest('[data-alca]')) return;
        const p = posicaoLocal(evento);
        arrastando = { ...p, moveu: false, centro: { ...estado.centro } };
        elemento.setPointerCapture(evento.pointerId);
    });

    elemento.addEventListener('pointermove', evento => {
        const p = posicaoLocal(evento);
        ouvintes.moveu.forEach(f => f(telaParaGeo(p.x, p.y), p));
        if (!arrastando) return;
        const dx = p.x - arrastando.x;
        const dy = p.y - arrastando.y;
        if (Math.abs(dx) > 3 || Math.abs(dy) > 3) arrastando.moveu = true;
        const centroMundo = geoParaMundo(arrastando.centro.lon, arrastando.centro.lat, estado.zoom);
        estado.centro = mundoParaGeo(centroMundo.x - dx, centroMundo.y - dy, estado.zoom);
        redesenhar();
    });

    function soltar(evento) {
        if (!arrastando) return;
        const p = posicaoLocal(evento);
        const clique = !arrastando.moveu;
        arrastando = null;
        if (clique) ouvintes.clicou.forEach(f => f(telaParaGeo(p.x, p.y), p, evento));
    }
    elemento.addEventListener('pointerup', soltar);
    elemento.addEventListener('pointercancel', () => { arrastando = null; });

    elemento.addEventListener('wheel', evento => {
        evento.preventDefault();
        const p = posicaoLocal(evento);
        // Passo fracionário deixa a aproximação contínua em vez de saltar
        // de nível em nível.
        aplicarZoom(estado.zoom - Math.sign(evento.deltaY) * 0.5, p.x, p.y);
    }, { passive: false });

    elemento.addEventListener('dblclick', evento => {
        evento.preventDefault();
        const p = posicaoLocal(evento);
        aplicarZoom(Math.round(estado.zoom) + 1, p.x, p.y);
    });

    const observador = new ResizeObserver(() => { medir(); redesenhar(); });
    observador.observe(elemento);

    medir();
    redesenhar();

    return {
        camadaVetor,
        estado: instantaneo,
        irPara,
        ajustarPara,
        definirCamada,
        redesenhar,
        geoParaTela,
        telaParaGeo,
        aproximar: (passo = 1) => aplicarZoom(
            Math.round(estado.zoom) + passo, estado.largura / 2, estado.altura / 2),
        ao: (nome, funcao) => { ouvintes[nome]?.push(funcao); },
        destruir: () => { observador.disconnect(); elemento.innerHTML = ''; },
    };
}
