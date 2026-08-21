from copy import deepcopy
from functools import lru_cache
from hashlib import sha256
import json
from pathlib import Path


NOME_MOTOR = "AERI Registral"
VERSAO_MOTOR = "2.1.0"
MODO_MOTOR = "DETERMINÍSTICO"
NAO_CONSTA = "NÃO CONSTA"

# Arquivos que efetivamente mudam a interpretação registral. O hash curto
# entra na versão persistida do índice: assim uma regra alterada deixa as
# matrículas antigas objetivamente identificáveis para reindexação, sem
# depender de alguém lembrar de trocar um número manualmente.
ARQUIVOS_REGRAS = (
    "parser.py",
    "regras.py",
    "cancelamentos.py",
    "proprietarios.py",
    "servicos/dados_imovel.py",
)


@lru_cache(maxsize=1)
def hash_regras() -> str:
    raiz = Path(__file__).resolve().parents[1]
    digest = sha256()
    for relativo in ARQUIVOS_REGRAS:
        caminho = raiz / relativo
        digest.update(relativo.encode("utf-8"))
        digest.update(caminho.read_bytes())
    return digest.hexdigest()


def versao_indice_motor() -> str:
    """Versão compacta que cabe na coluna histórica VARCHAR(30)."""
    return f"{VERSAO_MOTOR}+{hash_regras()[:12]}"


def metadados_analise() -> dict:
    return {
        "motor": NOME_MOTOR,
        "versao": VERSAO_MOTOR,
        "versao_indice": versao_indice_motor(),
        "regras_hash": hash_regras(),
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
