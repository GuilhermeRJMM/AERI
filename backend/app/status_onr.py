import hashlib
import hmac
import json
import re
import unicodedata
from datetime import datetime, timezone


STATUS_VALIDOS = {
    "OPERATIONAL", "UNDERMAINTENANCE", "DEGRADEDPERFORMANCE",
    "PARTIALOUTAGE", "MAJOROUTAGE", "UNKNOWN",
}

PESO_STATUS = {
    "UNKNOWN": 0,
    "OPERATIONAL": 1,
    "UNDERMAINTENANCE": 2,
    "DEGRADEDPERFORMANCE": 3,
    "PARTIALOUTAGE": 4,
    "MAJOROUTAGE": 5,
}


def normalizar_texto(texto: str) -> str:
    texto = unicodedata.normalize("NFD", str(texto or "").upper())
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", texto).strip()


def componente_oficio(nome: str) -> bool:
    normalizado = normalizar_texto(nome)
    return "OFICIO ELETRONICO" in normalizado


def componentes_oficio_api(dados) -> list[dict]:
    itens = dados.get("components", []) if isinstance(dados, dict) else dados
    encontrados = []

    def percorrer(componentes):
        for item in componentes or []:
            if componente_oficio(item.get("name", "")):
                encontrados.append(item)
            percorrer(item.get("children"))

    percorrer(itens)
    return encontrados


def status_seguro(status: str) -> str:
    normalizado = normalizar_texto(status).replace(" ", "")
    aliases = {
        "UP": "OPERATIONAL",
        "HASISSUES": "DEGRADEDPERFORMANCE",
        "MAJOR": "MAJOROUTAGE",
        "CRITICAL": "MAJOROUTAGE",
        "MINOR": "DEGRADEDPERFORMANCE",
        "NONE": "OPERATIONAL",
    }
    normalizado = aliases.get(normalizado, normalizado)
    return normalizado if normalizado in STATUS_VALIDOS else "UNKNOWN"


def pior_status(statuses) -> str:
    valores = [status_seguro(status) for status in statuses]
    return max(valores, key=lambda status: PESO_STATUS[status], default="UNKNOWN")


def serializar_payload(payload: dict) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def assinatura_valida(payload: dict, corpo: bytes, assinatura: str, segredo: str) -> bool:
    assinatura = str(assinatura or "").strip().lower()
    if not segredo or not re.fullmatch(r"[0-9a-f]{64}", assinatura):
        return False
    candidatos = {corpo, serializar_payload(payload)}
    return any(
        hmac.compare_digest(hmac.new(segredo.encode(), candidato, hashlib.sha256).hexdigest(), assinatura)
        for candidato in candidatos
    )


def data_iso(valor) -> str | None:
    if not valor:
        return None
    texto = str(valor).strip()
    try:
        return datetime.fromisoformat(texto.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat()
    except ValueError:
        return None


def interpretar_webhook(payload: dict) -> dict:
    pagina = payload.get("page") or {}
    if payload.get("component_update") or payload.get("component"):
        componente = payload.get("component") or {}
        atualizacao = payload.get("component_update") or {}
        nome = str(componente.get("name") or "Ofício Eletrônico")[:180]
        return {
            "tipo": "COMPONENTE",
            "chave": str(componente.get("id") or atualizacao.get("component_id") or "oficio-eletronico")[:120],
            "nome": nome,
            "status": status_seguro(atualizacao.get("new_status") or componente.get("status")),
            "referencia": str(atualizacao.get("component_id") or componente.get("id") or "")[:120],
            "resumo": f"{nome}: {status_seguro(atualizacao.get('new_status') or componente.get('status'))}"[:300],
            "atualizado_em": data_iso(atualizacao.get("created_at") or componente.get("updated_at")),
            "detalhes": {"pagina": pagina.get("url")},
        }

    item = payload.get("incident") or payload.get("maintenance") or {}
    tipo = "INCIDENTE" if payload.get("incident") else "MANUTENCAO"
    status_item = normalizar_texto(item.get("status")).replace(" ", "")
    resolvido = status_item in {"RESOLVED", "COMPLETED"}
    status = "OPERATIONAL" if resolvido else status_seguro(item.get("impact"))
    if status == "UNKNOWN" and not resolvido:
        status = status_seguro(pagina.get("status_indicator"))
    atualizacoes = item.get("incident_updates") or item.get("maintenance_updates") or []
    mensagem = str((atualizacoes[-1] if atualizacoes else {}).get("body") or item.get("name") or "")[:300]
    return {
        "tipo": tipo,
        "chave": f"{tipo.lower()}:{str(item.get('id') or 'atual')[:100]}",
        "nome": str(item.get("name") or "Ofício Eletrônico")[:180],
        "status": status,
        "referencia": str(item.get("id") or "")[:120],
        "resumo": mensagem,
        "atualizado_em": data_iso(item.get("updated_at") or item.get("created_at")),
        "detalhes": {"url": item.get("url"), "situacao": status_item, "mensagem": mensagem},
    }
