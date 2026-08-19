"""Geometria dos desenhos do módulo Polígonos.

Tudo aqui trabalha em WGS84 (longitude, latitude) em graus decimais, na
ordem do GeoJSON. A escolha de guardar em graus, e não em UTM, é para o
dado não carregar o fuso junto: um imóvel na divisa de fuso continua
sendo um polígono só, e a conversão para UTM ou GMS acontece na leitura.

Área e distância são calculadas sobre o elipsoide, não sobre um plano.
Num cartório isso não é preciosismo: projetar 100 ha em UTM e medir no
plano erra na casa de centenas de metros quadrados, o que é diferença
suficiente para não bater com o memorial descritivo.
"""
import math
import re
import unicodedata


# WGS84
_A = 6378137.0                      # semieixo maior, em metros
_F = 1 / 298.257223563              # achatamento
_B = _A * (1 - _F)                  # semieixo menor
_E2 = _F * (2 - _F)                 # primeira excentricidade ao quadrado
_E = math.sqrt(_E2)


def _q(seno_lat: float) -> float:
    """Função auxiliar de área autálica de Snyder (1987), eq. 3-12."""
    if _E == 0:
        return 2 * seno_lat
    return (1 - _E2) * (
        seno_lat / (1 - _E2 * seno_lat * seno_lat)
        - (1 / (2 * _E)) * math.log((1 - _E * seno_lat) / (1 + _E * seno_lat))
    )


_Q_POLO = _q(1.0)
# Raio da esfera de mesma área que o elipsoide. Medir o polígono nessa
# esfera, com as latitudes convertidas para autálicas, dá a área
# elipsoidal com erro relativo na casa de 1e-9 -- ou seja, milímetros
# quadrados numa fazenda inteira.
_RAIO_AUTALICO = _A * math.sqrt(_Q_POLO / 2)


def _latitude_autalica(latitude_graus: float) -> float:
    seno = math.sin(math.radians(latitude_graus))
    razao = _q(seno) / _Q_POLO
    # Fora de [-1, 1] só por erro de arredondamento perto do polo.
    return math.asin(max(-1.0, min(1.0, razao)))


def _normalizar_delta_longitude(delta_radianos: float) -> float:
    """Traz a diferença de longitude para (-pi, pi].

    Sem isso, um polígono que cruza o antimeridiano daria a área do
    complemento. Não acontece em Goiás, mas o dado importado pode vir de
    qualquer lugar e o custo de tratar é uma linha.
    """
    while delta_radianos > math.pi:
        delta_radianos -= 2 * math.pi
    while delta_radianos <= -math.pi:
        delta_radianos += 2 * math.pi
    return delta_radianos


def area_m2(anel: list) -> float:
    """Área do polígono sobre o elipsoide, em metros quadrados.

    O anel é fechado automaticamente: o último ponto não precisa repetir
    o primeiro. Menos de três vértices não delimita área alguma.
    """
    pontos = _anel_limpo(anel)
    if len(pontos) < 3:
        return 0.0

    total = 0.0
    for indice in range(len(pontos)):
        lon1, lat1 = pontos[indice]
        lon2, lat2 = pontos[(indice + 1) % len(pontos)]
        delta_lon = _normalizar_delta_longitude(
            math.radians(lon2) - math.radians(lon1))
        total += delta_lon * (
            math.sin(_latitude_autalica(lat1)) + math.sin(_latitude_autalica(lat2)))

    # O sinal indica só a orientação do anel (horário x anti-horário).
    return abs(total) * _RAIO_AUTALICO * _RAIO_AUTALICO / 2.0


def distancia_m(ponto_a: tuple, ponto_b: tuple) -> float:
    """Distância geodésica entre dois pontos, em metros (Vincenty inverso)."""
    return _vincenty(ponto_a, ponto_b)[0]


def azimute_graus(ponto_a: tuple, ponto_b: tuple) -> float:
    """Azimute inicial de A para B, em graus a partir do norte."""
    return _vincenty(ponto_a, ponto_b)[1] % 360.0


