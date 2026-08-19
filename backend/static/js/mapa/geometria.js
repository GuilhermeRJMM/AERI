/**
 * Medidas geodésicas no navegador, para a leitura acompanhar o mouse.
 *
 * É o espelho de backend/app/servicos/poligonos.py e tem de dar o mesmo
 * número -- há teste comparando os dois. Ainda assim, o valor que vai
 * para o banco e para o documento é sempre o que o servidor calcula:
 * aqui é conforto de interface, lá é a fonte da verdade.
 */

const A = 6378137.0;
const F = 1 / 298.257223563;
const B = A * (1 - F);
const E2 = F * (2 - F);
const E = Math.sqrt(E2);

function q(senoLat) {
    return (1 - E2) * (
        senoLat / (1 - E2 * senoLat * senoLat)
        - (1 / (2 * E)) * Math.log((1 - E * senoLat) / (1 + E * senoLat))
    );
}

const Q_POLO = q(1.0);
const RAIO_AUTALICO = A * Math.sqrt(Q_POLO / 2);

function latitudeAutalica(graus) {
    const seno = Math.sin((graus * Math.PI) / 180);
    return Math.asin(Math.max(-1, Math.min(1, q(seno) / Q_POLO)));
}

function normalizarDeltaLongitude(radianos) {
    let d = radianos;
    while (d > Math.PI) d -= 2 * Math.PI;
    while (d <= -Math.PI) d += 2 * Math.PI;
    return d;
}

function anelLimpo(anel) {
    const pontos = (anel || [])
        .filter(p => Array.isArray(p) && p.length >= 2
            && Number.isFinite(p[0]) && Number.isFinite(p[1]))
        .map(p => [p[0], p[1]]);
    if (pontos.length > 1
        && pontos[0][0] === pontos[pontos.length - 1][0]
        && pontos[0][1] === pontos[pontos.length - 1][1]) pontos.pop();
    return pontos;
}

/** Área sobre o elipsoide, em metros quadrados. */
export function areaM2(anel) {
    const p = anelLimpo(anel);
    if (p.length < 3) return 0;
    let total = 0;
    for (let i = 0; i < p.length; i += 1) {
        const [lon1, lat1] = p[i];
        const [lon2, lat2] = p[(i + 1) % p.length];
        const dLon = normalizarDeltaLongitude(
            (lon2 * Math.PI) / 180 - (lon1 * Math.PI) / 180);
        total += dLon * (
            Math.sin(latitudeAutalica(lat1)) + Math.sin(latitudeAutalica(lat2)));
    }
    return (Math.abs(total) * RAIO_AUTALICO * RAIO_AUTALICO) / 2;
}

/** Distância geodésica entre dois pontos (Vincenty inverso), em metros. */
export function distanciaM(a, b) {
    return vincenty(a, b).distancia;
}

/** Azimute inicial de A para B, em graus a partir do norte. */
export function azimuteGraus(a, b) {
    return (vincenty(a, b).azimute + 360) % 360;
}

