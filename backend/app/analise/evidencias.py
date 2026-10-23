import re
import unicodedata


LIMITE_TRECHO = 420


def normalizar(valor: object) -> str:
    texto = unicodedata.normalize("NFD", str(valor or ""))
    texto = "".join(caractere for caractere in texto if unicodedata.category(caractere) != "Mn")
    return re.sub(r"\s+", " ", texto).strip().upper()


def compactar(valor: object) -> str:
    return re.sub(r"\s+", " ", str(valor or "")).strip()


def trecho_evidencia(texto: str, termo: str | None = None, limite: int = LIMITE_TRECHO) -> str:
    texto_compacto = compactar(texto)
    if len(texto_compacto) <= limite:
        return texto_compacto

    inicio = 0
    if termo:
        posicao = normalizar(texto_compacto).find(normalizar(termo))
        if posicao >= 0:
            inicio = max(0, posicao - limite // 3)
    fim = min(len(texto_compacto), inicio + limite)
    prefixo = "..." if inicio else ""
    sufixo = "..." if fim < len(texto_compacto) else ""
    return f"{prefixo}{texto_compacto[inicio:fim].strip()}{sufixo}"


def descricao_ato(ato) -> str:
    return str(getattr(ato, "descricao", None) or (ato.get("descricao", "") if isinstance(ato, dict) else ""))


def codigo_ato(ato) -> str:
    return str(getattr(ato, "codigo", None) or (ato.get("codigo", "") if isinstance(ato, dict) else ""))


def normalizar_codigo_ato(codigo: str) -> str:
    encontrado = re.fullmatch(r"\s*(R|AV)\s*[.\-]?\s*0*(\d+)\s*", str(codigo), re.IGNORECASE)
    return f"{encontrado[1].upper()}.{int(encontrado[2])}" if encontrado else normalizar(codigo)


def trecho_por_padroes(texto: str, padroes: list[str], limite: int = LIMITE_TRECHO) -> str:
    """Localiza a cláusula na grafia original, inclusive além do cabeçalho.

    O mapa mantém offsets corretos quando a remoção de acentos/caixa expande
    algum caractere. Nunca corta usando offsets de uma string diferente.
    """
    compacto = compactar(texto)
    normalizado = []
    mapa = []
    for indice, caractere in enumerate(compacto):
        parte = normalizar(caractere) if not caractere.isspace() else " "
        normalizado.append(parte)
        mapa.extend([indice] * len(parte))
    linear = "".join(normalizado)
    for padrao in padroes:
        match = re.search(padrao, linear)
        if match:
            inicio_termo = mapa[match.start()]
            fim_termo = mapa[match.end()-1] + 1
            inicio = max(0, inicio_termo - limite // 4)
            fim = min(len(compacto), max(inicio + limite, fim_termo))
            return ("..." if inicio else "") + compacto[inicio:fim].strip() + ("..." if fim < len(compacto) else "")
    return trecho_evidencia(compacto, limite=limite)


def ato_por_codigo(atos: list, codigo: str):
    alvo = normalizar_codigo_ato(codigo)
    for ato in reversed(atos):
        atual = normalizar_codigo_ato(codigo_ato(ato))
        if atual == alvo:
            return ato
    return None


def evidencia_por_origem(texto: str, atos: list, origem: str, termo: str | None = None) -> dict:
    ato = ato_por_codigo(atos, origem)
    if ato is not None:
        return {
            "fonte": codigo_ato(ato),
            "trecho": trecho_evidencia(descricao_ato(ato), termo),
        }
    if normalizar(origem) in {"CABECALHO", "MATRICULA", "TEXTO REGISTRAL"}:
        cabecalho = re.split(r"(?:^|\n)\s*(?:R|AV)[.\-]\s*\d+", texto, maxsplit=1, flags=re.IGNORECASE)[0]
        return {"fonte": origem, "trecho": trecho_evidencia(cabecalho or texto, termo)}
    return {"fonte": origem or "NÃO IDENTIFICADA", "trecho": ""}
