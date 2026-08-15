import os
import re


MODO_HIBRIDO = "hibrido"
MODO_LEGADO = "legado"

_MODOS_LEGADOS = {"0", "false", "legacy", "legado"}
_SIGEF = re.compile(
    r"confrontando\s+com\s+CNS\s*:\s*[\d.\-]+\s*\|\s*"
    r"Mat\.?\s*([\d.,]{1,12})\s*\|\s*"
    r"(.{3,300}?)(?=\s+no\s+azimute\b|\s+confrontando\s+com\b|;|$)",
    re.IGNORECASE,
)
_FORMATO_ANTIGO = re.compile(
    r"confrontando\s+com\s+(?:a|o|as|os)?\s*([^/;]{3,180}?)\s*"
    r"/\s*Mat\.?\s*([\d.,]{1,12})",
    re.IGNORECASE,
)
_MARCADOR_PROPRIETARIO = re.compile(
    r"\b(?:"
    r"propriedade\s+(?:de|do|da|dos|das)|"
    r"pertencente\s+(?:a|ao|à|à)|"
    r"propriet[aá]ri[oa]\s*:"
    r")\s*",
    re.IGNORECASE,
)


def modo_analise_mapa_onr() -> str:
    configurado = os.getenv("MAPA_ONR_MODO_ANALISE", MODO_HIBRIDO).strip().lower()
    return MODO_LEGADO if configurado in _MODOS_LEGADOS else MODO_HIBRIDO


def _compactar(valor: str) -> str:
    return re.sub(r"\s+", " ", valor or "").strip(" \t\r\n,;-")


def _numero_matricula(valor: str) -> str | None:
    numero = re.sub(r"\D", "", valor or "")
    return numero or None


def _separar_descricao_e_proprietario(detalhe: str) -> tuple[str, str | None, str | None]:
    detalhe = _compactar(detalhe)
    marcador = _MARCADOR_PROPRIETARIO.search(detalhe)
    if not marcador:
        return detalhe, None, "Proprietário não identificado explicitamente no texto"

    descricao = _compactar(detalhe[: marcador.start()])
    descricao = re.sub(r"\s+e$", "", descricao, flags=re.IGNORECASE).strip(" ,;-")
    proprietario = _compactar(detalhe[marcador.end() :])
    if not proprietario:
        return descricao, None, "Nome do proprietário ausente após o marcador registral"
    if proprietario.endswith(("...", "…")) or "..." in proprietario:
        return descricao, None, "Nome do proprietário está incompleto na fonte"
    return descricao, proprietario, None


def _ocorrencias_confrontantes(texto: str) -> list[dict]:
    compacto = re.sub(r"\s+", " ", texto or "").strip()
    ocorrencias = []

    for encontrado in _SIGEF.finditer(compacto):
        descricao, proprietario, pendencia = _separar_descricao_e_proprietario(
            encontrado.group(2)
        )
        ocorrencias.append({
            "numero_matricula_confrontante": _numero_matricula(encontrado.group(1)),
            "nome_proprietario_confrontante": proprietario,
            "descricao_confrontacao": descricao or None,
            "confianca": "baixa" if pendencia else "alta",
            "pendencia": pendencia,
            "evidencia": _compactar(encontrado.group(0))[:360],
        })

    for encontrado in _FORMATO_ANTIGO.finditer(compacto):
        descricao, proprietario, pendencia = _separar_descricao_e_proprietario(
            encontrado.group(1)
        )
        ocorrencias.append({
            "numero_matricula_confrontante": _numero_matricula(encontrado.group(2)),
            "nome_proprietario_confrontante": proprietario,
            "descricao_confrontacao": descricao or None,
            "confianca": "baixa" if pendencia else "alta",
            "pendencia": pendencia,
            "evidencia": _compactar(encontrado.group(0))[:360],
        })

    return ocorrencias


def extrair_confrontantes_semanticos(texto: str) -> list[dict]:
    """Extrai confrontantes sem confundir imóvel/servidão com pessoa proprietária."""
    agrupados: dict[str, dict] = {}
    sem_matricula = 0

    for ocorrencia in _ocorrencias_confrontantes(texto):
        numero = ocorrencia["numero_matricula_confrontante"]
        if numero:
            chave = numero
        else:
            sem_matricula += 1
            chave = f"sem-matricula-{sem_matricula}"

        atual = agrupados.get(chave)
        if atual is None:
            atual = {
                "numero_matricula_confrontante": numero,
                "nome_proprietario_confrontante": None,
                "descricoes_confrontacao": [],
                "confianca": "baixa",
                "pendencia": ocorrencia["pendencia"],
                "evidencias": [],
                "ocorrencias": [],
            }
            agrupados[chave] = atual

        descricao = ocorrencia["descricao_confrontacao"]
        if descricao and descricao not in atual["descricoes_confrontacao"]:
            atual["descricoes_confrontacao"].append(descricao)
        if ocorrencia["evidencia"] not in atual["evidencias"]:
            atual["evidencias"].append(ocorrencia["evidencia"])

        atual["ocorrencias"].append(ocorrencia)

    for atual in agrupados.values():
        ocorrencias = atual["ocorrencias"]
        nomes = {
            item["nome_proprietario_confrontante"].casefold():
                item["nome_proprietario_confrontante"]
            for item in ocorrencias
            if item["nome_proprietario_confrontante"]
        }
        incompletas = [item for item in ocorrencias if item["pendencia"]]
        if len(nomes) > 1:
            atual["pendencia"] = (
                "Há proprietários divergentes para a mesma matrícula confrontante"
            )
        elif incompletas:
            atual["pendencia"] = incompletas[0]["pendencia"]
            if nomes:
                atual["pendencia"] = (
                    "Nem todas as ocorrências identificam expressamente o mesmo proprietário"
                )
        elif len(nomes) == 1:
            atual["nome_proprietario_confrontante"] = next(iter(nomes.values()))
            atual["confianca"] = "alta"
            atual["pendencia"] = None

    return list(agrupados.values())


def construir_contexto_mapa_onr(texto: str, resultado_aeri: dict) -> dict:
    modo = modo_analise_mapa_onr()
    imovel = resultado_aeri.get("imovel") or {}
    if modo == MODO_LEGADO:
        return {
            "modo": MODO_LEGADO,
            "confrontantes": [],
            "total_pendencias": 0,
        }

    confrontantes = extrair_confrontantes_semanticos(texto)
    return {
        "modo": MODO_HIBRIDO,
        "analise_aeri": {
            "tipo_imovel": str(imovel.get("tipo") or "").lower() or None,
            "situacao": (imovel.get("situacao") or {}).get("status"),
        },
        "confrontantes": confrontantes,
        "total_pendencias": sum(1 for item in confrontantes if item["pendencia"]),
    }
