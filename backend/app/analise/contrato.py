from copy import deepcopy
from hashlib import sha256
import json


NOME_MOTOR = "AERI Registral"
VERSAO_MOTOR = "2.0.0"
MODO_MOTOR = "DETERMINÍSTICO"
NAO_CONSTA = "NÃO CONSTA"


def metadados_analise() -> dict:
    return {
        "motor": NOME_MOTOR,
        "versao": VERSAO_MOTOR,
        "modo": MODO_MOTOR,
        "texto_persistido": False,
    }


def finalizar_contrato(resultado: dict, evidencias: dict | None = None) -> dict:
    """Entrega um contrato novo sem permitir mutação acidental do pipeline."""
    retorno = deepcopy(resultado)
    retorno["meta"] = metadados_analise()
    retorno["evidencias"] = deepcopy(evidencias or {})
    conteudo_assinado = {
        "resultado": retorno.get("resultado"),
        "publicidade": retorno.get("publicidade"),
        "atos": retorno.get("atos", []),
        "proprietarios_atuais": retorno.get("proprietarios_atuais", []),
        "imovel": retorno.get("imovel", {}),
        "motor": retorno["meta"],
    }
    serializado = json.dumps(
        conteudo_assinado,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    retorno["resultado_hash"] = sha256(serializado).hexdigest()
    return retorno
