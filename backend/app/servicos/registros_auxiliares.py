import hashlib
import re
import unicodedata
from decimal import Decimal


PRODUTOS = (
    ("SOJA", r"\bSOJA(?:\s+EM\s+GRAOS)?\b"),
    ("MILHO", r"\bMILHO\b"),
    ("SORGO", r"\bSORGO\b"),
    ("ALGODÃO", r"\bALGODAO\b"),
    ("CAFÉ", r"\bCAFE\b"),
    ("FEIJÃO", r"\bFEIJAO\b"),
    ("ARROZ", r"\bARROZ\b"),
    ("TRIGO", r"\bTRIGO\b"),
    ("ESTUFAS", r"\bESTUFAS?\b"),
    ("BOVINOS", r"\bBOVINOS?\b"),
    ("NOVILHOS", r"\bNOVILHOS?\b"),
    ("BEZERROS", r"\bBEZERROS?\b"),
    ("VACAS", r"\bVACAS?\b"),
    ("EQUINOS", r"\bEQUINOS?\b"),
)

PADRAO_EMITENTE = r"EMITENTE(?:\(S\)|S)?"
PADRAO_DEVEDOR = r"DEVEDOR(?:\(A\)|\(ES\)|\(AS\)|A|ES|AS)?"
PADRAO_DEPOSITARIO = r"DEPOSIT[ÁA]RIO(?:\(S\)|S)?"
PADRAO_FIEL = rf"(?:FIEL(?:\(IS\))?|FI[ÉE]IS)(?:\s+{PADRAO_DEPOSITARIO})?"
PADRAO_PAPEL_COMPLEMENTAR = (
    rf"(?:{PADRAO_EMITENTE}|{PADRAO_DEVEDOR}|{PADRAO_FIEL}|{PADRAO_DEPOSITARIO})"
)
PADRAO_PAPEIS_BUSCADOS = (
    rf"(?:{PADRAO_EMITENTE}|{PADRAO_DEVEDOR})"
    rf"(?:\s*(?:/|E|-)\s*{PADRAO_PAPEL_COMPLEMENTAR})*"
)

PADRAO_PAPEIS_NAO_BUSCADOS = (
    r"CREDOR(?:A|ES|AS)?|AVALISTA(?:S)?|INTERVENIENTE(?:S)?|GARANTIDOR(?:A|ES|AS)?"
    r"|FIDUCIANTE(?:S)?|FIDUCI[ÁA]RIO(?:A|S)?|OUTORGANTE(?:S)?|OUTORGADO(?:A|S)?"
    r"|C[ÔO]NJUGE(?:S)?|ANUENTE(?:S)?|REPRESENTANTE(?:S)?|PROCURADOR(?:A|ES|AS)?"
    r"|PROPRIET[ÁA]RIO(?:A|S)?"
)

VALOR_CERTIDAO_REGISTRO_AUXILIAR = Decimal("139.93")


def normalizar_busca(valor: str) -> str:
    sem_acentos = "".join(
        caractere for caractere in unicodedata.normalize("NFKD", valor or "")
        if not unicodedata.combining(caractere)
    )
    return re.sub(r"\s+", " ", sem_acentos).strip().upper()


def _formatar_documento(valor: str) -> str:
    digitos = re.sub(r"\D", "", valor)
    if len(digitos) == 11:
        return f"{digitos[:3]}.{digitos[3:6]}.{digitos[6:9]}-{digitos[9:]}"
    if len(digitos) == 14:
        return f"{digitos[:2]}.{digitos[2:5]}.{digitos[5:8]}/{digitos[8:12]}-{digitos[12:]}"
    return digitos


