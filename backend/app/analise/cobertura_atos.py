"""Conferência objetiva de cobertura, sem classificar ônus ou titularidade."""
import re
from backend.app.analise.evidencias import codigo_ato, normalizar_codigo_ato


# Leitura independente e conservadora dos cabeçalhos explícitos. Não inventa
# atos a partir de lacunas numéricas ou referências no meio de uma frase.
CABECALHO_EXPLICITO = re.compile(
    r"(?:^|\n)[ \t\-–—]*(R|AV)\s*[.\-]?\s*([0-9OIL]+)[ \t]*[-–—:]",
    re.IGNORECASE,
)


def _ordenar(codigos):
    return sorted(set(codigos), key=lambda c: (int(c.split(".")[1]), c))


def conferir_cobertura_texto(texto, atos):
    detectados = _ordenar(normalizar_codigo_ato(codigo_ato(ato)) for ato in atos)
    explicitos = _ordenar(
        f"{m[1].upper()}.{int(m[2].upper().translate(str.maketrans({'O':'0','I':'1','L':'1'})))}"
        for m in CABECALHO_EXPLICITO.finditer(texto)
    )
    faltantes = _ordenar(set(explicitos) - set(detectados))
    return {
        "estado": "DIVERGENTE" if faltantes else "CONFERIDA" if detectados else "SEM_ATOS",
        "escopo": "CABECALHOS_EXPLICITOS", "codigos_texto": detectados,
        "cabecalhos_explicitos": explicitos, "nao_segmentados": faltantes,
        "tri7": {"estado": "NAO_CONSULTADA"},
        "altera_resultado_oficial": False,
    }


def comparar_atos_tri7(cobertura, resposta):
    retorno = {**cobertura}
    if not isinstance(resposta, dict) or not isinstance(resposta.get("atos"), list):
        retorno["tri7"] = {"estado": "RESPOSTA_INVALIDA"}
        return retorno
    confirmados = set()
    invalidos = 0
    for item in resposta["atos"]:
        if not isinstance(item, dict):
            invalidos += 1
            continue
        if str(item.get("status", "")).strip().upper() != "REGISTRADO":
            continue
        codigo = normalizar_codigo_ato(item.get("ato", ""))
        if re.fullmatch(r"(?:R|AV)\.\d+", codigo):
            confirmados.add(codigo)
        else:
            invalidos += 1
    if invalidos:
        retorno["tri7"] = {"estado": "RESPOSTA_INVALIDA", "itens_invalidos": invalidos}
        return retorno
    texto = set(cobertura["codigos_texto"])
    faltantes = _ordenar(confirmados - texto)
    somente_texto = _ordenar(texto - confirmados)
    retorno["tri7"] = {
        "estado": "DIVERGENTE" if faltantes or somente_texto else "CONFERIDA",
        "registrados": _ordenar(confirmados), "faltantes_no_texto": faltantes,
        "somente_no_texto": somente_texto,
    }
    if faltantes or somente_texto:
        retorno["estado"] = "DIVERGENTE"
    return retorno
