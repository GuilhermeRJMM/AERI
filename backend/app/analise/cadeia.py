from backend.app.analise.evidencias import codigo_ato, descricao_ato, normalizar, trecho_evidencia
from backend.app.proprietarios import calcular_cadeia_dominial


def _localizar_origem(nome: str, texto: str, atos: list) -> tuple[str, str]:
    nome_normalizado = normalizar(nome)
    for ato in reversed(atos):
        descricao = descricao_ato(ato)
        if nome_normalizado and nome_normalizado in normalizar(descricao):
            return codigo_ato(ato), trecho_evidencia(descricao, nome)
    cabecalho = texto.split("----------------------------------------------------------------------------", 1)[0]
    if nome_normalizado and nome_normalizado in normalizar(cabecalho):
        return "Cabeçalho", trecho_evidencia(cabecalho, nome)
    return "Cadeia dominial", "Origem calculada pela aplicação cronológica dos atos registrais."


def calcular_cadeia(atos: list, texto: str) -> list[dict]:
    return calcular_cadeia_dominial(atos, texto)


def evidencias_cadeia(proprietarios: list[dict], atos: list, texto: str) -> list[dict]:
    retorno = []
    for indice, proprietario in enumerate(proprietarios):
        origem, trecho = _localizar_origem(proprietario.get("nome", ""), texto, atos)
        retorno.append({
            "indice": indice,
            "regra_id": "CADEIA-ESTADO-CRONOLOGICO-001",
            "fonte": origem,
            "trecho": trecho,
        })
    return retorno