def _extrair_pessoas(texto: str) -> list[dict]:
    texto_linear = re.sub(r"\s+", " ", texto)
    separador_papel = r"(?P<separador>\s*:\s*|\s*[-–—]\s*|\s+)"
    cabecalho = re.compile(
        rf"\b(?P<papel>{PADRAO_PAPEIS_BUSCADOS}){separador_papel}",
        re.IGNORECASE,
    )
    papel_nao_buscado = re.compile(
        rf"\b(?P<papel>{PADRAO_PAPEIS_NAO_BUSCADOS}){separador_papel}",
        re.IGNORECASE,
    )
    cabecalho_maiusculo = re.compile(r"\b[A-ZÀ-Ü][A-ZÀ-Ü0-9/ ()-]{2,60}\s*:\s*")
    pessoa_no_inicio = re.compile(
        r"^\s*(?:\d+\)\s*[-–—]?\s*)?"
        r"(?P<nome>[A-ZÀ-Ü][A-Za-zÀ-ÿ0-9&' .-]{2,150}?),"
        r".{0,420}?"
        r"(?P<tipo>CPF|CNPJ)(?:/MF)?\s*(?:sob\s+o\s+n[.º°o]*\s*)?"
        r"(?P<numero>[0-9./-]{11,18})",
        re.IGNORECASE,
    )
    encontrados = []
    vistos = set()
    def marcador_valido(item) -> bool:
        return ":" in item.group("separador") or item.group("papel") == item.group("papel").upper()

    cabecalhos = [item for item in cabecalho.finditer(texto_linear) if marcador_valido(item)]
    cabecalhos_nao_buscados = [
        item for item in papel_nao_buscado.finditer(texto_linear) if marcador_valido(item)
    ]
    for indice, marcador in enumerate(cabecalhos):
        inicio = marcador.end()
        limite = cabecalhos[indice + 1].start() if indice + 1 < len(cabecalhos) else len(texto_linear)
        proximo_papel_nao_buscado = next(
            (
                item for item in cabecalhos_nao_buscados
                if inicio <= item.start() < limite
            ),
            None,
        )
        candidatos_fim = [
            item.start()
            for item in (
                proximo_papel_nao_buscado,
                cabecalho_maiusculo.search(texto_linear, inicio, limite),
            )
            if item
        ]
        fim = min(candidatos_fim, default=limite)
        bloco = texto_linear[inicio:fim]
        papel = normalizar_busca(marcador.group("papel"))
        plural = bool(re.search(
            r"\b(?:EMITENTES|DEVEDORES|DEVEDORAS)\b|\((?:S|ES|AS)\)",
            papel,
        ))
        segmentos = re.split(r";\s*(?=(?:\d+\)\s*[-–—]?\s*)?[A-ZÀ-Ü])", bloco) if plural else [bloco]
        for segmento in segmentos:
            item = pessoa_no_inicio.search(segmento)
            if not item:
                continue
            nome = re.sub(r"\s+", " ", item.group("nome")).strip(" ,;:-")
            nome = re.sub(r"^(?:O|A|OS|AS)\s+", "", nome, flags=re.IGNORECASE)
            numero = _formatar_documento(item.group("numero"))
            chave = (normalizar_busca(nome), re.sub(r"\D", "", numero))
            if len(nome) < 3 or chave in vistos:
                continue
            vistos.add(chave)
            encontrados.append({"nome": nome, "documento": numero, "papel": papel})
    return encontrados


def _extrair_situacao(texto: str) -> str:
    normalizado = normalizar_busca(texto)
    padroes_baixa_integral = (
        r"\bCANCELAMENTO\s+(?:TOTAL\s+)?(?:DO|DA|DESTE|DESTA)\s+"
        r"(?:PENHOR|ALIENACAO|GARANTIA|CEDULA|REGISTRO)",
        r"\bFICA(?:M)?\s+CANCELAD[OA]S?\s+(?:O|A|OS|AS)?\s*"
        r"(?:R\.?\s*0*1\b|REGISTRO|PENHOR|ALIENACAO|GARANTIA|CEDULA)",
        r"\bCANCELA-SE\s+(?:O|A)?\s*(?:R\.?\s*0*1\b|REGISTRO|PENHOR|ALIENACAO|GARANTIA|CEDULA)",
        r"\bBAIXA\s+(?:TOTAL\s+)?(?:DO|DA)\s+(?:REGISTRO|PENHOR|ALIENACAO|GARANTIA|CEDULA)",
        r"\bEXTINCAO\s+(?:TOTAL\s+)?(?:DO|DA)\s+(?:PENHOR|ALIENACAO|GARANTIA|CEDULA)",
    )
    if any(re.search(padrao, normalizado) for padrao in padroes_baixa_integral):
        return "BAIXADO"
    return "ATIVO"


