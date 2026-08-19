/**
 * Módulo Polígonos: desenhar, medir e conferir limites sobre satélite.
 *
 * O desenho vive em WGS84 (lon, lat) do começo ao fim. A tela é só uma
 * projeção disso -- por isso arrastar o mapa não muda um único vértice,
 * e mudar o zoom não muda a área.
 */
import {requisicaoAeri} from './api.js';
import {escaparHtml} from './util.js';
import {CAMADAS, criarMapa} from './mapa/motor.js?v=20260819-poligonos-v2';
import {
    areaM2, azimuteGraus, distanciaM, formatarArea, formatarDistancia,
    formatarGms, ladosDoAnel, perimetroM,
} from './mapa/geometria.js?v=20260819-poligonos-v2';

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
    tabela.innerHTML = ladosDoAnel(anel, fechado).map(lado => `
        <tr>
            <td>${lado.de} → ${lado.para}</td>
            <td>${lado.distancia.toLocaleString('pt-BR', {minimumFractionDigits: 2, maximumFractionDigits: 2})} m</td>
            <td>${lado.azimute.toLocaleString('pt-BR', {minimumFractionDigits: 2, maximumFractionDigits: 2})}°</td>
        </tr>`).join('');
}

function atualizarTudo() {
    redesenharVetores();
    atualizarMedidas();
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
    const fechar = rascunho.tipo === 'POLIGONO';
    const pontos = fechar ? [...rascunho.anel, rascunho.anel[0]] : rascunho.anel;
    // KML quer longitude,latitude,altitude separados por espaço.
    const coordenadas = pontos.map(([lon, lat]) => `${lon},${lat},0`).join(' ');
    const geometria = rascunho.tipo === 'PONTO'
        ? `<Point><coordinates>${coordenadas}</coordinates></Point>`
        : fechar
            ? `<Polygon><outerBoundaryIs><LinearRing><coordinates>${coordenadas}</coordinates></LinearRing></outerBoundaryIs></Polygon>`
            : `<LineString><coordinates>${coordenadas}</coordinates></LineString>`;
    baixar(`${nomeBase()}.kml`, `<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Placemark>
      <name>${escaparHtml(elemento('poligonos-nome').value.trim() || 'Polígono')}</name>
      ${geometria}
    </Placemark>
  </Document>
</kml>`, 'application/vnd.google-earth.kml+xml');
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
        elemento('poligonos-cursor').textContent =
            `${formatarGms(geo.lat, 'lat')}  ${formatarGms(geo.lon, 'lon')}`;
    });
    ligarArrasteDeVertices();

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
    atualizarMedidas();
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