def _vincenty(ponto_a: tuple, ponto_b: tuple) -> tuple:
    """Vincenty inverso: devolve (distância em metros, azimute em graus).

    Converge em milímetros para qualquer par de pontos que não seja
    quase antipodal -- caso que não existe dentro de uma matrícula.
    """
    lon1, lat1 = float(ponto_a[0]), float(ponto_a[1])
    lon2, lat2 = float(ponto_b[0]), float(ponto_b[1])
    if lon1 == lon2 and lat1 == lat2:
        return 0.0, 0.0

    u1 = math.atan((1 - _F) * math.tan(math.radians(lat1)))
    u2 = math.atan((1 - _F) * math.tan(math.radians(lat2)))
    delta_lon = math.radians(lon2 - lon1)
    sin_u1, cos_u1 = math.sin(u1), math.cos(u1)
    sin_u2, cos_u2 = math.sin(u2), math.cos(u2)

    lambda_atual = delta_lon
    sin_sigma = cos_sigma = sigma = sin_alfa = cos2_alfa = cos_2sigma_m = 0.0
    for _ in range(200):
        sin_lambda, cos_lambda = math.sin(lambda_atual), math.cos(lambda_atual)
        sin_sigma = math.sqrt(
            (cos_u2 * sin_lambda) ** 2
            + (cos_u1 * sin_u2 - sin_u1 * cos_u2 * cos_lambda) ** 2
        )
        if sin_sigma == 0:
            return 0.0, 0.0
        cos_sigma = sin_u1 * sin_u2 + cos_u1 * cos_u2 * cos_lambda
        sigma = math.atan2(sin_sigma, cos_sigma)
        sin_alfa = cos_u1 * cos_u2 * sin_lambda / sin_sigma
        cos2_alfa = 1 - sin_alfa * sin_alfa
        # cos2_alfa == 0 na linha do equador, onde não há termo de latitude.
        cos_2sigma_m = (
            cos_sigma - 2 * sin_u1 * sin_u2 / cos2_alfa if cos2_alfa != 0 else 0.0
        )
        correcao = (
            _F / 16 * cos2_alfa * (4 + _F * (4 - 3 * cos2_alfa))
        )
        lambda_anterior = lambda_atual
        lambda_atual = delta_lon + (1 - correcao) * _F * sin_alfa * (
            sigma + correcao * sin_sigma * (
                cos_2sigma_m + correcao * cos_sigma * (-1 + 2 * cos_2sigma_m ** 2)
            )
        )
        if abs(lambda_atual - lambda_anterior) < 1e-12:
            break

    u_quadrado = cos2_alfa * (_A * _A - _B * _B) / (_B * _B)
    fator_a = 1 + u_quadrado / 16384 * (
        4096 + u_quadrado * (-768 + u_quadrado * (320 - 175 * u_quadrado)))
    fator_b = u_quadrado / 1024 * (
        256 + u_quadrado * (-128 + u_quadrado * (74 - 47 * u_quadrado)))
    delta_sigma = fator_b * sin_sigma * (
        cos_2sigma_m + fator_b / 4 * (
            cos_sigma * (-1 + 2 * cos_2sigma_m ** 2)
            - fator_b / 6 * cos_2sigma_m * (-3 + 4 * sin_sigma ** 2)
            * (-3 + 4 * cos_2sigma_m ** 2)
        )
    )
    distancia = _B * fator_a * (sigma - delta_sigma)

    sin_lambda, cos_lambda = math.sin(lambda_atual), math.cos(lambda_atual)
    azimute = math.degrees(math.atan2(
        cos_u2 * sin_lambda,
        cos_u1 * sin_u2 - sin_u1 * cos_u2 * cos_lambda,
    ))
    return distancia, azimute


