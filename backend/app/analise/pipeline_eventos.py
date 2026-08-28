"""Pipeline registral paralelo baseado em eventos normalizados.

Esta camada não substitui o motor oficial. Ela transforma a interpretação já
validada em uma representação intermediária estável, calcula efeitos e produz
diagnósticos de coerência. Enquanto estiver em modo paralelo, nenhuma decisão
desta camada altera ônus, titulares ou dados do imóvel entregues ao usuário.
"""

from __future__ import annotations

from hashlib import sha256
import json
import re
import unicodedata


VERSAO_PIPELINE_EVENTOS = "1.0.0"


def _normalizar(valor: object) -> str:
    texto = unicodedata.normalize("NFD", str(valor or ""))
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", texto).strip().upper()


def _atributo(ato: object, nome: str, padrao=None):
    if isinstance(ato, dict):
        return ato.get(nome, padrao)
    return getattr(ato, nome, padrao)


def _tipo_evento(ato: object) -> str:
    categoria = _normalizar(_atributo(ato, "categoria"))
    descricao = _normalizar(_atributo(ato, "descricao"))
    if categoria == "CANCELAMENTO":
        return "CANCELAMENTO"
    if categoria in {"ONUS", "RESTRICAO"}:
        return "CONSTITUICAO_GRAVAME"
    if categoria == "PUBLICIDADE":
        return "PUBLICIDADE"
    if re.search(r"\b(?:VENDA E COMPRA|COMPRA E VENDA|DOACAO|PARTILHA|INVENTARIO)\b", descricao):
        return "TRANSMISSAO"
    if re.search(r"\b(?:CEP|DESIGNACAO CADASTRAL|EDIFICACAO|CCIR|CAR|CIB|CCI)\b", descricao):
        return "ATUALIZACAO_IMOVEL"
    if re.search(r"\b(?:ENCERRAMENTO|ENCERRADA|TRANSPORTADA PARA A MATRICULA)\b", descricao):
        return "SITUACAO_MATRICULA"
    return "OUTRO"


def normalizar_atos(atos: list[object]) -> list[dict]:
    eventos = []
    for ordem, ato in enumerate(atos):
        descricao = str(_atributo(ato, "descricao", "") or "")
        eventos.append({
            "ordem": ordem,
            "codigo": str(_atributo(ato, "codigo", "") or ""),
            "tipo": _tipo_evento(ato),
            "categoria": str(_atributo(ato, "categoria", "") or ""),
            "tipo_onus": _atributo(ato, "tipo_onus"),
            "status": str(_atributo(ato, "status", "ATIVO") or "ATIVO"),
            "cancelado_por": _atributo(ato, "cancelado_por"),
            "cancela_atos": list(_atributo(ato, "cancela_atos", []) or []),
            # O texto não é persistido nem devolvido. O hash permite comparar
            # o evento sem duplicar conteúdo registral sensível.
            "origem_hash": sha256(descricao.encode("utf-8")).hexdigest(),
        })
    return eventos


def derivar_efeitos(eventos: list[dict]) -> list[dict]:
    efeitos = []
    for evento in eventos:
        tipo = evento["tipo"]
        if tipo == "CONSTITUICAO_GRAVAME":
            acao = "MANTER_ATIVO" if evento["status"] == "ATIVO" else "MANTER_CANCELADO"
            dominio = "ONUS"
        elif tipo == "CANCELAMENTO":
            acao, dominio = "CANCELAR_REFERENCIAS", "ONUS"
        elif tipo == "TRANSMISSAO":
            acao, dominio = "RECALCULAR_TITULARIDADE", "CADEIA"
        elif tipo in {"ATUALIZACAO_IMOVEL", "SITUACAO_MATRICULA"}:
            acao, dominio = "ATUALIZAR_ESTADO", "IMOVEL"
        else:
            acao, dominio = "SEM_EFEITO_ESTADO_ATUAL", "INFORMATIVO"
        efeitos.append({
            "codigo": evento["codigo"],
            "dominio": dominio,
            "acao": acao,
            "referencias": evento["cancela_atos"],
        })
    return efeitos


def _percentual(valor: object) -> float | None:
    encontrado = re.search(r"(-?\d+(?:[.,]\d+)?)\s*%", str(valor or ""))
    if not encontrado:
        return None
    try:
        return float(encontrado.group(1).replace(",", "."))
    except ValueError:
        return None


def diagnosticar_coerencia(
    eventos: list[dict], proprietarios: list[dict], imovel: dict,
) -> list[dict]:
    alertas = []
    codigos = [evento["codigo"] for evento in eventos if evento["codigo"]]
    duplicados = sorted({codigo for codigo in codigos if codigos.count(codigo) > 1})
    if duplicados:
        alertas.append({"regra": "EVENTO_CODIGO_DUPLICADO", "itens": duplicados})

    codigos_existentes = set(codigos)
    for evento in eventos:
        if evento["tipo"] != "CANCELAMENTO":
            continue
        referencias = set(evento["cancela_atos"])
        faltantes = sorted(referencias - codigos_existentes)
        if faltantes:
            alertas.append({
                "regra": "CANCELAMENTO_ORIGEM_NAO_LOCALIZADA",
                "ato": evento["codigo"],
                "itens": faltantes,
            })

    percentuais = [_percentual(item.get("proporcao")) for item in proprietarios]
    conhecidos = [valor for valor in percentuais if valor is not None]
    if proprietarios and len(conhecidos) == len(proprietarios):
        total = round(sum(conhecidos), 8)
        if abs(total - 100.0) > 0.000001:
            alertas.append({"regra": "TITULARIDADE_TOTAL_DIVERGENTE", "total": total})

    tipo = _normalizar(imovel.get("tipo"))
    cadastros = _normalizar(json.dumps(imovel.get("cadastros") or [], ensure_ascii=False))
    if tipo == "URBANO" and re.search(r"\b(?:CAR|CCIR|NIRF|CIB RURAL)\b", cadastros):
        alertas.append({"regra": "CADASTRO_RURAL_EM_IMOVEL_URBANO"})
    return alertas


def executar_pipeline_paralelo(
    atos: list[object], proprietarios: list[dict], imovel: dict,
) -> dict:
    eventos = normalizar_atos(atos)
    efeitos = derivar_efeitos(eventos)
    alertas = diagnosticar_coerencia(eventos, proprietarios, imovel)
    estrutura = {"eventos": eventos, "efeitos": efeitos, "alertas": alertas}
    digest = sha256(json.dumps(
        estrutura, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()
    return {
        "modo": "PARALELO",
        "versao": VERSAO_PIPELINE_EVENTOS,
        "eventos": len(eventos),
        "efeitos": len(efeitos),
        "alertas": alertas,
        "hash": digest,
        "altera_resultado_oficial": False,
    }
