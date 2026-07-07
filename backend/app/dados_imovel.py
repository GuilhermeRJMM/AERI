import re


def _limpar(texto):
    return re.sub(r"\s+", " ", texto or "").strip(" ,.;:-")


def _primeiro(padroes, texto, flags=re.I | re.DOTALL):
    for padrao in padroes:
        m = re.search(padrao, texto, flags)
        if m:
            return _limpar(m.group(1))
    return ""


def _normalizar_area(valor, unidade):
    valor = _limpar(valor)
    unidade = (unidade or "").lower()
    if not valor:
        return ""
    if "ha" in unidade or "hectare" in unidade:
        return f"{valor} ha"
    return f"{valor} m²"


def _extrair_matricula(texto):
    return _primeiro([r"\bMATR[ÍI]CULA\s*(?:N[º°.]?\s*)?([\d.]+)"], texto)


def _extrair_area(texto, unidade_preferida):
    if unidade_preferida == "ha":
        padroes = [
            r"\b[aá]rea\s+(?:total\s+)?(?:de\s+)?([\d.,]+)\s*(ha|hectares?)\b",
            r"\b([\d.,]+)\s*(ha|hectares?)\b",
        ]
    else:
        padroes = [
            r"\b[aá]rea\s+(?!constru[íi]da\b)(?:total\s+)?(?:de\s+)?([\d.,]+)\s*(m²|m2|metros?\s+quadrados?)\b",
            r"\bcom\s+a\s+[aá]rea\s+de\s+([\d.,]+)\s*(m²|m2|metros?\s+quadrados?)\b",
        ]

    for padrao in padroes:
        m = re.search(padrao, texto, re.I | re.DOTALL)
        if m:
            return _normalizar_area(m.group(1), m.group(2))
    return ""


def _extrair_confrontacao(texto, posicao):
    mapas = {
        "frente": [
            r"\bfrente\s+(?:com|para|pela|pela dita|com a citada)\s+([^;]+)",
            r"\bna\s+frente\s+com\s+([^;]+)",
            r"\bdividindo\s+na\s+frente\s+com\s+([^;]+)",
        ],
        "direita": [
            r"\blateral\s+direita\s+com\s+([^;]+)",
            r"\blado\s+direito.*?\bconfrontando\s+(?:com\s+)?([^;]+)",
            r"\bdo\s+lado\s+direito.*?\bconfrontando\s+(?:com\s+)?([^;]+)",
        ],
        "esquerda": [
            r"\blateral\s+esquerda\s+com\s+([^;]+)",
            r"\blado\s+esquerdo.*?\bconfrontando\s+(?:com\s+)?([^;]+)",
            r"\bdo\s+lado\s+esquerdo.*?\bconfrontando\s+(?:com\s+)?([^;]+)",
        ],
        "fundos": [
            r"\bfundos\s+com\s+([^;]+)",
            r"\bnos\s+fundos.*?\bconfrontando\s+(?:com\s+)?([^;]+)",
            r"\be,\s*nos\s+fundos.*?\bconfrontando\s+(?:com\s+)?([^;]+)",
        ],
    }
    return _primeiro(mapas[posicao], texto)


def _extrair_finalidade(texto):
    if re.search(r"\bresidencial\s+e\s+comercial\b", texto, re.I):
        return "Residencial e comercial"
    if re.search(r"\bcomercial\b", texto, re.I):
        return "Comercial"
    if re.search(r"\bresidencial\b|\bmoradia\b|\bhabita[cç][aã]o\b", texto, re.I):
        return "Residencial"
    if re.search(r"\brural\b|fazenda|s[ií]tio|ch[aá]cara|gleba", texto, re.I):
        return "Rural"
    return ""


def _extrair_setor(texto):
    return _primeiro(
        [
            r"\b(Setor\s+[A-ZÁÀÂÃÉÈÊÍÌÎÓÒÔÕÚÙÛÇ0-9][^,;.]*)",
            r"\b(Jardim\s+[A-ZÁÀÂÃÉÈÊÍÌÎÓÒÔÕÚÙÛÇ0-9][^,;.]*)",
            r"\b(Residencial\s+[A-ZÁÀÂÃÉÈÊÍÌÎÓÒÔÕÚÙÛÇ0-9][^,;.]*)",
            r"\b(Vila\s+[A-ZÁÀÂÃÉÈÊÍÌÎÓÒÔÕÚÙÛÇ0-9][^,;.]*)",
        ],
        texto,
    )