def destino_geodesico(origem: tuple, azimute: float, distancia: float) -> tuple:
    """Vincenty direto: de onde se chega saindo de um ponto com azimute e distância.

    É a conta do memorial descritivo -- "do vértice P-01, segue com
    azimute 90°00'00" e distância 910,39 m até o vértice P-02". Sobre o
    elipsoide, não no plano: em 1 km a diferença já passa de centímetros.
    """
    lon1, lat1 = float(origem[0]), float(origem[1])
    if distancia == 0:
        return (lon1, lat1)

    alfa1 = math.radians(azimute)
    sin_alfa1, cos_alfa1 = math.sin(alfa1), math.cos(alfa1)

    tan_u1 = (1 - _F) * math.tan(math.radians(lat1))
    cos_u1 = 1 / math.sqrt(1 + tan_u1 * tan_u1)
    sin_u1 = tan_u1 * cos_u1

    sigma1 = math.atan2(tan_u1, cos_alfa1)
    sin_alfa = cos_u1 * sin_alfa1
    cos2_alfa = 1 - sin_alfa * sin_alfa
    u_quadrado = cos2_alfa * (_A * _A - _B * _B) / (_B * _B)
    fator_a = 1 + u_quadrado / 16384 * (
        4096 + u_quadrado * (-768 + u_quadrado * (320 - 175 * u_quadrado)))
    fator_b = u_quadrado / 1024 * (
        256 + u_quadrado * (-128 + u_quadrado * (74 - 47 * u_quadrado)))

    sigma = distancia / (_B * fator_a)
    cos_2sigma_m = delta_sigma = 0.0
    for _ in range(200):
        cos_2sigma_m = math.cos(2 * sigma1 + sigma)
        sin_sigma, cos_sigma = math.sin(sigma), math.cos(sigma)
        delta_sigma = fator_b * sin_sigma * (
            cos_2sigma_m + fator_b / 4 * (
                cos_sigma * (-1 + 2 * cos_2sigma_m ** 2)
                - fator_b / 6 * cos_2sigma_m * (-3 + 4 * sin_sigma ** 2)
                * (-3 + 4 * cos_2sigma_m ** 2)
            )
        )
        anterior = sigma
        sigma = distancia / (_B * fator_a) + delta_sigma
        if abs(sigma - anterior) < 1e-12:
            break

    sin_sigma, cos_sigma = math.sin(sigma), math.cos(sigma)
    temporario = sin_u1 * sin_sigma - cos_u1 * cos_sigma * cos_alfa1
    lat2 = math.atan2(
        sin_u1 * cos_sigma + cos_u1 * sin_sigma * cos_alfa1,
        (1 - _F) * math.sqrt(sin_alfa * sin_alfa + temporario * temporario),
    )
    lambda_ = math.atan2(
        sin_sigma * sin_alfa1,
        cos_u1 * cos_sigma - sin_u1 * sin_sigma * cos_alfa1,
    )
    correcao = _F / 16 * cos2_alfa * (4 + _F * (4 - 3 * cos2_alfa))
    diferenca_lon = lambda_ - (1 - correcao) * _F * sin_alfa * (
        sigma + correcao * sin_sigma * (
            cos_2sigma_m + correcao * cos_sigma * (-1 + 2 * cos_2sigma_m ** 2)
        )
    )
    return (lon1 + math.degrees(diferenca_lon), math.degrees(lat2))


def perimetro_m(anel: list, fechado: bool = True) -> float:
    """Soma das distâncias geodésicas entre vértices consecutivos.

    ``fechado=False`` mede uma linha aberta -- é o caso da ferramenta de
    medir distância, que não volta ao ponto de partida.
    """
    pontos = _anel_limpo(anel)
    if len(pontos) < 2:
        return 0.0
    total = sum(
        distancia_m(pontos[i], pontos[i + 1]) for i in range(len(pontos) - 1))
    if fechado and len(pontos) > 2:
        total += distancia_m(pontos[-1], pontos[0])
    return total


def _anel_limpo(anel: list) -> list:
    """Descarta o vértice de fechamento repetido e valida cada par."""
    pontos = []
    for item in anel or []:
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            continue
        try:
            lon, lat = float(item[0]), float(item[1])
        except (TypeError, ValueError):
            continue
        if not (-180.0 <= lon <= 180.0 and -90.0 <= lat <= 90.0):
            continue
        pontos.append((lon, lat))
    # GeoJSON repete o primeiro ponto no fim; nas contas ele atrapalharia.
    if len(pontos) > 1 and pontos[0] == pontos[-1]:
        pontos.pop()
    return pontos


def validar_anel(anel: list, tipo: str) -> list:
    """Valida o desenho recebido da interface e devolve o anel limpo."""
    pontos = _anel_limpo(anel)
    minimos = {"POLIGONO": 3, "LINHA": 2, "PONTO": 1}
    if tipo not in minimos:
        raise ValueError("Tipo de desenho inválido.")
    if len(pontos) < minimos[tipo]:
        nomes = {"POLIGONO": "três", "LINHA": "dois", "PONTO": "um"}
        raise ValueError(
            f"Um {tipo.lower()} precisa de pelo menos {nomes[tipo]} ponto(s).")
    # Teto defensivo: um memorial de fazenda raramente passa de algumas
    # centenas de vértices, e sem limite um POST malformado viraria uma
    # linha gigante no banco.
    if len(pontos) > 10_000:
        raise ValueError("Desenho com vértices demais (limite de 10.000).")
    return pontos


