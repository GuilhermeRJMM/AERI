from backend.app.cancelamentos import aplicar_cancelamentos
from backend.app.modelos import Ato
from backend.app.parser import separar_atos
from backend.app.proprietarios import calcular_cadeia_dominial
from backend.app.regras import (
    classificar,
    extrair_grau_hipoteca,
    formatar_grau_onus,
    identificar_tipo_onus,
)
from backend.app.servicos.aprendizado_regras import identificar_tipo_onus_aprendido
from backend.app.servicos.dados_imovel import extrair_dados_imovel


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


def analisar_matricula(texto: str, regras_aprendidas: list[dict] | None = None) -> dict:
    atos = []
    for item in separar_atos(texto):
        categoria, impacta = classificar(item["texto"], regras_aprendidas=regras_aprendidas)
        tipo_onus = None
        if categoria == "ÔNUS":
            tipo_onus = identificar_tipo_onus(item["texto"]) or identificar_tipo_onus_aprendido(
                item["texto"],
                regras_aprendidas,
            )
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

    atos = aplicar_cancelamentos(atos)
    atualizar_grau_hipotecas(atos)
    tem_onus = any(ato.categoria == "ÔNUS" and ato.status == "ATIVO" for ato in atos)
    tem_publicidade = any(
        ato.categoria == "PUBLICIDADE" and ato.status == "ATIVO"
        for ato in atos
    )

    if tem_onus:
        resultado_final = "POSITIVA PARA ÔNUS"
    elif tem_publicidade:
        resultado_final = "NEGATIVA, PORÉM COM PUBLICIDADE"
    else:
        resultado_final = "NEGATIVA PARA ÔNUS"

    categorias_permitidas = ["ÔNUS", "RESTRIÇÃO", "PUBLICIDADE", "CANCELAMENTO"]
    atos_filtrados = [
        ato.model_dump() if hasattr(ato, "model_dump") else ato.dict()
        for ato in atos
        if ato.categoria in categorias_permitidas
    ]

    proprietarios_atuais = calcular_cadeia_dominial(atos, texto)

    return {
        "resultado": resultado_final,
        "publicidade": "COM PUBLICIDADE" if tem_publicidade else "SEM PUBLICIDADE",
        "atos": atos_filtrados,
        "proprietarios_atuais": proprietarios_atuais,
        "imovel": extrair_dados_imovel(texto, atos, proprietarios_atuais),
    }
