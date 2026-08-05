import hashlib
import re
import unicodedata


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

PAPEIS = (
    "EMITENTE/DEVEDOR", "EMITENTE", "DEVEDOR", "DEVEDORA", "DEVEDORES",
    "CREDOR", "CREDORA", "CREDORES", "FIDUCIANTE", "FIDUCIÁRIO",
    "GARANTIDOR", "GARANTIDORA", "GARANTIDORES", "AVALISTA", "AVALISTAS",
    "INTERVENIENTE", "INTERVENIENTES", "OUTORGANTE", "OUTORGADO",
)


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
    papeis = "|".join(re.escape(item) for item in PAPEIS)
    marcador = rf"(?:(?P<papel>{papeis})\s*:\s*|\bcom\s+|\b\d+\)\s*[-–—]?\s*)"
    documento = (
        r"(?P<nome>[A-ZÀ-Ü][A-Za-zÀ-ÿ0-9&' .-]{2,150}?),"
        r".{0,360}?"
        r"(?P<tipo>CPF|CNPJ)(?:/MF)?\s*(?:sob\s+o\s+n[.º°o]*\s*)?"
        r"(?P<numero>[0-9./-]{11,18})"
    )
    encontrados = []
    vistos = set()
    for item in re.finditer(marcador + documento, texto_linear, re.IGNORECASE):
        nome = re.sub(r"\s+", " ", item.group("nome")).strip(" ,;:-")
        nome = re.sub(r"^(?:O|A|OS|AS)\s+", "", nome, flags=re.IGNORECASE)
        numero = _formatar_documento(item.group("numero"))
        chave = (normalizar_busca(nome), re.sub(r"\D", "", numero))
        if len(nome) < 3 or chave in vistos:
            continue
        vistos.add(chave)
        encontrados.append({
            "nome": nome,
            "documento": numero,
            "papel": normalizar_busca(item.group("papel") or "PARTE"),
        })
    return encontrados


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
        "pessoas": item["pessoas"] or [],
        "produtos": item["produtos"] or [],
        "safras": item["safras"] or [],
        "consultadoEm": item["consultado_em"].isoformat(),
        "alterado": bool(item.get("alterado", False)),
    }