def medidas(anel: list, tipo: str) -> dict:
    """Área e perímetro prontos para gravar e exibir."""
    pontos = _anel_limpo(anel)
    if tipo == "POLIGONO":
        return {
            "area_m2": area_m2(pontos),
            "perimetro_m": perimetro_m(pontos, fechado=True),
        }
    if tipo == "LINHA":
        return {"area_m2": 0.0, "perimetro_m": perimetro_m(pontos, fechado=False)}
    return {"area_m2": 0.0, "perimetro_m": 0.0}


# ---------------------------------------------------------------------------
# Sobreposição
# ---------------------------------------------------------------------------

def _orientacao(p, q, r) -> int:
    valor = (q[1] - p[1]) * (r[0] - q[0]) - (q[0] - p[0]) * (r[1] - q[1])
    if abs(valor) < 1e-15:
        return 0
    return 1 if valor > 0 else 2


def _no_segmento(p, q, r) -> bool:
    return (
        min(p[0], r[0]) <= q[0] <= max(p[0], r[0])
        and min(p[1], r[1]) <= q[1] <= max(p[1], r[1])
    )


def _segmentos_cruzam(p1, p2, q1, q2) -> bool:
    o1, o2 = _orientacao(p1, p2, q1), _orientacao(p1, p2, q2)
    o3, o4 = _orientacao(q1, q2, p1), _orientacao(q1, q2, p2)
    if o1 != o2 and o3 != o4:
        return True
    # Casos colineares: o toque conta como cruzamento.
    return (
        (o1 == 0 and _no_segmento(p1, q1, p2))
        or (o2 == 0 and _no_segmento(p1, q2, p2))
        or (o3 == 0 and _no_segmento(q1, p1, q2))
        or (o4 == 0 and _no_segmento(q1, p2, q2))
    )


def ponto_dentro(ponto, anel: list) -> bool:
    """Ponto dentro do anel, pela regra do número de cruzamentos."""
    pontos = _anel_limpo(anel)
    if len(pontos) < 3:
        return False
    x, y = float(ponto[0]), float(ponto[1])
    dentro = False
    for i in range(len(pontos)):
        x1, y1 = pontos[i]
        x2, y2 = pontos[(i + 1) % len(pontos)]
        if (y1 > y) != (y2 > y):
            corte = x1 + (y - y1) / (y2 - y1) * (x2 - x1)
            if corte > x:
                dentro = not dentro
    return dentro


def _envelope(pontos: list) -> tuple:
    lons = [p[0] for p in pontos]
    lats = [p[1] for p in pontos]
    return min(lons), min(lats), max(lons), max(lats)


def se_sobrepoem(anel_a: list, anel_b: list) -> bool:
    """Diz se dois polígonos se tocam ou se invadem.

    Responde só sim ou não, de propósito. Calcular a *área* de
    sobreposição exigiria recortar um polígono contra o outro, e um
    recorte com bug devolveria um número errado com cara de exato -- que
    numa qualificação registral é pior do que não ter número nenhum.
    """
    pa, pb = _anel_limpo(anel_a), _anel_limpo(anel_b)
    if len(pa) < 3 or len(pb) < 3:
        return False

    # Descarte barato antes do teste caro: envelopes disjuntos não podem
    # se sobrepor, e é o caso da esmagadora maioria dos pares do acervo.
    a_min_lon, a_min_lat, a_max_lon, a_max_lat = _envelope(pa)
    b_min_lon, b_min_lat, b_max_lon, b_max_lat = _envelope(pb)
    if (a_max_lon < b_min_lon or b_max_lon < a_min_lon
            or a_max_lat < b_min_lat or b_max_lat < a_min_lat):
        return False

    for i in range(len(pa)):
        for j in range(len(pb)):
            if _segmentos_cruzam(
                pa[i], pa[(i + 1) % len(pa)],
                pb[j], pb[(j + 1) % len(pb)],
            ):
                return True
    # Sem cruzar aresta, ainda resta um contido inteiramente no outro.
    return ponto_dentro(pa[0], pb) or ponto_dentro(pb[0], pa)


