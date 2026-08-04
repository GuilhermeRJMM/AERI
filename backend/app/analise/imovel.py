from backend.app.analise.contrato import NAO_CONSTA
from backend.app.analise.evidencias import evidencia_por_origem
from backend.app.servicos.dados_imovel import extrair_dados_imovel


CAMPOS = {
    "URBANO": {
        "identificacao": ["Matrícula", "Lote", "Quadra", "Rua", "Número", "Setor"],
        "confrontacoes": ["Frente", "Lado direito", "Lado esquerdo", "Fundos"],
        "areas": ["Área", "Área Construída"],
        "cadastros": ["Cadastro municipal / CCI", "CEP"],
    },
    "RURAL": {
        "identificacao": ["Matrícula", "Nome"],
        "confrontacoes": ["Frente", "Lado direito", "Lado esquerdo", "Fundos"],
        "areas": ["Área", "Área Construída", "Área no CCIR", "Área declarada no CAR"],
        "cadastros": ["CCIR / Código rural", "INCRA", "CAR", "Coordenadas do CAR"],
    },
}


def _normalizar_rotulo(rotulo: str) -> str:
    aliases = {
        "CCI": "Cadastro municipal / CCI",
        "Cadastro municipal": "Cadastro municipal / CCI",
        "CCIR / código rural": "CCIR / Código rural",
        "Denominação": "Nome",
    }
    return aliases.get(rotulo, rotulo)


def _enriquecer_item(item: dict, texto: str, atos: list) -> dict:
    retorno = dict(item)
    retorno["rotulo"] = _normalizar_rotulo(str(retorno.get("rotulo", "")))
    origem = str(retorno.get("origem", ""))
    retorno["aplicabilidade"] = "APLICÁVEL"
    retorno["regra_id"] = "IMOVEL-" + retorno["rotulo"].upper().replace(" ", "-").replace("/", "-") + "-001"
    retorno["evidencia"] = evidencia_por_origem(texto, atos, origem, str(retorno.get("valor", "")))
    return retorno


def _campos_aplicaveis(imovel: dict, texto: str, atos: list) -> dict:
    tipo = imovel.get("tipo") if imovel.get("tipo") in CAMPOS else "URBANO"
    grupos = {}
    for grupo, rotulos in CAMPOS[tipo].items():
        existentes = [_enriquecer_item(item, texto, atos) for item in imovel.get(grupo, [])]
        por_rotulo = {}
        for item in existentes:
            por_rotulo.setdefault(item["rotulo"], []).append(item)
        completos = []
        for rotulo in rotulos:
            if por_rotulo.get(rotulo):
                completos.extend(por_rotulo.pop(rotulo))
            else:
                completos.append({
                    "rotulo": rotulo,
                    "valor": NAO_CONSTA,
                    "origem": "NÃO IDENTIFICADA",
                    "ausente": True,
                    "aplicabilidade": "APLICÁVEL",
                    "regra_id": "CAMPO-APLICAVEL-SEM-EVIDENCIA",
                    "evidencia": {"fonte": "NÃO IDENTIFICADA", "trecho": ""},
                })
        for sobras in por_rotulo.values():
            completos.extend(sobras)
        grupos[grupo] = completos
    grupos["restricoes"] = [_enriquecer_item(item, texto, atos) for item in imovel.get("restricoes", [])]
    grupos["divergencias"] = [_enriquecer_item(item, texto, atos) for item in imovel.get("divergencias", [])]
    return grupos


def extrair_imovel_com_evidencias(
    texto: str,
    atos: list,
    proprietarios: list[dict],
    numero_matricula: str | None = None,
) -> tuple[dict, dict]:
    imovel = extrair_dados_imovel(texto, atos, proprietarios, numero_matricula=numero_matricula)
    retorno = dict(imovel)
    retorno["campos_aplicaveis"] = _campos_aplicaveis(imovel, texto, atos)
    situacao = dict(imovel.get("situacao") or {})
    origem = str(situacao.get("origem", "Matrícula"))
    evidencias_campos = []
    for grupo, itens in retorno["campos_aplicaveis"].items():
        for indice, item in enumerate(itens):
            evidencias_campos.append({
                "grupo": grupo,
                "indice": indice,
                "rotulo": item["rotulo"],
                "regra_id": item["regra_id"],
                **item["evidencia"],
            })
    evidencias = {
        "situacao": {
            "regra_id": "IMOVEL-SITUACAO-001",
            **evidencia_por_origem(texto, atos, origem, situacao.get("status")),
        },
        "campos": evidencias_campos,
    }
    return retorno, evidencias
