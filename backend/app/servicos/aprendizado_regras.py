import re
import unicodedata
from uuid import UUID


CATEGORIAS_APRENDIZADO = {"ÔNUS", "RESTRIÇÃO", "PUBLICIDADE", "CANCELAMENTO", "IGNORAR"}


def normalizar_expressao(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", str(texto or "").upper())
    texto = texto.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", texto).strip()


def impacto_categoria(categoria: str) -> bool:
    return categoria in {"ÔNUS", "RESTRIÇÃO"}


def _mascarar_documentos(texto: str) -> str:
    texto = re.sub(r"(?<!\d)\d{2}[\s.\-/]*\d{3}[\s.\-/]*\d{3}[\s.\-/]*\d{4}[\s.\-/]*\d{2}(?!\d)", "[CNPJ]", texto)
    texto = re.sub(r"(?<!\d)\d{3}[\s.\-]*\d{3}[\s.\-]*\d{3}[\s.\-]*\d{2}(?!\d)", "[CPF]", texto)
    return texto


def validar_sugestao_aprendizado(dados: dict) -> dict:
    expressao = re.sub(r"\s+", " ", str(dados.get("expressao", "")).strip())
    categoria = str(dados.get("categoria", "")).strip().upper()
    tipo_onus = re.sub(r"\s+", " ", str(dados.get("tipo_onus", "")).strip().upper())
    justificativa = _mascarar_documentos(str(dados.get("justificativa", "")).strip())[:500]

    if categoria not in CATEGORIAS_APRENDIZADO:
        raise ValueError("Categoria de aprendizado inválida.")
    if len(expressao) < 4 or len(expressao) > 120:
        raise ValueError("Informe um termo de 4 a 120 caracteres.")
    if sum(1 for caractere in expressao if caractere.isdigit()) > 6:
        raise ValueError("Use um termo jurídico, sem documentos ou números longos.")

    normalizada = normalizar_expressao(expressao)
    if len(normalizada) < 4 or not re.search(r"[A-Z]", normalizada):
        raise ValueError("Informe um termo textual válido.")

    if categoria != "ÔNUS":
        tipo_onus = ""
    elif len(tipo_onus) > 80:
        raise ValueError("O tipo de ônus deve ter até 80 caracteres.")

    return {
        "expressao": expressao,
        "expressao_normalizada": normalizada,
        "categoria": categoria,
        "impacta_resultado": impacto_categoria(categoria),
        "tipo_onus": tipo_onus,
        "justificativa": justificativa,
    }


def validar_id_regra(valor: str) -> UUID:
    try:
        return UUID(str(valor))
    except ValueError as exc:
        raise ValueError("Regra de aprendizado inválida.") from exc


def encontrar_regra_aprendida(texto: str, regras_aprendidas: list[dict] | None) -> dict | None:
    texto_normalizado = normalizar_expressao(texto)
    melhor_regra = None
    melhor_indice = len(texto_normalizado) + 1

    for regra in regras_aprendidas or []:
        expressao = normalizar_expressao(regra.get("expressao_normalizada") or regra.get("expressao"))
        if not expressao:
            continue
        indice = texto_normalizado.find(expressao)
        if indice != -1 and indice < melhor_indice:
            melhor_regra = regra
            melhor_indice = indice

    return melhor_regra


def identificar_tipo_onus_aprendido(texto: str, regras_aprendidas: list[dict] | None) -> str | None:
    regra = encontrar_regra_aprendida(texto, regras_aprendidas)
    if regra and regra.get("categoria") == "ÔNUS" and regra.get("tipo_onus"):
        return str(regra["tipo_onus"])
    return None