def _extrair_urbano(texto):
    return {
        "tipo": "urbano",
        "matricula": _extrair_matricula(texto),
        "lote": _primeiro([r"\bLote(?:\s+de\s+terras)?\s*(?:n[º°.]?\s*)?([A-Z0-9.\-/]+)"], texto),
        "quadra": _primeiro([r"\bquadra\s*(?:n[º°.]?\s*)?([A-Z0-9.\-/]+)"], texto),
        "area": _extrair_area(texto, "m2"),
        "rua": _primeiro([r"\b(Rua\s+[^,;.]*)", r"\b(Avenida\s+[^,;.]*)", r"\b(Travessa\s+[^,;.]*)"], texto),
        "setor": _extrair_setor(texto),
        "cci": _primeiro(
            [
                r"\bCCI\s*(?:n[º°.]?\s*)?([A-Z0-9.\-/]+)",
                r"\bCadastrad[oa]\s+[^.;]*?\s+sob\s+o\s+n[º°.]?\s*([A-Z0-9.\-/]+)",
            ],
            texto,
        ),
        "cep": _primeiro([r"\bCEP\s*(?:n[º°.]?\s*)?(\d{5}-?\d{3})"], texto),
        "numero": _primeiro([r"\bn[.º°]*\s*(\d+[A-Z]?)\b", r"\bn[úu]mero\s+(\d+[A-Z]?)\b"], texto),
        "area_construida": _extrair_area_construida(texto),
        "finalidade": _extrair_finalidade(texto),
        "confrontacoes": {
            "frente": _extrair_confrontacao(texto, "frente"),
            "lateral_direita": _extrair_confrontacao(texto, "direita"),
            "lateral_esquerda": _extrair_confrontacao(texto, "esquerda"),
            "fundos": _extrair_confrontacao(texto, "fundos"),
        },
    }


def _extrair_area_construida(texto):
    return _primeiro(
        [
            r"\b[aá]rea\s+constru[íi]da\s+(?:de\s+)?([\d.,]+\s*(?:m²|m2|metros?\s+quadrados?))",
            r"\bconstru[cç][aã]o\s+(?:com\s+)?(?:a\s+)?[aá]rea\s+(?:de\s+)?([\d.,]+\s*(?:m²|m2|metros?\s+quadrados?))",
        ],
        texto,
    ).replace("m2", "m²")


def _extrair_rural(texto):
    return {
        "tipo": "rural",
        "matricula": _extrair_matricula(texto),
        "nome": _primeiro(
            [
                r"\bIM[ÓO]VEL\s*:\s*((?:Fazenda|S[ií]tio|Ch[aá]cara|Gleba|Est[âa]ncia)[^,;.]+)",
                r"\b((?:Fazenda|S[ií]tio|Ch[aá]cara|Gleba|Est[âa]ncia)\s+[^,;.]+)",
            ],
            texto,
        ),
        "area": _extrair_area(texto, "ha"),
        "incra_ccir": _primeiro(
            [
                r"\b(?:INCRA|CCIR)(?:\s*/\s*(?:INCRA|CCIR))?[^0-9]{0,30}([0-9.\-/]+)",
                r"\bC[óo]digo\s+do\s+im[óo]vel\s+rural[^0-9]{0,30}([0-9.\-/]+)",
            ],
            texto,
        ),
        "itr_cib_nirf": _primeiro(
            [
                r"\b(?:ITR|CIB|NIRF)(?:\s*/\s*(?:ITR|CIB|NIRF))*[^0-9]{0,30}([0-9.\-/]+)",
            ],
            texto,
        ),
        "car": _primeiro(
            [
                r"\bCAR(?:\s*n[º°.]?)?[^A-Z0-9]{0,40}([A-Z]{2}-[0-9]{7}-[A-Z0-9.\-]+)",
                r"\bCAR(?:\s*n[º°.]?)?[^A-Z0-9]{0,40}([A-Z0-9.\-/]{10,})",
            ],
            texto,
        ),
    }


def _eh_rural(texto):
    return bool(
        re.search(r"\b(Fazenda|S[ií]tio|Ch[aá]cara|Gleba|CCIR|INCRA|NIRF|CIB|CAR)\b", texto, re.I)
        or re.search(r"\b[aá]rea\s+(?:de\s+)?[\d.,]+\s*(ha|hectares?)\b", texto, re.I)
    )


def _cabecalho(texto):
    return re.split(r"(?:^|\n)[ \t\-]*(?:R|AV)[.\-]\s*\d+[\.\-]", texto, maxsplit=1, flags=re.I)[0]


def _atos_retificacao(texto):
    padrao = r"(?:^|\n)[ \t\-]*((?:R|AV)[.\-]\s*\d+[\.\-].*?)(?=(?:\n[ \t\-]*(?:R|AV)[.\-]\s*\d+[\.\-])|\Z)"
    for ato in re.findall(padrao, texto, flags=re.I | re.DOTALL):
        if re.search(r"\bRETIFICA[ÇC][ÃA]O\b|EX-?OFFICIO|DE OF[ÍI]CIO", ato, re.I):
            yield ato


def _mesclar(base, novo):
    for chave, valor in novo.items():
        if chave == "tipo":
            continue
        if isinstance(valor, dict):
            destino = base.setdefault(chave, {})
            for sub_chave, sub_valor in valor.items():
                if sub_valor:
                    destino[sub_chave] = sub_valor
        elif valor:
            base[chave] = valor


def _com_proprietarios(dados, proprietarios):
    if dados.get("tipo") != "urbano":
        return dados
    nomes = [p.get("nome", "") for p in proprietarios or [] if p.get("nome")]
    dados["proprietario"] = "; ".join(nomes)
    return dados


def extrair_dados_imovel(texto, proprietarios=None):
    texto = texto or ""
    base_texto = _cabecalho(texto) or texto
    rural = _eh_rural(base_texto)
    dados = _extrair_rural(base_texto) if rural else _extrair_urbano(base_texto)

    for ato in _atos_retificacao(texto):
        novos = _extrair_rural(ato) if dados["tipo"] == "rural" else _extrair_urbano(ato)
        _mesclar(dados, novos)

    return _com_proprietarios(dados, proprietarios)