function vincenty(pa, pb) {
    const [lon1, lat1] = pa;
    const [lon2, lat2] = pb;
    if (lon1 === lon2 && lat1 === lat2) return { distancia: 0, azimute: 0 };

    const rad = g => (g * Math.PI) / 180;
    const u1 = Math.atan((1 - F) * Math.tan(rad(lat1)));
    const u2 = Math.atan((1 - F) * Math.tan(rad(lat2)));
    const deltaLon = rad(lon2 - lon1);
    const sinU1 = Math.sin(u1); const cosU1 = Math.cos(u1);
    const sinU2 = Math.sin(u2); const cosU2 = Math.cos(u2);

    let lambda = deltaLon;
    let sinSigma = 0; let cosSigma = 0; let sigma = 0;
    let cos2Alfa = 0; let cos2SigmaM = 0; let sinAlfa = 0;
    for (let i = 0; i < 200; i += 1) {
        const sinLambda = Math.sin(lambda); const cosLambda = Math.cos(lambda);
        sinSigma = Math.sqrt(
            (cosU2 * sinLambda) ** 2
            + (cosU1 * sinU2 - sinU1 * cosU2 * cosLambda) ** 2);
        if (sinSigma === 0) return { distancia: 0, azimute: 0 };
        cosSigma = sinU1 * sinU2 + cosU1 * cosU2 * cosLambda;
        sigma = Math.atan2(sinSigma, cosSigma);
        sinAlfa = (cosU1 * cosU2 * sinLambda) / sinSigma;
        cos2Alfa = 1 - sinAlfa * sinAlfa;
        cos2SigmaM = cos2Alfa !== 0 ? cosSigma - (2 * sinU1 * sinU2) / cos2Alfa : 0;
        const c = (F / 16) * cos2Alfa * (4 + F * (4 - 3 * cos2Alfa));
        const anterior = lambda;
        lambda = deltaLon + (1 - c) * F * sinAlfa * (
            sigma + c * sinSigma * (
                cos2SigmaM + c * cosSigma * (-1 + 2 * cos2SigmaM ** 2)));
        if (Math.abs(lambda - anterior) < 1e-12) break;
    }

    const uQuad = (cos2Alfa * (A * A - B * B)) / (B * B);
    const fatorA = 1 + (uQuad / 16384) * (
        4096 + uQuad * (-768 + uQuad * (320 - 175 * uQuad)));
    const fatorB = (uQuad / 1024) * (
        256 + uQuad * (-128 + uQuad * (74 - 47 * uQuad)));
    const deltaSigma = fatorB * sinSigma * (
        cos2SigmaM + (fatorB / 4) * (
            cosSigma * (-1 + 2 * cos2SigmaM ** 2)
            - (fatorB / 6) * cos2SigmaM * (-3 + 4 * sinSigma ** 2)
            * (-3 + 4 * cos2SigmaM ** 2)));

    const sinLambda = Math.sin(lambda); const cosLambda = Math.cos(lambda);
    return {
        distancia: B * fatorA * (sigma - deltaSigma),
        azimute: (Math.atan2(
            cosU2 * sinLambda,
            cosU1 * sinU2 - sinU1 * cosU2 * cosLambda) * 180) / Math.PI,
    };
}

export function perimetroM(anel, fechado = true) {
    const p = anelLimpo(anel);
    if (p.length < 2) return 0;
    let total = 0;
    for (let i = 0; i < p.length - 1; i += 1) total += distanciaM(p[i], p[i + 1]);
    if (fechado && p.length > 2) total += distanciaM(p[p.length - 1], p[0]);
    return total;
}

// ---------------------------------------------------------------------------
// Apresentação das medidas
// ---------------------------------------------------------------------------

const ALQUEIRE_GOIANO_M2 = 48400;   // 4,84 ha, a medida usada na região

export function formatarArea(m2) {
    if (!m2) return '—';
    const ha = m2 / 10000;
    const numero = (valor, casas) => valor.toLocaleString('pt-BR', {
        minimumFractionDigits: casas, maximumFractionDigits: casas,
    });
    if (m2 < 10000) return `${numero(m2, 2)} m²`;
    return `${numero(ha, 4)} ha  ·  ${numero(m2 / ALQUEIRE_GOIANO_M2, 4)} alq.  ·  ${numero(m2, 2)} m²`;
}

export function formatarDistancia(m) {
    if (!m) return '—';
    const numero = (valor, casas) => valor.toLocaleString('pt-BR', {
        minimumFractionDigits: casas, maximumFractionDigits: casas,
    });
    return m < 1000 ? `${numero(m, 2)} m` : `${numero(m / 1000, 3)} km`;
}

export function formatarGms(valor, eixo) {
    const positivo = valor >= 0;
    const absoluto = Math.abs(valor);
    const graus = Math.floor(absoluto);
    const minutosDecimais = (absoluto - graus) * 60;
    const minutos = Math.floor(minutosDecimais);
    const segundos = (minutosDecimais - minutos) * 60;
    const letra = eixo === 'lat' ? (positivo ? 'N' : 'S') : (positivo ? 'E' : 'W');
    return `${graus}°${String(minutos).padStart(2, '0')}'`
        + `${segundos.toFixed(3).padStart(6, '0')}"${letra}`;
}

/** Lados do polígono com distância e azimute, como num memorial. */
export function ladosDoAnel(anel, fechado = true) {
    const p = anelLimpo(anel);
    const lados = [];
    const ate = fechado ? p.length : p.length - 1;
    for (let i = 0; i < ate; i += 1) {
        const a = p[i];
        const b = p[(i + 1) % p.length];
        if (!b) break;
        lados.push({
            de: i + 1,
            para: ((i + 1) % p.length) + 1,
            distancia: distanciaM(a, b),
            azimute: azimuteGraus(a, b),
        });
    }
    return lados;
}
