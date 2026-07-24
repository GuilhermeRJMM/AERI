import re


PADRAO_CABECALHO_ATO = re.compile(
    r"(?:^|\n)[ \t\-–—]*"
    r"(?P<tipo>R|AV)\s*(?P<marcador>[.\-]?)\s*(?P<numero>[0-9OIL]+)"
    r"(?P<separador>[ \t]*[.\-–—:][ \t]*|[ \t]*,[ \t]*|[ \t]+(?=\S))",
    flags=re.IGNORECASE,
)


def _cabecalhos_validos(texto: str) -> list[re.Match]:
    encontrados = list(PADRAO_CABECALHO_ATO.finditer(texto))
    validos = []
    ordinais_usados = set()

    for cabecalho in encontrados:
        ordinal = int(_normalizar_numero(cabecalho.group("numero")))
        if ordinal in ordinais_usados:
            # Um número de ordem registral não pode existir simultaneamente
            # como R e AV. Repetições no corpo são referências internas.
            continue
        separador = cabecalho.group("separador").strip()
        if not cabecalho.group("marcador") and separador not in {"-", "–", "—"}:
            # A grafia histórica sem ponto após R/AV só é cabeçalho quando
            # mantém o hífen seguinte: "R12-27" ou "AV11-27".
            continue
        if separador == ",":
            proximo_ordinal = max(ordinais_usados, default=0) + 1
            if ordinal != proximo_ordinal:
                # Vírgulas são aceitas em cabeçalhos históricos, mas não em
                # listas como "R.030, R.050" ou referências fora de sequência.
                continue
        validos.append(cabecalho)
        ordinais_usados.add(ordinal)

    return validos


def _normalizar_numero(valor: str) -> str:
    return valor.upper().translate(str.maketrans({"O": "0", "I": "1", "L": "1"}))


def _normalizar_quebras_tri7(texto: str) -> str:
    # Alguns retornos do Tri7 expõem o marcador interno da ficha imediatamente
    # antes do ato seguinte: "RTIPO...FICHA«a».10-25.956". O "R" inicial é o
    # tipo do ato e precisa ser preservado como início de uma nova linha.
    return re.sub(
        r"R(?:TIPO|IPO)[^\r\n]{0,100}?(?:«|Â«)+a(?:»|Â»)+",
        "\nR",
        texto,
        flags=re.IGNORECASE,
    )


def separar_atos(texto):
    # O Tri7 preserva formatos históricos como "R.01 -", "AV-02-",
    # "R.03 descrição" e, em alguns livros, "R.01, descrição".
    texto = _normalizar_quebras_tri7(texto)
    cabecalhos = _cabecalhos_validos(texto)
    atos = []

    for indice, cabecalho in enumerate(cabecalhos):
        inicio = cabecalho.start("tipo")
        fim = cabecalhos[indice + 1].start("tipo") if indice + 1 < len(cabecalhos) else len(texto)
        bloco = texto[inicio:fim].strip()
        atos.append(
            {
                "codigo": f"{cabecalho.group('tipo').upper()}.{_normalizar_numero(cabecalho.group('numero'))}",
                "texto": bloco,
            }
        )

    return atos
