import re
import unicodedata

from backend.app.cancelamentos import aplicar_cancelamentos
from backend.app.modelos import Ato
from backend.app.parser import separar_atos
from backend.app.regras import (
    classificar,
    extrair_grau_hipoteca,
    formatar_grau_onus,
    identificar_tipo_onus,
)
from backend.app.servicos.aprendizado_regras import identificar_tipo_onus_aprendido


CATEGORIAS_RETORNO = ["ÔNUS", "RESTRIÇÃO", "PUBLICIDADE", "CANCELAMENTO"]


def _normalizar(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii").upper()


def _protocolo_ato(texto: str) -> str:
    encontrado = re.search(r"\bPROTOCOLO\s+N[^0-9]{0,8}([\d.]+)", _normalizar(texto)[:500])
    return re.sub(r"\D", "", encontrado.group(1)) if encontrado else ""


def ato_transmissao_repete_onus_seguinte(descricao: str, descricao_seguinte: str) -> bool:
    """Detecta venda que apenas cita a garantia registrada no ato seguinte."""
    atual = _normalizar(descricao)
    seguinte = _normalizar(descricao_seguinte)
    protocolo = _protocolo_ato(descricao)
    if not protocolo or protocolo != _protocolo_ato(descricao_seguinte):
        return False
    return bool(
        re.search(r"\b(?:VENDA\s+E\s+COMPRA|COMPRA\s+E\s+VENDA)\b", atual[:420])
        and "ALIENACAO FIDUCIARIA" in atual
        and "ALIENACAO FIDUCIARIA" in seguinte[:420]
    )


def ato_cadastral_apenas_cita_onus(descricao: str, tipo_onus: str | None) -> bool:
    """Evita que a origem documental de um ato cadastral seja tratada como gravame."""
    texto = _normalizar(descricao)
    cadastro = re.search(
        r"\b(?:ATUALIZACAO\s+(?:DE|DA)\s+)?DESIGNACAO\s+CADASTRAL"
        r"(?:\s+DO\s+IMOVEL)?\b",
        texto[:420],
    )
    if not cadastro:
        return False

    # Se o próprio título constitutivo do ônus vier antes da referência cadastral,
    # trata-se de um gravame verdadeiro que apenas menciona dados do imóvel.
    onus = _normalizar(tipo_onus or "").strip()
    posicao_onus = texto.find(onus) if onus else -1
    return posicao_onus < 0 or cadastro.start() < posicao_onus


def _remover_onus_duplicado_da_transmissao(atos: list[Ato]) -> None:
    for indice, ato in enumerate(atos[:-1]):
        seguinte = atos[indice + 1]
        if (
            ato.categoria == "ÔNUS"
            and ato.tipo_onus == "ALIENAÇÃO FIDUCIÁRIA"
            and seguinte.categoria == "ÔNUS"
            and seguinte.tipo_onus == "ALIENAÇÃO FIDUCIÁRIA"
            and ato_transmissao_repete_onus_seguinte(ato.descricao, seguinte.descricao)
        ):
            ato.categoria = "IGNORAR"
            ato.tipo_onus = None
            ato.impacta_resultado = False


def atualizar_grau_hipotecas(atos):
    graus_cancelados = []
    for ato in atos:
        if ato.tipo_onus != "HIPOTECA":
            continue
        grau_declarado = extrair_grau_hipoteca(ato.descricao)
        if ato.status == "CANCELADO":
            ato.grau_onus = None
            if grau_declarado:
                graus_cancelados.append(grau_declarado)
            continue
        if grau_declarado:
            rebaixamentos = len({grau for grau in graus_cancelados if grau < grau_declarado})
            ato.grau_onus = formatar_grau_onus(max(1, grau_declarado - rebaixamentos))


def processar_atos(texto: str, regras_aprendidas: list[dict] | None = None) -> list[Ato]:
    atos = []
    for item in separar_atos(texto):
        categoria, impacta = classificar(item["texto"], regras_aprendidas=regras_aprendidas)
        tipo_onus = None
        if categoria == "ÔNUS":
            tipo_onus = identificar_tipo_onus(item["texto"]) or identificar_tipo_onus_aprendido(
                item["texto"], regras_aprendidas
            )
            if ato_cadastral_apenas_cita_onus(item["texto"], tipo_onus):
                categoria = "IGNORAR"
                impacta = False
                tipo_onus = None
        atos.append(
            Ato(
                codigo=item["codigo"],
                descricao=item["texto"],
                categoria=categoria,
                tipo_onus=tipo_onus,
                grau_onus=None,
                impacta_resultado=impacta,
            )
        )
    _remover_onus_duplicado_da_transmissao(atos)
    atos = aplicar_cancelamentos(atos)
    atualizar_grau_hipotecas(atos)
    return atos


def resumir_resultado_onus(atos: list[Ato]) -> tuple[str, str]:
    tem_onus = any(ato.categoria == "ÔNUS" and ato.status == "ATIVO" for ato in atos)
    tem_publicidade = any(ato.categoria == "PUBLICIDADE" and ato.status == "ATIVO" for ato in atos)
    if tem_onus:
        resultado = "POSITIVA PARA ÔNUS"
    elif tem_publicidade:
        resultado = "NEGATIVA, PORÉM COM PUBLICIDADE"
    else:
        resultado = "NEGATIVA PARA ÔNUS"
    return resultado, "COM PUBLICIDADE" if tem_publicidade else "SEM PUBLICIDADE"


def serializar_atos(atos: list[Ato]) -> list[dict]:
    return [
        ato.model_dump() if hasattr(ato, "model_dump") else ato.dict()
        for ato in atos
        if ato.categoria in CATEGORIAS_RETORNO
    ]


def evidencias_atos(atos: list[Ato]) -> list[dict]:
    retorno = []
    for ato in atos:
        if ato.categoria not in CATEGORIAS_RETORNO:
            continue
        tipo = ato.tipo_onus or ato.categoria
        retorno.append({
            "codigo": ato.codigo,
            "regra_id": f"ONUS-{str(tipo).upper().replace(' ', '-')}-001",
            "fonte": ato.codigo,
            "trecho": ato.descricao[:420],
        })
    return retorno
