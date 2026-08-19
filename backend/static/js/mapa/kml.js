/**
 * Geração de KML no padrão do Mapa do Registro de Imóveis (ONR).
 *
 * Duas fontes definem o que este arquivo precisa cumprir:
 *
 * - Manual Técnico Operacional do Mapa, item 3.4.3: só polígonos
 *   fechados, sem linhas separadas, e coordenadas geográficas em datum
 *   SAD69 ou SIRGAS 2000. Os formatos aceitos são shapefile (preferido),
 *   .kml e .kmz; .dgn, .dxf e .dwg são recusados.
 * - Manual da API de Envio de Polígonos, item 6: a tabela de 34 atributos
 *   do imóvel. Ela está escrita para o shapefile, mas é o vocabulário do
 *   Mapa -- em KML, o lugar equivalente é ExtendedData.
 *
 * Sobre o datum: o KML é definido em WGS84, e o Mapa pede SIRGAS 2000.
 * Os dois coincidem no nível de centímetros, bem abaixo dos 8 cm de
 * precisão posicional que o próprio manual exige para vértice urbano
 * (item 3.7), então o arquivo é aceitável como SIRGAS 2000. O que NÃO
 * seria aceitável é declarar SAD69, que difere na casa das dezenas de
 * metros -- por isso o datum vai escrito no arquivo, e não subentendido.
 */

import {areaM2, perimetroM} from './geometria.js?v=20260819-poligonos-v4';

// Ordem e grafia exatas do item 6 do manual da API. Os nomes têm no
// máximo 10 caracteres porque no shapefile o QGIS trunca nesse tamanho
// (o script do manual faz `name[:10]`); manter iguais aqui evita que o
// mesmo imóvel chegue ao Mapa com nomes de campo diferentes conforme o
// formato escolhido.
export const CAMPOS_MAPA = [
    'MATRICULA', 'DAT_MAT', 'LIV_MAT', 'FOL_MAT', 'TRANSCRI', 'CNM', 'CNS',
    'ENDERECO', 'NUMERO', 'CEP', 'MUNICIPIO', 'UF', 'NOME_PROP', 'CPF_CNPJ',
    'CONF_MAT', 'CONF_NOM', 'REL_JUR', 'DAT_INI', 'DAT_FIM', 'PER_REL',
    'NOME_IMO', 'AREA_HA', 'AREA_M2', 'PERIM_M', 'PERIM_KM', 'CCIR_SNCR',
    'SIGEF', 'SNCI', 'CIB_NIRF', 'ITBI', 'CAR', 'RIP', 'CIF', 'CLASSIFICA',
];

// Categoria C do manual: "desenho em imagem de satélite ou google earth".
// É exatamente o que este módulo produz, e classificar como A ou B seria
// declarar uma certificação ou um levantamento que não existem.
const CATEGORIA_DESENHO_EM_SATELITE = '3';

const CASAS = 8;   // ~1 mm; a exigência do manual é 8 cm

function escapar(valor) {
    return String(valor ?? '').replace(/[&<>"']/g, c => (
        {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&apos;'}[c]
    ));
}

/** Área com sinal, só para descobrir o sentido do anel. */
function areaComSinal(anel) {
    let total = 0;
    for (let i = 0; i < anel.length; i += 1) {
        const [x1, y1] = anel[i];
        const [x2, y2] = anel[(i + 1) % anel.length];
        total += x1 * y2 - x2 * y1;
    }
    return total / 2;
}

/**
 * Prepara o anel para virar LinearRing do KML.
 *
 * Faz duas coisas que o formato exige e que o desenho na tela não
 * garante: fecha o anel repetindo o primeiro vértice no fim, e coloca os
 * vértices no sentido anti-horário, que é o que a especificação do KML
 * define para o contorno externo de um polígono.
 */
export function anelParaKml(anel) {
    const pontos = anel.map(([lon, lat]) => [lon, lat]);
    if (pontos.length > 1) {
        const [lonA, latA] = pontos[0];
        const [lonZ, latZ] = pontos[pontos.length - 1];
        if (lonA === lonZ && latA === latZ) pontos.pop();
    }
    if (areaComSinal(pontos) < 0) pontos.reverse();
    return [...pontos, pontos[0]];
}

function coordenadas(pontos) {
    // KML é sempre longitude,latitude,altitude -- nessa ordem.
    return pontos
        .map(([lon, lat]) => `${lon.toFixed(CASAS)},${lat.toFixed(CASAS)},0`)
        .join(' ');
}

function atributos(dados) {
    const anel = dados.anel || [];
    const fechado = dados.tipo === 'POLIGONO' && anel.length >= 3;
    const area = fechado ? areaM2(anel) : 0;
    const perimetro = perimetroM(anel, fechado);

    // Preenchido é só o que o AERI realmente sabe. Os demais campos vão
    // vazios, e não ausentes: quem receber o arquivo vê a estrutura
    // inteira e sabe o que falta completar, em vez de descobrir depois
    // que o Mapa recusou por campo que ninguém percebeu que existia.
    const conhecidos = {
        MATRICULA: (dados.matricula || '').replace(/\D/g, ''),
        NOME_IMO: dados.nome || '',
        AREA_HA: fechado ? (area / 10000).toFixed(4) : '',
        AREA_M2: fechado ? area.toFixed(2) : '',
        PERIM_M: perimetro ? perimetro.toFixed(2) : '',
        PERIM_KM: perimetro ? (perimetro / 1000).toFixed(4) : '',
        CLASSIFICA: CATEGORIA_DESENHO_EM_SATELITE,
    };
    return CAMPOS_MAPA.map(campo =>
        `        <Data name="${campo}"><value>`
        + `${escapar(conhecidos[campo] ?? '')}</value></Data>`,
    ).join('\n');
}

function geometria(dados) {
    const anel = dados.anel || [];
    if (dados.tipo === 'PONTO') {
        return `      <Point>
        <coordinates>${coordenadas(anel.slice(0, 1))}</coordinates>
      </Point>`;
    }
    if (dados.tipo === 'LINHA') {
        return `      <LineString>
        <coordinates>${coordenadas(anel)}</coordinates>
      </LineString>`;
    }
    return `      <Polygon>
        <altitudeMode>clampToGround</altitudeMode>
        <outerBoundaryIs>
          <LinearRing>
            <coordinates>${coordenadas(anelParaKml(anel))}</coordinates>
          </LinearRing>
        </outerBoundaryIs>
      </Polygon>`;
}

/** Monta o KML completo. Função pura, para poder ser testada fora do navegador. */
export function montarKml(dados) {
    const nome = dados.nome || 'Polígono';
    const descricao = [
        dados.matricula ? `Matrícula ${dados.matricula}` : '',
        dados.observacao || '',
        'Datum: SIRGAS 2000 (equivalente a WGS84 no nível de centímetros).',
        'Categoria C: desenho sobre imagem de satélite.',
    ].filter(Boolean).join(' — ');

    return `<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>${escapar(nome)}</name>
    <Placemark>
      <name>${escapar(nome)}</name>
      <description>${escapar(descricao)}</description>
      <ExtendedData>
${atributos(dados)}
      </ExtendedData>
${geometria(dados)}
    </Placemark>
  </Document>
</kml>
`;
}
