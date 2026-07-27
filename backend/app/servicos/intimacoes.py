import re
import unicodedata
from datetime import date

from fastapi import HTTPException


FASE_INICIAL = "INTIMACAO"
FASE_EDITAL = "EDITAL"
FASE_CONSOLIDACAO = "CONSOLIDACAO"
FASES_INTIMACAO = {FASE_INICIAL, FASE_EDITAL, FASE_CONSOLIDACAO}


def _texto_normalizado(valor: str) -> str:
    texto = unicodedata.normalize("NFD", str(valor or ""))
    return "".join(caractere for caractere in texto if unicodedata.category(caractere) != "Mn").lower()


def validar_fase(valor: object, *, obrigatoria: bool = False) -> str | None:
    fase = str(valor or "").strip().upper()
    if not fase and not obrigatoria:
        return None
    if fase not in FASES_INTIMACAO:
        raise HTTPException(status_code=422, detail="Selecione uma fase válida para a intimação.")
    return fase


def fase_por_andamento(nome_andamento: str, fase_atual: str | None = None) -> str:
    """Avança a fase quando o andamento identifica inequivocamente a próxima etapa."""
    texto = _texto_normalizado(nome_andamento)
    atual = validar_fase(fase_atual) or FASE_INICIAL

    if "consolida" in texto or "intimacao positiva" in texto:
        return FASE_CONSOLIDACAO
    if "edital" in texto and atual != FASE_CONSOLIDACAO:
        return FASE_EDITAL
    return atual


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
        "fase": registro.get("fase"),
    }


def validar_intimacao(dados: dict) -> tuple[str, str, str, str, date, str]:
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
    fase_informada = validar_fase(dados.get("fase")) or FASE_INICIAL
    fase = fase_por_andamento(nome_andamento, fase_informada)
    return protocolo, credor, devedor, nome_andamento, andamento, fase


def validar_novo_andamento(dados: dict | None) -> str | None:
    if not dados or "nomeAndamento" not in dados:
        return None
    nome_andamento = str(dados["nomeAndamento"]).strip()
    if not nome_andamento or len(nome_andamento) > 160:
        raise HTTPException(status_code=422, detail="Informe um novo andamento válido.")
    return nome_andamento
