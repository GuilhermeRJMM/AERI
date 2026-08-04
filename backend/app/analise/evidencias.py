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


def ato_por_codigo(atos: list, codigo: str):
    alvo = normalizar(codigo).replace("-", ".")
    for ato in reversed(atos):
        atual = normalizar(codigo_ato(ato)).replace("-", ".")
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
