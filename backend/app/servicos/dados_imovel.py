import re
import unicodedata
from typing import Optional


def _sem_acentos(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii").upper()


def _compactar(texto: str) -> str:
    return re.sub(r"\s+", " ", texto or "").strip(" ,.;:-")


def _normalizar_localizacao(texto: str) -> str:
    valor = _compactar(texto)
    valor = re.sub(r"^(?:d[oa]s?|n[oa]s?|em)\s+", "", valor, flags=re.IGNORECASE)
    valor = re.sub(
        r"^(?:loteamento|bairro)\s+(?:denominad[oa]\s+)?[\"'“”]?"
        r"(?=(?:Vila|Setor|Jardim|Bairro|Residencial|Parque|Centro)\b)",
        "",
        valor,
        flags=re.IGNORECASE,
    )
    return _compactar(valor.strip("\"'“”"))


def _valor_decimal(texto: str) -> Optional[float]:
    valor = re.sub(r"[^\d,.]", "", texto or "").strip(".,")
    if not valor:
        return None
    if "," in valor:
        valor = valor.replace(".", "").replace(",", ".")
    elif valor.count(".") > 1:
        # Nos textos registrais brasileiros, pontos repetidos separam milhares
        # (por exemplo, 1.477.100 m²), e não casas decimais.
        valor = valor.replace(".", "")
    try:
        return float(valor)
    except ValueError:
        return None


def _formatar_numero(valor: float, casas: int = 4) -> str:
    texto = f"{valor:.{casas}f}".rstrip("0").rstrip(".")
    inteiro, separador, decimal = texto.partition(".")
    inteiro = f"{int(inteiro):,}".replace(",", ".")
    return f"{inteiro},{decimal}" if separador else inteiro


def _adicionar_unico(lista: list[dict], item: dict) -> None:
    chave = (item.get("rotulo"), item.get("valor"), item.get("origem"))
    if chave not in {(x.get("rotulo"), x.get("valor"), x.get("origem")) for x in lista}:
        lista.append(item)


def _substituir_por_rotulo(lista: list[dict], item: dict) -> None:
    lista[:] = [existente for existente in lista if existente.get("rotulo") != item.get("rotulo")]
    lista.append(item)


def _descricao_ato(ato) -> str:
    return ato.descricao if hasattr(ato, "descricao") else str(ato.get("descricao", ""))


def _codigo_ato(ato) -> str:
    return ato.codigo if hasattr(ato, "codigo") else str(ato.get("codigo", "ATO"))


def _tem_encerramento_explicito(normalizado: str) -> bool:
    return (
        "FICA ENCERRADA" in normalizado
        or "FICA ENCERRADO" in normalizado
        or bool(re.search(r"\bENCERRAD[AO]\s+A\s+PRESENTE\s+MATRICULA\b", normalizado))
        or bool(re.search(r"\bENCERRA-SE\s+(?:A\s+)?(?:PRESENTE\s+)?MATRICULA\b", normalizado))
        or bool(re.search(r"\bENCERRAMENTO\s+DA\s+(?:PRESENTE\s+)?MATRICULA\b", normalizado))
    )


def _extrair_area_registral(cabecalho: str, rural: bool) -> Optional[str]:
    # Muitos registros históricos foram digitados sem acento em "área".
    # Unificar a grafia permite manter os padrões numéricos mais restritivos.
    cabecalho = re.sub(r"\b[aàáâã]rea\b", "área", cabecalho, flags=re.IGNORECASE)
    cabecalho = re.sub(r"\bhá\b", "ha", cabecalho, flags=re.IGNORECASE)
    if rural:
        historica_decimal = re.search(
            r"(?:área(?:\s+total)?(?:\s+de)?|com\s+(?:a\s+)?área(?:\s+total)?(?:\s+de)?)\s*(\d+)\s*,\s*(\d{1,2})\s*,\s*(\d{1,4})\s*(?:ha|hectares?)",
            cabecalho,
            re.IGNORECASE,
        )
        if historica_decimal:
            parte_decimal = historica_decimal.group(2) + historica_decimal.group(3)
            hectares = int(historica_decimal.group(1)) + int(parte_decimal) / (10 ** len(parte_decimal))
            return f"{_formatar_numero(hectares)} ha"

        composta = re.search(
            r"(?:área(?:\s+total)?(?:\s+de)?|com\s+(?:a\s+)?área(?:\s+total)?(?:\s+de)?)\s*(\d+)(?:\s*\([^)]*\))?\s*hectares?,\s*"
            r"(\d+)(?:\s*\([^)]*\))?\s*ares?\s+e\s*(\d+)(?:\s*\([^)]*\))?\s*centiares?",
            cabecalho,
            re.IGNORECASE,
        )
        if not composta:
            composta = re.search(
                r"(?:área(?:\s+total)?(?:\s+de)?|com\s+(?:a\s+)?área(?:\s+total)?(?:\s+de)?)\s*(\d+)\s*hectares?,\s*(\d+)\s*ares?\s+e\s*(\d+)\s*centiares?",
                cabecalho,
                re.IGNORECASE,
            )
        if composta:
            hectares = int(composta.group(1)) + int(composta.group(2)) / 100 + int(composta.group(3)) / 10000
            return f"{_formatar_numero(hectares)} ha"

        hectares_ares = re.search(
            r"(?:área(?:\s+total)?(?:\s+de)?|com\s+(?:a\s+)?área(?:\s+total)?(?:\s+de)?)"
            r"\s*(\d+)(?:\s*\([^)]*\))?\s*hectares?\s+e\s+"
            r"(\d+)(?:\s*\([^)]*\))?\s*ares?",
            cabecalho,
            re.IGNORECASE,
        )
        if hectares_ares:
            hectares = int(hectares_ares.group(1)) + int(hectares_ares.group(2)) / 100
            return f"{_formatar_numero(hectares)} ha"

        simples = re.search(r"(?:área(?:\s+total)?(?:\s+de)?|com\s+(?:a\s+)?área(?:\s+total)?(?:\s+de)?)\s*([\d.,]+)\s*(?:ha|hectares?)", cabecalho, re.IGNORECASE)
        if simples:
            valor = _valor_decimal(simples.group(1))
            return f"{_formatar_numero(valor)} ha" if valor is not None else None
        # Há imóveis rurais antigos cuja área registral foi expressa em m².
        rural_metros = re.search(
            r"(?:área(?:\s+total)?(?:\s+de)?|com\s+(?:a\s+)?área(?:\s+total)?(?:\s+de)?)\s*([\d.,]+)\s*m[²2]",
            cabecalho,
            re.IGNORECASE,
        )
        if rural_metros:
            valor = _valor_decimal(rural_metros.group(1))
            return f"{_formatar_numero(valor, 2)} m²" if valor is not None else None
        return None

    urbana_historica = re.search(
        r"(?:área(?:\s+total)?(?:\s+de)?|com\s+(?:a\s+)?área(?:\s+total)?(?:\s+de)?)"
        r"\s*(\d+)\s*,\s*(\d{1,3})\s*,\s*(\d{1,2})\s*m[²2]",
        cabecalho,
        re.IGNORECASE,
    )
    if urbana_historica:
        grupo_intermediario = urbana_historica.group(2)
        if len(grupo_intermediario) == 3:
            metros = int(urbana_historica.group(1) + grupo_intermediario) + int(urbana_historica.group(3)) / 100
        else:
            metros = (
                int(urbana_historica.group(1))
                + int(grupo_intermediario) / 100
                + int(urbana_historica.group(3)) / 10000
            )
        return f"{_formatar_numero(metros, 2)} m²"

    urbana = re.search(r"(?:área(?:\s+total)?(?:\s+de)?|com\s+(?:a\s+)?área(?:\s+total)?(?:\s+de)?)\s*([\d.,]+)\s*m[²2]", cabecalho, re.IGNORECASE)
    if urbana:
        valor = _valor_decimal(urbana.group(1))
        return f"{_formatar_numero(valor, 2)} m²" if valor is not None else None
    return None


def _extrair_bloco_imovel(texto: str) -> tuple[str, str]:
    partes = re.split(r"(?:^|\n)[ \t-]*(?:R|AV)[.\-]\s*\d+[.\-]", texto, maxsplit=1, flags=re.IGNORECASE)
    cabecalho = partes[0]
    bloco = re.search(
        r"IM[ÓO]VEL\s*:\s*(.*?)(?=\b(?:P?R[OÓ]PRIET)[ÁA]RI[OA]S?\s*[:;]|\bORIGEM\s*:|\bT[ÍI]TULO\s+AQUISITIVO\s*:|\Z)",
        cabecalho,
        re.IGNORECASE | re.DOTALL,
    )
    if bloco:
        return cabecalho, _compactar(bloco.group(1))

    # Matrículas antigas frequentemente iniciam diretamente pela descrição,
    # sem o rótulo "IMÓVEL:". Limita-se o fallback ao trecho anterior ao
    # proprietário/origem para não confundir dados pessoais com o bem.
    descricao_legada = re.split(
        r"\b(?:P?R[OÓ]PRIET)[ÁA]RI[OA]S?\s*[:;]|\bORIGEM\s*:|\bT[ÍI]TULO\s+AQUISITIVO\s*:",
        cabecalho,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    return cabecalho, _compactar(descricao_legada)


def _extrair_lotes(segmento: str) -> Optional[str]:
    padrao = re.compile(
        r"\blotes?(?:\s+de\s+terras)?\s*"
        r"(?:n(?:[.º°o]|os|s)*\s*)?"
        r"(?P<lotes>\d+[A-Za-z]?(?:[-/]\w+)?(?:\s*(?:,|e)\s*\d+[A-Za-z]?(?:[-/]\w+)?)*)"
        r"(?:\s+da\s+quadra\s+(?:n(?:[.º°o]|os|s)*\s*)?(?P<quadra>[\w\-/]+))?",
        re.IGNORECASE,
    )
    confrontantes = []
    for lote in padrao.finditer(segmento):
        identificadores = [
            item.strip()
            for item in re.split(r"\s*(?:,|\be\b)\s*", lote.group("lotes"), flags=re.IGNORECASE)
            if item.strip()
        ]
        quadra = lote.group("quadra")
        confrontantes.extend((identificador, quadra) for identificador in identificadores)

    if not confrontantes:
        return None

    unicos = []
    for confrontante in confrontantes:
        if confrontante not in unicos:
            unicos.append(confrontante)

    quadras = {quadra for _, quadra in unicos}
    if len(quadras) == 1:
        quadra = next(iter(quadras))
        lotes = [identificador for identificador, _ in unicos]
        lista = lotes[0] if len(lotes) == 1 else f"{', '.join(lotes[:-1])} e {lotes[-1]}"
        prefixo = "Lote" if len(lotes) == 1 else "Lotes"
        complemento = f" da Quadra {quadra}" if quadra else ""
        return f"{prefixo} {lista}{complemento}"

    partes = []
    for identificador, quadra in unicos:
        partes.append(f"Lote {identificador}" + (f" da Quadra {quadra}" if quadra else ""))
    return "; ".join(partes)


def _extrair_confrontacoes(descricao: str, origem: str = "Cabeçalho", rua: Optional[str] = None) -> list[dict]:
    marcadores = []
    padroes = (
        ("Frente", r"\b(?:pela\s+|de\s+|na\s+)?frente\b"),
        ("Lado Direito", r"\b(?:lado\s+direito|direita)\b"),
        ("Lado Esquerdo", r"\b(?:lado\s+esquerdo|esquerda)\b"),
        ("Fundos", r"\b(?:fundos|fundo)\b"),
    )
    for rotulo, padrao in padroes:
        for ocorrencia in re.finditer(padrao, descricao, re.IGNORECASE):
            marcadores.append((ocorrencia.start(), ocorrencia.end(), rotulo))

    marcadores.sort(key=lambda item: item[0])
    confrontacoes = {}
    for indice, (_, fim, rotulo) in enumerate(marcadores):
        limite = marcadores[indice + 1][0] if indice + 1 < len(marcadores) else len(descricao)
        segmento = descricao[fim:limite]
        alvo = _extrair_lotes(segmento)
        if not alvo and rotulo == "Frente" and rua and "RUA" in _sem_acentos(segmento):
            alvo = rua
        if not alvo:
            curso_agua = re.search(r"\b(Córrego\s+[^;,.]+)", segmento, re.IGNORECASE)
            if curso_agua:
                alvo = _compactar(curso_agua.group(1))
        if alvo and rotulo not in confrontacoes:
            confrontacoes[rotulo] = alvo

    return [
        {"rotulo": rotulo, "valor": confrontacoes[rotulo], "origem": origem}
        for rotulo, _ in padroes
        if rotulo in confrontacoes
    ]


def _extrair_endereco(descricao: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
    tipo_logradouro = r"(?:Rua|Avenida|Av[.]?|Alameda|Travessa|Praça|Rodovia|Estrada|Viela)"
    logradouro = re.search(
        rf"\bsituad[oa]\s+(?:na|no)\s+({tipo_logradouro}\b[^,;]+)",
        descricao,
        re.IGNORECASE,
    )
    if not logradouro:
        logradouro = re.match(rf"\s*({tipo_logradouro}\b[^,;]+)", descricao, re.IGNORECASE)

    rua = _compactar(logradouro.group(1)) if logradouro else None
    numero = None
    setor = None
    if logradouro:
        trecho_seguinte = descricao[logradouro.end():]
        localizacao = re.match(
            r"\s*,\s*(.*?)"
            r"(?=,\s*(?:nesta|neste|com\b|lote\b|quadra\b|medindo\b|possuindo\b|constituíd[oa]\b)|[.;]|$)",
            trecho_seguinte,
            re.IGNORECASE,
        )
        if localizacao:
            partes = [_compactar(parte) for parte in localizacao.group(1).split(",")]
            partes = [parte for parte in partes if parte]
            if partes:
                numero_encontrado = re.fullmatch(
                    r"(?:n(?:[.º°o]|os|s)*\s*)?(\d[\d.]*)",
                    partes[0],
                    re.IGNORECASE,
                )
                if numero_encontrado:
                    numero = numero_encontrado.group(1)
                    partes = partes[1:]
            candidato = _normalizar_localizacao(", ".join(partes))
            if re.search(r"\b(?:Vila|Setor|Jardim|Bairro|Residencial|Parque|Centro)\b", candidato, re.IGNORECASE):
                setor = candidato

        if not numero:
            numero_encontrado = re.match(
                r"\s*,\s*(?:n(?:[.º°o]|os|s)*\s*)?(\d[\d.]*)\b",
                trecho_seguinte,
                re.IGNORECASE,
            )
            if numero_encontrado:
                numero = numero_encontrado.group(1)

    if not setor:
        localizacao = re.search(
            r"\b((?:Vila\s+[^,;]+,\s*)?Setor\s+[^,;.]+)",
            descricao,
            re.IGNORECASE,
        )
        if localizacao:
            setor = _normalizar_localizacao(localizacao.group(1))

    return rua, numero, setor


def _extrair_area_construida(texto: str, normalizado: str) -> Optional[str]:
    totalizada = re.findall(
        r"totalizando\s+uma\s+área\s+de\s*([\d.,]+)\s*(?:m[²2]|metros?\s+quadrados?)",
        texto,
        re.IGNORECASE,
    )
    if totalizada:
        valor = _valor_decimal(totalizada[-1])
        return f"{_formatar_numero(valor, 2)} m²" if valor is not None else None

    if "RECONSTRUCAO" in normalizado:
        totais = re.findall(r"área\s+total\s+de\s*([\d.,]+)\s*m[²2]", texto, re.IGNORECASE)
        if totais:
            valor = _valor_decimal(totais[-1])
            return f"{_formatar_numero(valor, 2)} m²" if valor is not None else None

    padrao_area_construida = re.compile(
        r"(?:"
        r"área(?:\s+total)?\s+constru[íi]da(?:\s+total)?\s*[,;:]?\s*"
        r"(?:(?:é|e|de)\s*)?(?:de\s*)?:?\s*"
        r"(?P<depois>[\d.,]+)\s*(?:m[²2]|²|metros?\s+quadrados?)"
        r"|"
        # Limite explícito evita backtracking explosivo em matrículas extensas
        # que contêm sequências de máscara antes da unidade de medida.
        r"(?P<antes>[\d.,]+)[,.Xx\s]{0,40}(?:m[²2]|²|metros?\s+quadrados?)"
        r"(?:\s*\([^)]*\))?"
        r"\s*[,;:]?\s*(?:de|da)\s+área(?:\s+total)?\s+constru[íi]da"
        r")",
        re.IGNORECASE,
    )
    construidas = [
        correspondencia.group("depois") or correspondencia.group("antes")
        for correspondencia in padrao_area_construida.finditer(texto)
    ]
    if construidas:
        valor = _valor_decimal(construidas[-1])
        return f"{_formatar_numero(valor, 2)} m²" if valor is not None else None

    sem_unidade = re.findall(
        r"área(?:\s+total)?\s+constru[íi]da\s*[,;:]?\s*"
        r"(?:(?:é|e|de)\s*)?(?:de\s*)?:?\s*([\d.,]+)"
        r"(?=\s*[;.]|\s+(?:O\s+REFERIDO|DOU\s+FÉ))",
        texto,
        re.IGNORECASE,
    )
    if sem_unidade:
        valor = _valor_decimal(sem_unidade[-1])
        return f"{_formatar_numero(valor, 2)} m²" if valor is not None else None
    return None


def _percentual_numerico(texto: str) -> float:
    return float(str(texto).replace("%", "").replace(".", "").replace(",", "."))


def _sucessoras_desmembramento_integral(texto: str, normalizado: str) -> list[str]:
    quantidades = {
        "DUAS": 2,
        "TRES": 3,
        "QUATRO": 4,
        "CINCO": 5,
        "SEIS": 6,
        "SETE": 7,
        "OITO": 8,
        "NOVE": 9,
        "DEZ": 10,
    }
    divisao = re.search(
        r"DESMEMBRAMENTO\s+DO\s+IMOVEL\s+MATRICULADO\s+EM\s+"
        r"(DUAS|TRES|QUATRO|CINCO|SEIS|SETE|OITO|NOVE|DEZ|\d+)\s+GLEBAS\b",
        normalizado,
    )
    if not divisao or "REMANESC" in normalizado:
        return []

    quantidade_texto = divisao.group(1)
    quantidade = int(quantidade_texto) if quantidade_texto.isdigit() else quantidades[quantidade_texto]
    encontradas = re.findall(
        r"matriculad[oa]s?\s+sob\s+o\s+n?[.º°o\s]*([\d.]+)",
        texto,
        re.IGNORECASE,
    )
    for lista in re.findall(
        r"matriculad[oa]s\s+sob\s+(?:os?\s+)?n(?:[.º°o]|os|s)*\s*"
        r"(.*?)(?=\bFLS?\b|\bDO\s+L[ºO]\b|\bDESTE\s+REGISTRO\b|\.\s+O\s+REFERIDO|$)",
        texto,
        re.IGNORECASE | re.DOTALL,
    ):
        encontradas.extend(re.findall(r"\d+(?:\.\d+)+|\d{3,}", lista))
    sucessoras = []
    for numero in encontradas:
        numero = numero.rstrip(".")
        if numero and numero not in sucessoras:
            sucessoras.append(numero)
    return sucessoras if len(sucessoras) >= quantidade else []


def extrair_dados_imovel(
    texto: str,
    atos: list,
    proprietarios: list[dict],
    numero_matricula: Optional[str] = None,
) -> dict:
    cabecalho, descricao = _extrair_bloco_imovel(texto)
    descricao_normalizada = _sem_acentos(descricao)
    rural = (
        any(termo in descricao_normalizada for termo in ("FAZENDA", "SITIO", "INCRA", "IBRA", "HECTARE", "ALQUEIRE", "GLEBA", "ZONA RURAL"))
        or bool(re.search(r"\bHA\b", descricao_normalizada))
    )

    resultado = {
        "situacao": {"status": "ATIVA", "origem": "Matrícula"},
        "tipo": "RURAL" if rural else "URBANO",
        "identificacao": [],
        "confrontacoes": [],
        "areas": [],
        "cadastros": [],
        "restricoes": [],
        "divergencias": [],
        "alertas": [],
    }

    texto_normalizado = _sem_acentos(texto)
    matricula_inexistente = (
        "SALTO NA NUMERACAO SEQUENCIAL DE MATRICULAS" in texto_normalizado
        and bool(re.search(r"NAO\s+EXISTE(?:M)?\s+CARACTERISTICAS\s+DE\s+IMOV(?:EL|EIS)", texto_normalizado))
    )
    if matricula_inexistente:
        resultado["situacao"] = {
            "status": "INEXISTENTE",
            "origem": "Certidão de salto de numeração",
        }

    antes_imovel = re.split(r"IM[ÓO]VEL\s*:", cabecalho, maxsplit=1, flags=re.IGNORECASE)[0]
    matricula = re.search(
        r"MATR[ÍI]CULA(?:\s+n[.º°o]*)?\s*[-:]?\s*([\d.]+)",
        antes_imovel,
        re.IGNORECASE,
    )
    if not matricula:
        matricula = re.search(r"(?:^|\n)[ \t-]*(?:R|AV)[.\-]\s*\d+[.\-]\s*([\d.]+)", texto, re.IGNORECASE)
    if numero_matricula:
        numero_formatado = f"{int(numero_matricula):,}".replace(",", ".")
        _adicionar_unico(resultado["identificacao"], {
            "rotulo": "Matrícula",
            "valor": numero_formatado,
            "origem": "Consulta Tri7",
        })
    elif matricula:
        _adicionar_unico(resultado["identificacao"], {"rotulo": "Matrícula", "valor": matricula.group(1), "origem": "Cabeçalho"})

    lote = re.search(r"\bLote(?:\s+de\s+terras)?\s+n?[.º°o\s]*([\w\-/]+)", descricao, re.IGNORECASE)
    quadra = re.search(r"\bQuadra\s+n?[.º°o\s]*([\w\-/]+)", descricao, re.IGNORECASE)
    if lote:
        _adicionar_unico(resultado["identificacao"], {"rotulo": "Lote", "valor": lote.group(1), "origem": "Cabeçalho"})
    if quadra:
        _adicionar_unico(resultado["identificacao"], {"rotulo": "Quadra", "valor": quadra.group(1), "origem": "Cabeçalho"})

    rua, numero, setor = _extrair_endereco(descricao)
    if rua:
        _adicionar_unico(resultado["identificacao"], {"rotulo": "Rua", "valor": rua, "origem": "Cabeçalho"})
    if numero:
        _adicionar_unico(resultado["identificacao"], {"rotulo": "Número", "valor": numero, "origem": "Cabeçalho"})
    if setor:
        _adicionar_unico(resultado["identificacao"], {"rotulo": "Setor", "valor": setor, "origem": "Cabeçalho"})

    resultado["confrontacoes"] = _extrair_confrontacoes(descricao, rua=rua)

    if rural:
        denominacao = re.search(r"\b((?:Fazendas?|Sítio)\s+.*?)(?=,\s*(?:neste|situad[oa]|constituíd[oa]))", descricao, re.IGNORECASE)
        if denominacao:
            _adicionar_unico(resultado["identificacao"], {
                "rotulo": "Denominação",
                "valor": _compactar(denominacao.group(1)),
                "origem": "Cabeçalho",
            })

    area_registral = _extrair_area_registral(cabecalho, rural)
    if area_registral:
        _adicionar_unico(resultado["areas"], {"rotulo": "Área", "valor": area_registral, "origem": "Cabeçalho"})

    cadastro_municipal = re.search(
        r"Cadastrad[oa]\s+na\s+Prefeitura(?:\s+Municipal)?\s+sob\s+o\s+n?[.º°o\s]*(.*?)"
        r"(?=\bORIGEM\s*:|\b(?:P?R[OÓ]PRIET)[ÁA]RI[OA]S?\s*[:;]|\Z)",
        cabecalho,
        re.IGNORECASE | re.DOTALL,
    )
    if cadastro_municipal:
        _adicionar_unico(resultado["cadastros"], {
            "rotulo": "Cadastro municipal",
            "valor": _compactar(cadastro_municipal.group(1)),
            "origem": "Cabeçalho",
        })

    incra = re.search(r"INCRA[^\n;]*?sob\s+o\s+n?[.º°o\s]*([\d.\-/]+)", cabecalho, re.IGNORECASE)
    if incra:
        _adicionar_unico(resultado["cadastros"], {"rotulo": "INCRA", "valor": incra.group(1), "origem": "Cabeçalho"})

    for ato in atos:
        descricao_ato = _descricao_ato(ato)
        codigo = _codigo_ato(ato)
        normalizado = _sem_acentos(descricao_ato)

        if "CARACTERIZACAO DO IMOVEL" in normalizado:
            bloco_atual = re.search(
                r"assim\s+se\s+caracteriza\s*:\s*(.*)",
                descricao_ato,
                re.IGNORECASE | re.DOTALL,
            )
            caracterizacao = bloco_atual.group(1) if bloco_atual else descricao_ato

            lote_atual = re.search(r"\bLote(?:\s+de\s+terras)?\s+n?[.º°o\s]*([\w\-/]+)", caracterizacao, re.IGNORECASE)
            quadra_atual = re.search(r"\bQuadra\s+n?[.º°o\s]*([\w\-/]+)", caracterizacao, re.IGNORECASE)
            if lote_atual:
                _substituir_por_rotulo(resultado["identificacao"], {"rotulo": "Lote", "valor": lote_atual.group(1), "origem": codigo})
            if quadra_atual:
                _substituir_por_rotulo(resultado["identificacao"], {"rotulo": "Quadra", "valor": quadra_atual.group(1), "origem": codigo})

            rua_atual, numero_atual, setor_atual = _extrair_endereco(caracterizacao)
            if rua_atual:
                _substituir_por_rotulo(resultado["identificacao"], {"rotulo": "Rua", "valor": rua_atual, "origem": codigo})
            if numero_atual:
                _substituir_por_rotulo(resultado["identificacao"], {"rotulo": "Número", "valor": numero_atual, "origem": codigo})
            if setor_atual:
                _substituir_por_rotulo(resultado["identificacao"], {"rotulo": "Setor", "valor": setor_atual, "origem": codigo})

            confrontacoes_atuais = _extrair_confrontacoes(caracterizacao, codigo, rua_atual or rua)
            if confrontacoes_atuais:
                resultado["confrontacoes"] = confrontacoes_atuais

            area_atual = _extrair_area_registral(caracterizacao, False)
            if area_atual:
                _substituir_por_rotulo(resultado["areas"], {"rotulo": "Área", "valor": area_atual, "origem": codigo})
            construida_atual = _extrair_area_construida(caracterizacao, normalizado)
            if construida_atual:
                _substituir_por_rotulo(resultado["areas"], {"rotulo": "Área Construída", "valor": construida_atual, "origem": codigo})

        if "DESIGNACAO CADASTRAL DO IMOVEL" in normalizado:
            designacao = re.search(
                r"códigos?\s+cadastra(?:l|is)\b.*?:\s*(.*?)(?=\.\s*\*NOTA|\.\s*DOU\s+FÉ|\bDOU\s+FÉ|$)",
                descricao_ato,
                re.IGNORECASE | re.DOTALL,
            )
            if not designacao:
                designacao = re.search(
                    r"\bCCI\b\s*(.*?)(?=\.\s*\*NOTA|\.\s*DOU\s+FÉ|\bDOU\s+FÉ|$)",
                    descricao_ato,
                    re.IGNORECASE | re.DOTALL,
                )
            if designacao:
                mascarados = re.findall(
                    r"(?<![\dA-Za-z])(?=[\dXx.\-]*[Xx])"
                    r"[\dXx]+(?:\.[\dXx]+)+(?![\dA-Za-z])",
                    designacao.group(1),
                )
                mascarados = [
                    (prefixo.group(1) if (prefixo := re.match(r"(\d{1,3}\.\d{3})(?=[Xx])", valor)) else valor)
                    for valor in mascarados
                ]
                codigos = mascarados or [
                    re.sub(r"\s+", "", valor).rstrip(".")
                    for valor in re.findall(
                        r"(?<!\d)(?:\d{1,3}(?:\.\s*\d{3})+|\d+)(?![\dA-Za-z])",
                        designacao.group(1),
                    )
                ]
                codigos = [valor for valor in codigos if valor]
                if codigos:
                    lista_codigos = codigos[0] if len(codigos) == 1 else f"{', '.join(codigos[:-1])} e {codigos[-1]}"
                    _substituir_por_rotulo(resultado["cadastros"], {
                        "rotulo": "Cadastro municipal",
                        "valor": f"CCI {lista_codigos}",
                        "origem": codigo,
                    })

        # Formatos históricos também registram o cadastro como "CCI-127902"
        # ou inserem uma máscara antes do número efetivo retornado pela Tri7.
        if (
            "CCI" in normalizado
            and "CADASTR" in normalizado
            and "DESIGNACAO CADASTRAL DO IMOVEL" not in normalizado
        ):
            cci_generico = re.search(
                r"\bCCI\b[^\d]{0,40}(?:[Xx.\-]+\s*)?"
                r"(\d{1,3}(?:\.\d{3})+|\d+)",
                descricao_ato,
                re.IGNORECASE,
            )
            if cci_generico:
                _substituir_por_rotulo(resultado["cadastros"], {
                    "rotulo": "Cadastro municipal",
                    "valor": f"CCI {cci_generico.group(1)}",
                    "origem": codigo,
                })

        encerramento_explicito = _tem_encerramento_explicito(normalizado)
        sucessoras_desmembramento = _sucessoras_desmembramento_integral(descricao_ato, normalizado)
        if encerramento_explicito:
            sucessora = re.search(r"matriculad[oa]\s+sob\s+o\s+n?[.º°o\s]*([\d.]+)", descricao_ato, re.IGNORECASE)
            resultado["situacao"] = {"status": "ENCERRADA", "origem": codigo}
            if sucessora:
                resultado["situacao"]["matricula_sucessora"] = sucessora.group(1).rstrip(".")
            resultado["alertas"].append({
                "tipo": "MATRÍCULA ENCERRADA",
                "mensagem": "Consulte a matrícula sucessora antes de concluir a situação atual do imóvel.",
                "origem": codigo,
            })
        elif sucessoras_desmembramento:
            resultado["situacao"] = {
                "status": "ENCERRADA",
                "origem": codigo,
                "matriculas_sucessoras": sucessoras_desmembramento,
            }
            resultado["alertas"].append({
                "tipo": "MATRÍCULA ENCERRADA",
                "mensagem": "O imóvel foi integralmente desmembrado. Consulte todas as matrículas sucessoras.",
                "origem": codigo,
            })

        if "DEMOLI" in normalizado:
            resultado["areas"][:] = [
                item for item in resultado["areas"] if item.get("rotulo") != "Área Construída"
            ]
        elif "EDIFICACAO" in normalizado or "CONSTRUCAO" in normalizado or "AREA CONSTRUIDA" in normalizado:
            construida = _extrair_area_construida(descricao_ato, normalizado)
            if construida:
                _substituir_por_rotulo(resultado["areas"], {
                    "rotulo": "Área Construída",
                    "valor": construida,
                    "origem": codigo,
                })

        if "CCIR" in normalizado or "CERTIFICADO DE CADASTRO DE IMOVEL RURAL" in normalizado:
            codigo_rural = re.search(
                r"(?:código\s+do\s+imóvel\s+rural|código\s+de\s+cadastrad[oa])"
                r"\s*(?:n?[.º°o\s]*)?:?[^\d]{0,100}([\d][\d.\-/]+)",
                descricao_ato,
                re.IGNORECASE,
            )
            if not codigo_rural:
                codigo_rural = re.search(
                    r"n?[.º°o\s]*do\s+CCIR\s*:?\s*([\d.\-/]+)",
                    descricao_ato,
                    re.IGNORECASE,
                )
            if codigo_rural:
                _adicionar_unico(resultado["cadastros"], {"rotulo": "CCIR / código rural", "valor": codigo_rural.group(1), "origem": codigo})
            area_ccir = re.search(r"área\s+total\s*(?::|de)\s*([\d.,]+)\s*ha", descricao_ato, re.IGNORECASE)
            if area_ccir:
                valor = _valor_decimal(area_ccir.group(1))
                if valor is not None:
                    _adicionar_unico(resultado["areas"], {"rotulo": "Área no CCIR", "valor": f"{_formatar_numero(valor)} ha", "origem": codigo})

        if "INSCRICAO NO CAR" in normalizado or "CADASTRO AMBIENTAL RURAL" in normalizado:
            car_padronizado = re.search(
                # Alguns textos históricos trocaram a letra O por zero na UF
                # (por exemplo, G0 em vez de GO). O restante do identificador
                # continua permitindo validar que se trata de um CAR completo.
                r"\b([A-Z0-9]{2})\s*-\s*(\d{7})\s*-\s*"
                r"([A-F0-9]{28,40}|[A-F0-9]{4}(?:[.\s]+[A-F0-9]{4}){6,9})\b",
                descricao_ato,
                re.IGNORECASE,
            )
            valor_car = None
            if car_padronizado:
                sufixo = re.sub(r"\s+", "", car_padronizado.group(3))
                uf = car_padronizado.group(1).upper().replace("0", "O")
                valor_car = f"{uf}-{car_padronizado.group(2)}-{sufixo}".upper()
            else:
                car = re.search(
                    r"registro\s*:?\s*([A-Z]{2})-\s*([A-Z0-9][A-Z0-9.\-]+)",
                    descricao_ato,
                    re.IGNORECASE,
                )
                if not car:
                    car = re.search(
                    r"\b([A-Z]{2})\s*-\s*(\d{7}-[A-Z0-9][A-Z0-9.\-\s]{15,}?)"
                    r"(?=,\s*(?:CADASTR|APRESENT)|\.\s*DOU\s+FÉ|$)",
                    descricao_ato,
                    re.IGNORECASE | re.DOTALL,
                )
                if car:
                    valor_car = f"{car.group(1)}-{re.sub(r'\s+', '', car.group(2)).rstrip('.')}".upper()
            if valor_car:
                _adicionar_unico(resultado["cadastros"], {
                    "rotulo": "CAR",
                    "valor": valor_car,
                    "origem": codigo,
                })
            area_car = re.search(r"área\s+total\s*\(ha\)\s*:\s*([\d.,]+)", descricao_ato, re.IGNORECASE)
            if area_car:
                valor = _valor_decimal(area_car.group(1))
                if valor is not None:
                    _adicionar_unico(resultado["areas"], {"rotulo": "Área declarada no CAR", "valor": f"{_formatar_numero(valor)} ha", "origem": codigo})
            coordenadas = re.search(
                r"Latitude\s*:\s*([^;]+);\s*e\s*Longitude\s*:\s*([^;]+)",
                descricao_ato,
                re.IGNORECASE,
            )
            if coordenadas:
                _adicionar_unico(resultado["cadastros"], {
                    "rotulo": "Coordenadas do CAR",
                    "valor": f"{_compactar(coordenadas.group(1))}; {_compactar(coordenadas.group(2))}",
                    "origem": codigo,
                })

        cep_do_imovel = (
            "ENDERECAMENTO POSTAL" in normalizado
            or "CEP DO IMOVEL" in normalizado
            or bool(re.search(r"\bIMOVEL\b.{0,100}\bPOSSUI\b.{0,100}\bCEP\b", normalizado, re.DOTALL))
        )
        if cep_do_imovel:
            ceps = re.findall(
                r"(?<!\d)(\d{2}\.?\d{3}[-.]?\d{3})(?!\d)",
                descricao_ato,
            )
            if not ceps:
                for trecho in reversed(re.findall(r"\bCEP\b(.{0,100})", descricao_ato, re.IGNORECASE | re.DOTALL)):
                    antes_fe = re.split(r"\bDOU\s+FÉ\b", trecho, maxsplit=1, flags=re.IGNORECASE)[0]
                    digitos_mascarados = re.sub(r"\D", "", antes_fe)
                    if len(digitos_mascarados) == 8:
                        ceps = [digitos_mascarados]
                        break
            if ceps:
                digitos = re.sub(r"\D", "", ceps[-1])
                valor_cep = f"{digitos[:2]}.{digitos[2:5]}-{digitos[5:]}"
                _adicionar_unico(resultado["cadastros"], {"rotulo": "CEP", "valor": valor_cep, "origem": codigo})

        if "RESERVA LEGAL" in normalizado:
            reserva_car = re.search(r"área\s+de\s+reserva\s+legal\s*:\s*([\d.,]+)", descricao_ato, re.IGNORECASE)
            reserva = reserva_car or re.search(r"área\s+de\s*([\d.,]+)\s*(?:ha|hectares?)", descricao_ato, re.IGNORECASE)
            valor_reserva = "Área não identificada"
            if reserva:
                valor = _valor_decimal(reserva.group(1))
                if valor is not None:
                    valor_reserva = f"{_formatar_numero(valor)} ha"
            rotulo_reserva = "Reserva legal declarada no CAR" if reserva_car else "Reserva legal"
            _adicionar_unico(resultado["restricoes"], {"rotulo": rotulo_reserva, "valor": valor_reserva, "origem": codigo})

        if "CLAUSULA RESTRITIVA" in normalizado or "CLAUSULAS RESTRITIVAS" in normalizado:
            prazo = re.search(r"período\s+de\s*(\d+)\s*\([^)]*\)\s*anos", descricao_ato, re.IGNORECASE)
            valor = f"Prazo declarado de {prazo.group(1)} anos" if prazo else "Cláusula averbada"
            _adicionar_unico(resultado["restricoes"], {"rotulo": "Cláusula restritiva", "valor": valor, "origem": codigo})

        diferenca = re.search(
            r"diferença\s+entre.*?\[\s*([\d.,]+)\s*hectares?\s*\].*?\[\s*([\d.,]+)\s*hectares?\s*\]",
            descricao_ato,
            re.IGNORECASE | re.DOTALL,
        )
        if diferenca:
            mensagem = f"Área documental: {diferenca.group(1)} ha; representação gráfica: {diferenca.group(2)} ha."
            _adicionar_unico(resultado["divergencias"], {"rotulo": "Divergência de área", "valor": mensagem, "origem": codigo})

    if resultado["situacao"]["status"] == "ATIVA" and _tem_encerramento_explicito(texto_normalizado):
        resultado["situacao"] = {"status": "ENCERRADA", "origem": "Texto registral"}
        resultado["alertas"].append({
            "tipo": "MATRÍCULA ENCERRADA",
            "mensagem": "Consulte a matrícula sucessora antes de concluir a situação atual do imóvel.",
            "origem": "Texto registral",
        })

    ordem_identificacao = {"Matrícula": 0, "Lote": 1, "Quadra": 2, "Rua": 3, "Número": 4, "Setor": 5, "Denominação": 6}
    resultado["identificacao"].sort(key=lambda item: ordem_identificacao.get(item["rotulo"], 7))
    ordem_areas = {"Área": 0, "Área Construída": 1}
    resultado["areas"].sort(key=lambda item: ordem_areas.get(item["rotulo"], 2))

    try:
        total_titularidade = sum(_percentual_numerico(item["proporcao"]) for item in proprietarios)
    except (KeyError, TypeError, ValueError):
        total_titularidade = 0
    if proprietarios and abs(total_titularidade - 100) > 0.05:
        resultado["alertas"].append({
            "tipo": "TITULARIDADE INCONSISTENTE",
            "mensagem": f"Os percentuais identificados totalizam {_formatar_numero(total_titularidade, 2)}%.",
            "origem": "Cadeia dominial",
        })

    for divergencia in resultado["divergencias"]:
        resultado["alertas"].append({
            "tipo": "DIVERGÊNCIA CADASTRAL",
            "mensagem": divergencia["valor"],
            "origem": divergencia["origem"],
        })

    return resultado