# ---------------------------------------------------------------------------
# Leitura de coordenadas digitadas ou coladas
# ---------------------------------------------------------------------------

_PADRAO_GMS = re.compile(
    r"(\d{1,3})\s*[°º]\s*(\d{1,2})\s*['′]\s*([\d.,]+)\s*[\"″]?\s*([NSEWLO])",
    re.IGNORECASE,
)
_PADRAO_DECIMAL = re.compile(r"[-+]?\d{1,3}[.,]\d+")
_PADRAO_UTM = re.compile(
    r"\b(\d{1,2})\s*([A-HJ-NP-Z])\b[^\d]{0,12}(\d{6,7}(?:[.,]\d+)?)"
    r"[^\d]{1,12}(\d{6,8}(?:[.,]\d+)?)",
    re.IGNORECASE,
)


def _numero(texto: str) -> float:
    return float(texto.replace(".", "").replace(",", ".")) if texto.count(",") \
        else float(texto.replace(",", "."))


def gms_para_decimal(graus: float, minutos: float, segundos: float, hemisferio: str) -> float:
    decimal = abs(graus) + minutos / 60.0 + segundos / 3600.0
    # "O" de Oeste e "W" de West apontam para o mesmo lado; o acervo usa
    # as duas letras. "L" de Leste idem, para Este.
    if hemisferio.upper() in {"S", "W", "O"}:
        decimal = -decimal
    return decimal


def utm_para_geografica(leste: float, norte: float, fuso: int, hemisferio_sul: bool) -> tuple:
    """Converte UTM (SIRGAS 2000/WGS84, que coincidem no nível do desenho)."""
    k0 = 0.9996
    leste_relativo = leste - 500000.0
    norte_relativo = norte - (10000000.0 if hemisferio_sul else 0.0)

    e_linha2 = _E2 / (1 - _E2)
    m = norte_relativo / k0
    mu = m / (_A * (1 - _E2 / 4 - 3 * _E2 ** 2 / 64 - 5 * _E2 ** 3 / 256))
    e1 = (1 - math.sqrt(1 - _E2)) / (1 + math.sqrt(1 - _E2))

    lat1 = (
        mu
        + (3 * e1 / 2 - 27 * e1 ** 3 / 32) * math.sin(2 * mu)
        + (21 * e1 ** 2 / 16 - 55 * e1 ** 4 / 32) * math.sin(4 * mu)
        + (151 * e1 ** 3 / 96) * math.sin(6 * mu)
        + (1097 * e1 ** 4 / 512) * math.sin(8 * mu)
    )
    sin_lat1, cos_lat1, tan_lat1 = math.sin(lat1), math.cos(lat1), math.tan(lat1)
    n1 = _A / math.sqrt(1 - _E2 * sin_lat1 ** 2)
    t1 = tan_lat1 ** 2
    c1 = e_linha2 * cos_lat1 ** 2
    r1 = _A * (1 - _E2) / (1 - _E2 * sin_lat1 ** 2) ** 1.5
    d = leste_relativo / (n1 * k0)

    latitude = lat1 - (n1 * tan_lat1 / r1) * (
        d ** 2 / 2
        - (5 + 3 * t1 + 10 * c1 - 4 * c1 ** 2 - 9 * e_linha2) * d ** 4 / 24
        + (61 + 90 * t1 + 298 * c1 + 45 * t1 ** 2 - 252 * e_linha2 - 3 * c1 ** 2)
        * d ** 6 / 720
    )
    longitude = (
        d
        - (1 + 2 * t1 + c1) * d ** 3 / 6
        + (5 - 2 * c1 + 28 * t1 - 3 * c1 ** 2 + 8 * e_linha2 + 24 * t1 ** 2)
        * d ** 5 / 120
    ) / cos_lat1

    meridiano_central = math.radians((fuso - 1) * 6 - 180 + 3)
    return math.degrees(longitude + meridiano_central), math.degrees(latitude)


