from backend.app.analise.evidencias import codigo_ato, descricao_ato, normalizar, trecho_evidencia
from backend.app.proprietarios import calcular_cadeia_dominial
from backend.app.analise.rastro_cadeia import historico_proprietario
from backend.app.parser import separar_atos


def _localizar_origem(nome: str, texto: str, atos: list) -> tuple[str, str]:
    nome_normalizado = normalizar(nome)
    # Sem rastro de cálculo, não atribuir aquisição pela última menção nominal.
    separados = separar_atos(texto)
    inicio = texto.find(separados[0]["texto"]) if separados else -1
    cabecalho = texto[:inicio] if inicio >= 0 else texto if not separados else ""
    if nome_normalizado and nome_normalizado in normalizar(cabecalho):
        return "Cabeçalho", trecho_evidencia(cabecalho, nome)
    return "Cadeia dominial", "Origem calculada pela aplicação cronológica dos atos registrais."


def calcular_cadeia(atos: list, texto: str, *, rastro=None) -> list[dict]:
    return calcular_cadeia_dominial(atos, texto, rastro=rastro)


def evidencias_cadeia(proprietarios: list[dict], atos: list, texto: str, *, rastro=None) -> list[dict]:
    retorno = []
    for indice, proprietario in enumerate(proprietarios):
        origem, trecho = _localizar_origem(proprietario.get("nome", ""), texto, atos)
        historico = historico_proprietario(proprietario, rastro)
        aquisicoes = [evento for evento in historico if evento["variacao_percentual"] > 0 and evento["acao"] in {
            "ABERTURA", "TRANSMISSAO", "PARTILHA", "CONSOLIDACAO", "CONSTITUICAO_SOCIEDADE", "RESTABELECIMENTO",
        }]
        declaracoes = [evento for evento in historico if evento["acao"] == "DECLARACAO_TITULARIDADE"]
        fontes = aquisicoes or declaracoes
        if fontes:
            from backend.app.analise.evidencias import evidencia_por_origem
            origem = fontes[-1]["ato"]
            evidencia = evidencia_por_origem(texto, atos, origem, fontes[-1]["nome_no_ato"])
            trecho = evidencia["trecho"]
        retorno.append({
            "indice": indice,
            "regra_id": "CADEIA-ESTADO-CRONOLOGICO-001",
            "fonte": origem,
            "trecho": trecho,
            "historico": historico,
            "atos_aquisicao": list(dict.fromkeys(codigo for evento in aquisicoes for codigo in evento["atos"])),
        })
    return retorno