def resumo_certidao_registro_auxiliar(quantidade_registros: int) -> dict:
    quantidade = max(0, int(quantidade_registros))
    multiplicador = max(1, quantidade)
    valor = VALOR_CERTIDAO_REGISTRO_AUXILIAR * multiplicador
    return {
        "resultado": "POSITIVA" if quantidade else "NEGATIVA",
        "quantidadeRegistros": quantidade,
        "valorCertidao": f"{valor:.2f}",
    }


def extrair_indice_registro_auxiliar(numero: int | str, texto: str) -> dict:
    normalizado = normalizar_busca(texto)
    penhor_principal = bool(re.search(
        r"OBJETO\s+DA\s+GARANTIA\s*:.{0,140}\bPENHOR\b|\bPENHOR\s+CEDULAR\b",
        normalizado,
    ))
    alienacao_principal = bool(re.search(
        r"OBJETO\s+DA\s+GARANTIA\s*:.{0,140}\bALIENACAO\b|\bALIENACAO\s+FIDUCIARIA\b",
        normalizado,
    ))
    if penhor_principal:
        modalidade = "PENHOR"
    elif alienacao_principal:
        modalidade = "ALIENAÇÃO"
    elif re.search(r"\bPENHOR\b", normalizado):
        modalidade = "PENHOR"
    elif "ALIENACAO" in normalizado:
        modalidade = "ALIENAÇÃO"
    else:
        modalidade = "OUTROS"

    produtos = [rotulo for rotulo, padrao in PRODUTOS if re.search(padrao, normalizado)]
    safras = []
    for inicio, fim in re.findall(r"\b(20\d{2})\s*[/\-]\s*(20\d{2})\b", normalizado):
        safra = f"{inicio}/{fim}"
        if safra not in safras:
            safras.append(safra)
    for inicio, fim in re.findall(
        r"PERIODO\s+AGRICOLA.{0,80}?/[ ]?(20\d{2})\s+A\s+.{0,40}?/[ ]?(20\d{2})",
        normalizado,
    ):
        safra = f"{inicio}/{fim}"
        if safra not in safras:
            safras.append(safra)

    pessoas = _extrair_pessoas(texto)
    nomes_busca = " | ".join(normalizar_busca(item["nome"]) for item in pessoas)
    documentos_busca = " ".join(re.sub(r"\D", "", item["documento"]) for item in pessoas)
    return {
        "numero": int(numero),
        "texto_hash": hashlib.sha256(texto.encode("utf-8")).hexdigest(),
        "modalidade": modalidade,
        "situacao": _extrair_situacao(texto),
        "pessoas": pessoas,
        "nomes_busca": nomes_busca,
        "documentos_busca": documentos_busca,
        "produtos": produtos,
        "safras": safras,
    }


def registro_auxiliar_json(item: dict) -> dict:
    return {
        "numero": item["numero"],
        "modalidade": item["modalidade"],
        "situacao": item.get("situacao", "ATIVO"),
        "pessoas": item["pessoas"] or [],
        "produtos": item["produtos"] or [],
        "safras": item["safras"] or [],
        "consultadoEm": item["consultado_em"].isoformat(),
        "alterado": bool(item.get("alterado", False)),
    }