def fuso_de(longitude: float) -> int:
    """Fuso UTM que contém a longitude. Morrinhos cai no 22."""
    return int((longitude + 180) // 6) + 1


def geografica_para_utm(longitude: float, latitude: float, fuso: int | None = None) -> dict:
    """Converte para UTM. É a forma que o memorial descritivo usa."""
    fuso = fuso or fuso_de(longitude)
    k0 = 0.9996
    lat = math.radians(latitude)
    meridiano_central = math.radians((fuso - 1) * 6 - 180 + 3)
    delta_lon = math.radians(longitude) - meridiano_central

    e_linha2 = _E2 / (1 - _E2)
    n = _A / math.sqrt(1 - _E2 * math.sin(lat) ** 2)
    t = math.tan(lat) ** 2
    c = e_linha2 * math.cos(lat) ** 2
    a_termo = math.cos(lat) * delta_lon
    m = _A * (
        (1 - _E2 / 4 - 3 * _E2 ** 2 / 64 - 5 * _E2 ** 3 / 256) * lat
        - (3 * _E2 / 8 + 3 * _E2 ** 2 / 32 + 45 * _E2 ** 3 / 1024) * math.sin(2 * lat)
        + (15 * _E2 ** 2 / 256 + 45 * _E2 ** 3 / 1024) * math.sin(4 * lat)
        - (35 * _E2 ** 3 / 3072) * math.sin(6 * lat)
    )

    leste = k0 * n * (
        a_termo
        + (1 - t + c) * a_termo ** 3 / 6
        + (5 - 18 * t + t ** 2 + 72 * c - 58 * e_linha2) * a_termo ** 5 / 120
    ) + 500000.0
    norte = k0 * (
        m + n * math.tan(lat) * (
            a_termo ** 2 / 2
            + (5 - t + 9 * c + 4 * c ** 2) * a_termo ** 4 / 24
            + (61 - 58 * t + t ** 2 + 600 * c - 330 * e_linha2) * a_termo ** 6 / 720
        )
    )
    if latitude < 0:
        norte += 10000000.0
    return {"fuso": fuso, "leste": leste, "norte": norte, "hemisferio": "S" if latitude < 0 else "N"}


def interpretar_coordenadas(texto: str) -> list:
    """Lê uma lista de coordenadas colada, em qualquer das três formas.

    A ordem de tentativa importa: GMS primeiro porque seu texto contém
    números decimais que o padrão decimal casaria sozinho, e UTM antes do
    decimal porque suas coordenadas métricas não têm o formato de grau.
    """
    if not texto or not texto.strip():
        return []

    achados_gms = _PADRAO_GMS.findall(texto)
    if len(achados_gms) >= 2:
        valores = [
            gms_para_decimal(float(g), float(m), _numero(s), h)
            for g, m, s, h in achados_gms
        ]
        hemisferios = [h.upper() for *_, h in achados_gms]
        return _emparelhar(valores, hemisferios)

    achados_utm = _PADRAO_UTM.findall(texto)
    if achados_utm:
        pontos = []
        for fuso, banda, leste, norte in achados_utm:
            lon, lat = utm_para_geografica(
                _numero(leste), _numero(norte), int(fuso),
                banda.upper() < "N",
            )
            pontos.append([lon, lat])
        return pontos

    numeros = [_numero(v) for v in _PADRAO_DECIMAL.findall(texto)]
    ordem = _ordem_declarada(texto)
    pontos = []
    for i in range(0, len(numeros) - 1, 2):
        primeiro, segundo = numeros[i], numeros[i + 1]
        if ordem == "lon_lat":
            pontos.append([primeiro, segundo])
        elif ordem == "lat_lon":
            pontos.append([segundo, primeiro])
        # Sem ordem declarada, o palpite é "latitude, longitude", como o
        # Google Maps mostra -- é de lá que vem a maior parte do que se
        # cola aqui. O armazenamento é sempre o inverso, do GeoJSON.
        elif abs(primeiro) <= 90 and abs(segundo) <= 180:
            pontos.append([segundo, primeiro])
        elif abs(segundo) <= 90:
            pontos.append([primeiro, segundo])
    return pontos


def _ordem_declarada(texto: str):
    """Lê no texto qual eixo vem primeiro, quando ele diz.

    Existe porque o par é ambíguo em boa parte do Brasil: em Goiás tanto
    a longitude quanto a latitude cabem na faixa de uma latitude, então
    "-49.10, -17.73" pode ser lido dos dois jeitos, e o palpite errado
    joga o imóvel a milhares de quilômetros sem nenhum aviso.

    O módulo copia as coordenadas com a linha ``# longitude, latitude``
    justamente para que colar de volta não dependa de palpite. Planilhas
    e memoriais que rotulam as colunas também passam a ser lidos certo.
    """
    achado_lon = re.search(r"\blong(?:itude)?\b", texto, re.I)
    achado_lat = re.search(r"\blat(?:itude)?\b", texto, re.I)
    if not achado_lon or not achado_lat:
        return None
    return "lon_lat" if achado_lon.start() < achado_lat.start() else "lat_lon"


def _emparelhar(valores: list, hemisferios: list) -> list:
    """Junta os valores GMS em pares (lon, lat) pela letra do hemisfério."""
    pontos = []
    for i in range(0, len(valores) - 1, 2):
        a, b = valores[i], valores[i + 1]
        letra_a = hemisferios[i]
        if letra_a in {"N", "S"}:
            pontos.append([b, a])
        else:
            pontos.append([a, b])
    return pontos


# ---------------------------------------------------------------------------
# Dados de identificação exigidos pelo Mapa do Registro de Imóveis
# ---------------------------------------------------------------------------

# Motivos publicados no item 3.4.5.3 do Manual Técnico Operacional.
MOTIVOS_DE_ENVIO = (
    "Desdobro", "Desmembramento", "Divisão", "Loteamento", "Novo imóvel",
    "Regularização fundiária", "Retificação de matrícula", "Unificação",
)

# Item 5.12.1: o endereço vai sem abreviações. A lista fica curta e só com
# formas inequívocas -- expandir "Al." ou "Pq." exigiria adivinhar, e
# adivinhar em endereço de matrícula é pior do que deixar como está.
#
# Duas sutilezas que custaram um teste vermelho:
#
# 1. A expansão roda DEPOIS de sem_acentos, então os padrões precisam
#    casar a forma já sem acento ("Pc." e não "Pç."), e as substituições
#    precisam ser sem acento também -- escrever "Praça" aqui reintroduziria
#    justamente o acento que a regra do manual acabou de remover.
# 2. Todo padrão exige o ponto final. Sem ele, "Av" solto viraria
#    "Avenida" dentro de um nome próprio.
_ABREVIACOES = (
    (r"\bR\.", "Rua"),
    (r"\bAv\.", "Avenida"),
    (r"\bTrav\.|\bTv\.", "Travessa"),
    (r"\bRod\.", "Rodovia"),
    (r"\bPc\.|\bPca\.|\bPr\.", "Praca"),
    (r"\bEstr\.", "Estrada"),
    (r"\bLot\.", "Loteamento"),
    (r"\bCj\.|\bConj\.", "Conjunto"),
)

UFS = frozenset(
    "AC AL AM AP BA CE DF ES GO MA MG MS MT PA PB PE PI PR RJ RN RO RR "
    "RS SC SE SP TO".split()
)


def sem_acentos(texto: str) -> str:
    """Remove acentos e sinais, como o item 5.12.1 do manual determina.

    O manual é explícito: "acentos e caracteres especiais não devem ser
    usados no cadastro de parcelas". Vale só para o que vai nos atributos
    do imóvel; o nome que aparece na tela do AERI continua acentuado.
    """
    decomposto = unicodedata.normalize("NFD", texto)
    sem_marcas = "".join(c for c in decomposto if unicodedata.category(c) != "Mn")
    # Indicadores ordinais viram nada: "Nº 3" fica "N 3". Eles passariam
    # pelo filtro abaixo, porque o Unicode os classifica como letra.
    sem_marcas = sem_marcas.replace("º", "").replace("ª", "")
    limpo = re.sub(r"[^\w\s.,;:/()\-]", "", sem_marcas, flags=re.UNICODE)
    # Tirar travessão e aspas curvas deixa espaços dobrados no lugar.
    return re.sub(r"\s{2,}", " ", limpo).strip()


def expandir_abreviacoes(endereco: str) -> str:
    """Troca as abreviações de logradouro por extenso (item 5.12.1)."""
    texto = endereco
    for padrao, extenso in _ABREVIACOES:
        texto = re.sub(padrao, extenso, texto, flags=re.IGNORECASE)
    return re.sub(r"\s{2,}", " ", texto).strip()


def _lista_separada_por_virgula(valor: str, limite: int, so_digitos: bool = False) -> str:
    itens = []
    for parte in str(valor or "").split(","):
        parte = parte.strip()
        if so_digitos:
            parte = re.sub(r"\D", "", parte)
        if parte:
            itens.append(parte)
    return ", ".join(itens)[:limite]


def validar_dados_mapa(dados) -> dict:
    """Normaliza os campos de identificação do imóvel para o padrão do Mapa.

    Devolve sempre o dicionário completo, com string vazia onde não há
    informação: assim o KML sai com a estrutura inteira e quem recebe vê
    o que falta preencher, em vez de descobrir depois que o Mapa recusou.
    """
    dados = dados if isinstance(dados, dict) else {}

    def texto(chave, limite):
        return sem_acentos(str(dados.get(chave) or "").strip())[:limite]

    uf = re.sub(r"[^A-Za-z]", "", str(dados.get("uf") or "")).upper()[:2]
    motivo = str(dados.get("motivo") or "").strip()

    return {
        # CNS tem seis dígitos, mas registros antigos aparecem com hífen;
        # guardamos só os dígitos, como o manual exemplifica.
        "cns": re.sub(r"\D", "", str(dados.get("cns") or ""))[:10],
        "municipio": texto("municipio", 120),
        # Item 5.12.1: sempre duas letras, ABNT/NBR ISO 3166-2:BR.
        "uf": uf if uf in UFS else "",
        "proprietarios": _lista_separada_por_virgula(
            sem_acentos(str(dados.get("proprietarios") or "")), 600),
        "documentos": _lista_separada_por_virgula(
            dados.get("documentos"), 400, so_digitos=True),
        "endereco": expandir_abreviacoes(texto("endereco", 240)),
        "numero": texto("numero", 20),
        "cep": re.sub(r"\D", "", str(dados.get("cep") or ""))[:8],
        "motivo": motivo if motivo in MOTIVOS_DE_ENVIO else "",
    }


def centroide(anel: list) -> tuple:
    """Ponto central do imóvel, que a tela de cadastro do Mapa pede.

    É o centroide da área (item 9 e 10 do 3.4.5.1), e não a média dos
    vértices: num polígono com lados muito desiguais a média cai fora do
    imóvel, e o Mapa usa esse ponto para localizar a parcela.
    """
    pontos = _anel_limpo(anel)
    if len(pontos) < 3:
        return (pontos[0] if pontos else (0.0, 0.0))

    # Os produtos cruzados são calculados em torno do primeiro vértice, e
    # não das coordenadas cruas. Sem isso, um lote urbano em Goiás
    # multiplica valores na casa de 870 para extrair uma diferença na casa
    # de 1e-7: o ponto flutuante perde os dígitos que importam e o centro
    # sai deslocado mais de um metro -- num quadrado, onde ele tem de cair
    # exatamente no meio.
    origem_lon, origem_lat = pontos[0]
    locais = [(lon - origem_lon, lat - origem_lat) for lon, lat in pontos]

    area2 = soma_lon = soma_lat = 0.0
    for i in range(len(locais)):
        x1, y1 = locais[i]
        x2, y2 = locais[(i + 1) % len(locais)]
        cruzado = x1 * y2 - x2 * y1
        area2 += cruzado
        soma_lon += (x1 + x2) * cruzado
        soma_lat += (y1 + y2) * cruzado
    if abs(area2) < 1e-15:
        # Polígono degenerado: cai na média, que ao menos fica no desenho.
        return (
            sum(p[0] for p in pontos) / len(pontos),
            sum(p[1] for p in pontos) / len(pontos),
        )
    return (
        origem_lon + soma_lon / (3 * area2),
        origem_lat + soma_lat / (3 * area2),
    )


def poligono_json(item: dict) -> dict:
    """Formato que a interface consome."""
    return {
        "id": str(item["id"]),
        "nome": item["nome"],
        "matricula": item["matricula"],
        "tipo": item["tipo"],
        "anel": item["anel"],
        "areaM2": item["area_m2"],
        "perimetroM": item["perimetro_m"],
        "cor": item["cor"],
        "observacao": item["observacao"],
        "dadosMapa": item.get("dados_mapa") or {},
        "criadoPor": item["criado_por"],
        "criadoEm": item["criado_em"].isoformat(),
        "atualizadoEm": item["atualizado_em"].isoformat(),
    }
