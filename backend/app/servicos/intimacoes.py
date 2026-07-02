import re
from datetime import date

from fastapi import HTTPException


def intimacao_json(registro: dict) -> dict:
    return {
        "id": str(registro["id"]),
        "protocolo": registro["protocolo"],
        "credor": registro["credor"],
        "devedor": registro["devedor"],
        "nomeAndamento": registro["nome_andamento"],
        "ultimoAndamento": registro["ultimo_andamento"].isoformat(),
        "ultimaConferencia": (
            registro["ultima_conferencia"].isoformat()
            if registro["ultima_conferencia"]
            else None
        ),
        "historico": registro["historico"] or [],
    }


def validar_intimacao(dados: dict) -> tuple[str, str, str, str, date]:
    protocolo = str(dados.get("protocolo", "")).strip().upper()
    credor = str(dados.get("credor", "")).strip()
    devedor = str(dados.get("devedor", "")).strip()
    nome_andamento = str(dados.get("nomeAndamento", "Não informado")).strip()
    try:
        andamento = date.fromisoformat(str(dados.get("ultimoAndamento", "")))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Data do último andamento inválida.") from exc
    if not re.fullmatch(r"IN\d{8}C", protocolo):
        raise HTTPException(status_code=422, detail="Use o protocolo no padrão IN01625306C.")
    if not credor or not devedor or len(credor) > 160 or len(devedor) > 160:
        raise HTTPException(status_code=422, detail="Informe credor e devedor válidos.")
    if not nome_andamento or len(nome_andamento) > 160:
        raise HTTPException(status_code=422, detail="Informe o nome do último andamento.")
    return protocolo, credor, devedor, nome_andamento, andamento


def validar_novo_andamento(dados: dict | None) -> str | None:
    if not dados or "nomeAndamento" not in dados:
        return None
    nome_andamento = str(dados["nomeAndamento"]).strip()
    if not nome_andamento or len(nome_andamento) > 160:
        raise HTTPException(status_code=422, detail="Informe um novo andamento válido.")
    return nome_andamento
