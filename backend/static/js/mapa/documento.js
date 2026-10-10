/** Planta A4 e memorial imprimível do módulo Polígonos. */
import {
    areaM2, formatarArea, formatarGms, ladosDoAnel, perimetroM,
} from './geometria.js?v=20261008-poligonos-v14';

const POSICOES = {
    FRENTE: 'frente',
    CHANFRO: 'chanfro',
    FUNDOS: 'fundos',
    DIREITO: 'lado direito',
    ESQUERDO: 'lado esquerdo',
    OUTRO: 'outro lado',
};

function escapar(valor) {
    return String(valor ?? '').replace(/[&<>"']/g, caractere => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    })[caractere]);
}

function numero(valor, casas = 2) {
    return Number(valor || 0).toLocaleString('pt-BR', {
        minimumFractionDigits: casas,
        maximumFractionDigits: casas,
    });
}

// A gramática de atributos SVG exige ponto decimal; vírgula é separador de
// coordenadas e não pode vir do formato local usado nos textos visíveis.
function svgNumero(valor) {
    return Number(valor || 0).toFixed(3);
}

function nomeVertice(ordem) {
    return `P-${String(ordem).padStart(2, '0')}`;
}

function confrontanteDo(memorial, indice) {
    return String(memorial.lados?.[indice]?.confrontante || '').trim();
}

function classeDo(memorial, indice) {
    return POSICOES[memorial.lados?.[indice]?.posicao] || POSICOES.OUTRO;
}

function qualificacaoDoLado(memorial, indice) {
    return {
        FRENTE: 'pela frente', CHANFRO: 'pelo chanfro', FUNDOS: 'pelos fundos',
        DIREITO: 'pelo lado direito', ESQUERDO: 'pelo lado esquerdo',
        OUTRO: 'por outro lado',
    }[memorial.lados?.[indice]?.posicao] || 'por outro lado';
}

function textoConfrontante(memorial, indice) {
    return escapar(confrontanteDo(memorial, indice) || 'confrontante não informado');
}

function gerarDescricaoConfrontacoes(lados, memorial) {
    return 'O perímetro percorre os seguintes lados: ' + lados.map((lado, indice) => {
        return `do vértice ${nomeVertice(lado.de)} ao vértice ${nomeVertice(lado.para)}, `
            + `com ${numero(lado.distancia)} metros ${qualificacaoDoLado(memorial, indice)}, `
            + `confrontando com ${textoConfrontante(memorial, indice)}`;
    }).join('; ') + '.';
}

function gerarDescricaoVertices(lados, verticesUtm, memorial) {
    const primeiro = verticesUtm[0];
    const partes = [
        `Inicia-se no vértice ${nomeVertice(1)}, de coordenadas UTM `
        + `Este ${numero(primeiro.leste, 3)} m e Norte ${numero(primeiro.norte, 3)} m`,
    ];
    lados.forEach((lado, indice) => {
        const destino = verticesUtm[lado.para - 1];
        const coordenada = lado.para === 1
            ? 'ponto inicial do perímetro'
            : `coordenadas UTM Este ${numero(destino.leste, 3)} m e Norte ${numero(destino.norte, 3)} m`;
        partes.push(
            `segue com azimute geodésico de ${numero(lado.azimute, 4)} graus `
            + `e distância de ${numero(lado.distancia)} metros ${qualificacaoDoLado(memorial, indice)}, `
            + `confrontando com ${textoConfrontante(memorial, indice)}, `
            + `até o vértice ${nomeVertice(lado.para)}, ${coordenada}`,
        );
    });
    return `${partes.join('; ')}.`;
}

function escalaAdequada(largura, altura, areaLargura, areaAltura) {
    const necessario = Math.max(largura * 1000 / areaLargura, altura * 1000 / areaAltura, 1);
    const escalas = [50, 75, 100, 125, 150, 200, 250, 300, 400, 500, 600, 750,
        1000, 1250, 1500, 2000, 2500, 3000, 4000, 5000, 6000, 7500, 10000,
        12500, 15000, 20000, 25000, 50000, 100000];
    return escalas.find(escala => escala >= necessario)
        || Math.ceil(necessario / 10000) * 10000;
}

function rosaDosVentos(x, y) {
    return `<g class="rosa-ventos" transform="translate(${svgNumero(x)} ${svgNumero(y)})" aria-label="Rosa dos ventos, norte da quadrícula para cima">
        <circle r="13" fill="#fff" stroke="#182433" stroke-width="0.45"/>
        <path d="M0 -11 L3.1 0 L0 -2.2 L-3.1 0 Z" fill="#102b4e"/>
        <path d="M0 11 L3.1 0 L0 2.2 L-3.1 0 Z" fill="#fff" stroke="#182433" stroke-width="0.35"/>
        <path d="M-10 0 H10 M0 -10 V10" stroke="#526174" stroke-width="0.35"/>
        <circle r="1.2" fill="#182433"/>
        <text x="0" y="-15" text-anchor="middle" font-size="3.3" font-weight="700">N</text>
        <text x="15" y="1.1" text-anchor="middle" font-size="2.4">E</text>
        <text x="0" y="17.5" text-anchor="middle" font-size="2.4">S</text>
        <text x="-15" y="1.1" text-anchor="middle" font-size="2.4">O</text>
    </g>`;
}

function barraEscala(escala) {
    const metrosAlvo = 35 * escala / 1000;
    const potencia = 10 ** Math.floor(Math.log10(Math.max(1, metrosAlvo)));
    const normalizado = metrosAlvo / potencia;
    const fator = normalizado >= 5 ? 5 : normalizado >= 2 ? 2 : 1;
    const metros = fator * potencia;
    const milimetros = metros * 1000 / escala;
    return `<g class="barra-escala" transform="translate(18 169)">
        <rect x="0" y="0" width="${svgNumero(milimetros / 2)}" height="2.2" fill="#182433"/>
        <rect x="${svgNumero(milimetros / 2)}" y="0" width="${svgNumero(milimetros / 2)}" height="2.2" fill="#fff" stroke="#182433" stroke-width="0.35"/>
        <text x="0" y="-1.5" font-size="2.8">0</text>
        <text x="${svgNumero(milimetros)}" y="-1.5" text-anchor="end" font-size="2.8">${numero(metros, 0)} m</text>
    </g>`;
}

function textoMapa(texto, limite = 30) {
    const limpo = String(texto || '').trim();
    return limpo.length > limite ? `${limpo.slice(0, limite - 1)}…` : limpo;
}

function montarSvgPlanta(verticesUtm, lados, memorial) {
    const larguraSvg = 180;
    const alturaSvg = 185;
    const quadro = {x: 10, y: 12, largura: 138, altura: 148};
    const leste = verticesUtm.map(p => p.leste);
    const norte = verticesUtm.map(p => p.norte);
    const {min: minE, max: maxE} = leste.reduce((faixa, valor) => ({
        min: Math.min(faixa.min, valor), max: Math.max(faixa.max, valor),
    }), {min: Infinity, max: -Infinity});
    const {min: minN, max: maxN} = norte.reduce((faixa, valor) => ({
        min: Math.min(faixa.min, valor), max: Math.max(faixa.max, valor),
    }), {min: Infinity, max: -Infinity});
    const larguraMetros = Math.max(maxE - minE, 0.01);
    const alturaMetros = Math.max(maxN - minN, 0.01);
    const escala = escalaAdequada(larguraMetros, alturaMetros, quadro.largura - 30, quadro.altura - 30);
    const mmPorMetro = 1000 / escala;
    const larguraDesenho = larguraMetros * mmPorMetro;
    const alturaDesenho = alturaMetros * mmPorMetro;
    const x0 = quadro.x + (quadro.largura - larguraDesenho) / 2;
    const y0 = quadro.y + (quadro.altura - alturaDesenho) / 2;
    const pontos = verticesUtm.map(p => [
        x0 + (p.leste - minE) * mmPorMetro,
        y0 + (maxN - p.norte) * mmPorMetro,
    ]);
    const areaSinal = pontos.reduce((soma, p, indice) => {
        const q = pontos[(indice + 1) % pontos.length];
        return soma + p[0] * q[1] - q[0] * p[1];
    }, 0);
    const poligono = pontos.map(p => `${svgNumero(p[0])},${svgNumero(p[1])}`).join(' ');
    const medidas = lados.map((lado, indice) => {
        const a = pontos[lado.de - 1]; const b = pontos[lado.para - 1];
        const dx = b[0] - a[0]; const dy = b[1] - a[1];
        const comprimento = Math.hypot(dx, dy) || 1;
        const meioX = (a[0] + b[0]) / 2; const meioY = (a[1] + b[1]) / 2;
        let angulo = Math.atan2(dy, dx) * 180 / Math.PI;
        if (angulo > 90 || angulo < -90) angulo += 180;
        const larguraTexto = Math.min(27, Math.max(12, numero(lado.distancia).length * 1.7));
        const fora = areaSinal >= 0 ? 1 : -1;
        const normalX = (dy / comprimento) * fora;
        const normalY = (-dx / comprimento) * fora;
        const confrontante = textoMapa(confrontanteDo(memorial, indice), 27);
        return `<g class="medida-planta" transform="translate(${svgNumero(meioX)} ${svgNumero(meioY)}) rotate(${svgNumero(angulo)})">
            <rect x="${svgNumero(-larguraTexto / 2)}" y="-2.2" width="${svgNumero(larguraTexto)}" height="3" rx="0.6" fill="#fff"/>
            <text x="0" y="0" text-anchor="middle" dominant-baseline="central" font-size="2.5">${numero(lado.distancia)} m</text>
        </g>${confrontante ? `<text class="confrontante-planta" x="${svgNumero(meioX + normalX * 5.2)}" y="${svgNumero(meioY + normalY * 5.2)}" text-anchor="middle" dominant-baseline="central" font-size="2.5">${escapar(confrontante)}</text>` : ''}`;
    }).join('');
    const marcadores = pontos.map((p, indice) => `<g class="vertice-planta">
        <circle cx="${svgNumero(p[0])}" cy="${svgNumero(p[1])}" r="1.05" fill="#102b4e" stroke="#fff" stroke-width="0.45"/>
        <text x="${svgNumero(p[0] + 2.2)}" y="${svgNumero(p[1] - 2.2)}" font-size="2.8" font-weight="700">${nomeVertice(indice + 1)}</text>
    </g>`).join('');

    return `<svg class="poligonos-planta-svg" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${larguraSvg} ${alturaSvg}" role="img" aria-label="Planta esquemática com rosa dos ventos">
        <rect x="0.3" y="0.3" width="${larguraSvg - 0.6}" height="${alturaSvg - 0.6}" fill="#fff" stroke="#9aa4b2" stroke-width="0.3"/>
        <polygon points="${poligono}" fill="#f8fafc" stroke="#102b4e" stroke-width="0.8" stroke-linejoin="round"/>
        ${medidas}${marcadores}${rosaDosVentos(163, 25)}${barraEscala(escala)}
        <text x="162" y="60" text-anchor="middle" font-size="2.5">Norte da</text>
        <text x="162" y="64" text-anchor="middle" font-size="2.5">quadrícula</text>
        <text x="162" y="174" text-anchor="middle" font-size="2.7">Escala</text>
        <text x="162" y="178" text-anchor="middle" font-size="3" font-weight="700">1:${numero(escala, 0)}</text>
    </svg>`;
}

function linhasFaltantes(memorial, lados) {
    return lados.map((lado, indice) => confrontanteDo(memorial, indice)
        ? '' : `${nomeVertice(lado.de)}–${nomeVertice(lado.para)}`).filter(Boolean);
}

function tabelaVertices(verticesUtm, anel) {
    return verticesUtm.map((v, indice) => {
        const [lon, lat] = anel[indice];
        return `<tr><td>${nomeVertice(indice + 1)}</td><td>${numero(v.leste, 3)}</td>
            <td>${numero(v.norte, 3)}</td><td>${formatarGms(lat, 'lat')}</td>
            <td>${formatarGms(lon, 'lon')}</td></tr>`;
    }).join('');
}

function tabelaLados(lados, memorial) {
    return lados.map((lado, indice) => `<tr>
        <td>${nomeVertice(lado.de)} → ${nomeVertice(lado.para)}</td>
        <td>${classeDo(memorial, indice)}</td>
        <td>${numero(lado.distancia)} m</td>
        <td>${numero(lado.azimute, 4)}°</td>
        <td>${escapar(confrontanteDo(memorial, indice) || 'Não informado')}</td>
    </tr>`).join('');
}

/** Produz duas folhas A4: planta esquemática com rosa e memorial conferível. */
export function montarDocumentoPoligonos(dados) {
    const anel = dados.anel || [];
    const verticesUtm = dados.utm?.vertices || [];
    if (anel.length < 3 || verticesUtm.length !== anel.length) {
        throw new Error('O desenho precisa ter pelo menos três vértices e coordenadas UTM correspondentes.');
    }
    const mapa = dados.dadosMapa || {};
    const memorial = mapa.memorial || {};
    const lados = ladosDoAnel(anel, true);
    const area = areaM2(anel);
    const perimetro = perimetroM(anel, true);
    const hemisferio = anel[0][1] < 0 ? 'S' : 'N';
    const sistema = `UTM fuso ${dados.utm.fuso}${hemisferio} · coordenadas convertidas a partir do WGS84 armazenado no AERI`;
    const titulo = escapar(dados.nome || 'Imóvel sem nome');
    const identificacao = [
        dados.matricula ? `Matrícula ${escapar(dados.matricula)}` : '',
        memorial.lote ? `Lote ${escapar(memorial.lote)}` : '',
        memorial.quadra ? `Quadra ${escapar(memorial.quadra)}` : '',
        memorial.setor ? escapar(memorial.setor) : '',
    ].filter(Boolean).join(' · ');
    const endereco = [memorial.logradouro, mapa.endereco, mapa.numero,
        mapa.municipio, mapa.uf].filter(Boolean).map(escapar).join(', ');
    const descricao = memorial.estilo === 'VERTICES'
        ? gerarDescricaoVertices(lados, verticesUtm, memorial)
        : gerarDescricaoConfrontacoes(lados, memorial);
    const faltantes = linhasFaltantes(memorial, lados);
    const avisoFaltantes = faltantes.length
        ? `<p class="poligonos-aviso-print"><strong>Conferir confrontantes:</strong> ${faltantes.map(escapar).join(', ')} sem informação.</p>`
        : '';
    const proprietarios = escapar(mapa.proprietarios || 'Não informado');
    const documentos = escapar(mapa.documentos || 'Não informado');
    const nomeResponsavel = escapar(memorial.responsavelNome || '');
    const tituloResponsavel = escapar(memorial.responsavelTitulo || '');
    const registro = [memorial.responsavelConselho, memorial.responsavelRegistro]
        .filter(Boolean).map(escapar).join(' ');
    const assinaProprietario = memorial.assinarProprietario === true;
    const fuso = numero(dados.utm.fuso, 0);
    const localidade = [mapa.municipio, mapa.uf].filter(Boolean).map(escapar).join(' / ');

    return `<article class="poligonos-folha poligonos-folha-planta">
        <header class="poligonos-print-cabecalho">
            <span>PLANTA DO IMÓVEL</span><h1>${titulo}</h1>
            ${identificacao ? `<p>${identificacao}</p>` : ''}
        </header>
        <div class="poligonos-print-resumo">
            <div><span>Proprietário(s)</span><strong>${proprietarios}</strong><small>CPF/CNPJ: ${documentos}</small></div>
            <div><span>Área</span><strong>${formatarArea(area)}</strong><small>Perímetro: ${numero(perimetro)} m</small></div>
            <div><span>Localidade</span><strong>${localidade || 'Não informada'}</strong><small>${endereco || 'Endereço não informado'}</small></div>
        </div>
        ${montarSvgPlanta(verticesUtm, lados, memorial)}
        <footer class="poligonos-print-rodape">${sistema}. Medidas de lados e azimutes calculados sobre o elipsoide WGS84.</footer>
    </article>
    <article class="poligonos-folha poligonos-folha-memorial">
        <header class="poligonos-print-cabecalho"><span>DOCUMENTO PARA CONFERÊNCIA</span>
            <h1>Memorial descritivo</h1><p>${titulo}${identificacao ? ` · ${identificacao}` : ''}</p></header>
        <table class="poligonos-print-identificacao"><tbody>
            <tr><th>Proprietário(s)</th><td>${proprietarios}</td><th>CPF/CNPJ</th><td>${documentos}</td></tr>
            <tr><th>Imóvel</th><td colspan="3">${endereco || 'Endereço não informado'}</td></tr>
            <tr><th>Área</th><td>${formatarArea(area)}</td><th>Perímetro</th><td>${numero(perimetro)} m</td></tr>
            <tr><th>Sistema de coordenadas</th><td colspan="3">${sistema}</td></tr>
        </tbody></table>
        <h2>Descrição do perímetro</h2>
        <p class="poligonos-texto-legal">${descricao}</p>
        ${avisoFaltantes}
        <h2>Quadro de vértices</h2>
        <div class="poligonos-print-tabela"><table><thead><tr><th>Vértice</th><th>Este (m)</th><th>Norte (m)</th><th>Latitude</th><th>Longitude</th></tr></thead>
            <tbody>${tabelaVertices(verticesUtm, anel)}</tbody></table></div>
        <h2>Quadro de lados e confrontações</h2>
        <div class="poligonos-print-tabela"><table><thead><tr><th>Trecho</th><th>Posição</th><th>Distância</th><th>Azimute</th><th>Confrontante</th></tr></thead>
            <tbody>${tabelaLados(lados, memorial)}</tbody></table></div>
        <p class="poligonos-ressalva">Minuta gerada a partir das coordenadas e informações inseridas no AERI. Confira o levantamento, datum, fuso, medidas, confrontações e demais exigências técnicas antes de assinar ou apresentar. Esta prévia não substitui levantamento, certificação ou responsabilidade técnica.</p>
        <div class="poligonos-assinaturas">
            <div><span></span><strong>${nomeResponsavel || 'Responsável técnico'}</strong>
                <small>${[tituloResponsavel, registro, memorial.art ? `ART/RRT ${escapar(memorial.art)}` : ''].filter(Boolean).join(' · ')}</small>
                <small>Responsável técnico</small></div>
            ${assinaProprietario ? `<div><span></span><strong>${proprietarios}</strong><small>Proprietário(a)</small></div>` : ''}
        </div>
    </article>`;
}
