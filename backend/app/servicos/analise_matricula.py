from backend.app.analise.cadeia import calcular_cadeia, evidencias_cadeia
from backend.app.analise.contrato import finalizar_contrato
from backend.app.analise.imovel import extrair_imovel_com_evidencias
from backend.app.analise.onus import evidencias_atos, processar_atos, resumir_resultado_onus, serializar_atos
from backend.app.analise.pipeline_eventos import executar_pipeline_paralelo


def analisar_matricula(
    texto: str,
    regras_aprendidas: list[dict] | None = None,
    numero_matricula: str | None = None,
) -> dict:
    atos = processar_atos(texto, regras_aprendidas=regras_aprendidas)
    resultado_final, publicidade = resumir_resultado_onus(atos)
    proprietarios_atuais = calcular_cadeia(atos, texto)
    imovel, evidencias_imovel = extrair_imovel_com_evidencias(
        texto,
        atos,
        proprietarios_atuais,
        numero_matricula=numero_matricula,
    )

    retorno = finalizar_contrato({
        "resultado": resultado_final,
        "publicidade": publicidade,
        "atos": serializar_atos(atos),
        "proprietarios_atuais": proprietarios_atuais,
        "imovel": imovel,
    }, {
        "atos": evidencias_atos(atos),
        "proprietarios": evidencias_cadeia(proprietarios_atuais, atos, texto),
        "imovel": evidencias_imovel,
    })
    # O pipeline novo roda em sombra: mede e registra coerência estrutural,
    # mas não substitui nenhuma decisão já validada do motor oficial.
    retorno["meta"]["pipeline_paralelo"] = executar_pipeline_paralelo(
        atos, proprietarios_atuais, imovel,
    )
    return retorno
