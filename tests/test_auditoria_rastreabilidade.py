"""Evidências rastreáveis e cobertura independente, sem consultas externas."""
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from backend.app.analise.cadeia import evidencias_cadeia
from backend.app.analise.contrato import ARQUIVOS_REGRAS, versao_indice_motor
from backend.app.analise.cobertura_atos import conferir_cobertura_texto, comparar_atos_tri7
from backend.app.analise.evidencias import trecho_por_padroes
from backend.app.analise.onus import processar_atos, evidencias_atos
from backend.app.analise.rastro_cadeia import ObservadorCadeia, historico_proprietario
from backend.app.modelos import Ato
from backend.app.proprietarios import calcular_cadeia_dominial
from backend.app.rotas.analisador import _conferir_atos_na_tri7, analisar_por_numero
from backend.app.servicos.analise_matricula import analisar_matricula
from backend.app.servicos.tri7 import ErroTri7


TEXTO = """MATRÍCULA 100. IMÓVEL: Lote urbano. PROPRIETÁRIO: João da Silva, CPF 123.456.789-01.
R.01-100 - VENDA E COMPRA. TRANSMITENTE: João da Silva, CPF 123.456.789-01.
ADQUIRENTE: Maria de Souza, CPF 987.654.321-00. IMÓVEL: A totalidade. DOU FÉ."""
CADASTRO = "\nAV.02-100 - ALTERAÇÃO DE CEP. A proprietária Maria de Souza atualiza o endereço do imóvel. DOU FÉ."


def test_origem_nao_e_ultima_mencao_em_averbacao_cadastral():
    resultado = analisar_matricula(TEXTO + CADASTRO)
    evidencia = resultado["evidencias"]["proprietarios"][0]
    assert evidencia["fonte"] == "R.01"
    assert evidencia["atos_aquisicao"] == ["R.01"]
    assert "ADQUIRENTE: Maria de Souza" in evidencia["trecho"]
    assert not any(e["ato"] == "AV.02" for e in evidencia["historico"])


def test_sem_rastro_nao_fabrica_origem_pela_ultima_mencao():
    evidencia = evidencias_cadeia([{"nome": "Maria de Souza"}],
        [Ato(codigo="AV.02", descricao="Cadastro de Maria de Souza")], "MATRÍCULA 100.")[0]
    assert evidencia["fonte"] == "Cadeia dominial"


def test_cabecalho_nao_inclui_ato_de_aquisicao_posterior():
    evidencia = evidencias_cadeia([{"nome": "Maria de Souza"}], processar_atos(TEXTO), TEXTO)[0]
    assert evidencia["fonte"] != "Cabeçalho"


def test_rastro_nao_altera_proprietarios_dos_casos_conferidos():
    casos = json.loads((Path(__file__).parent / "corpus_ouro/manifest.json").read_text(encoding="utf-8"))
    for caso in casos:
        atos = processar_atos(caso["texto"])
        anterior = calcular_cadeia_dominial(atos, caso["texto"])
        rastro = []
        atual = calcular_cadeia_dominial(atos, caso["texto"], rastro=rastro)
        assert atual == anterior, caso["id"]


def _pessoa(nome="MARIA", cpf="12345678901", proporcao=100):
    return {"nome": nome, "cpf_original": cpf, "proporcao": proporcao}


def test_historico_reune_aquisicoes_parciais_e_venda_sem_trocar_origem():
    estado, rastro = {}, []
    observador = ObservadorCadeia(estado, rastro)
    observador.iniciar("R.1", "TRANSMISSAO")
    estado["p"] = _pessoa(proporcao=50)
    observador.iniciar("R.2", "TRANSMISSAO")
    estado["p"]["proporcao"] += 25
    observador.iniciar("R.3", "TRANSMISSAO")
    estado["p"]["proporcao"] -= 10
    observador.concluir()
    historico = historico_proprietario({"nome": "MARIA", "cpf": "12345678901"}, rastro)
    assert [e["variacao_percentual"] for e in historico] == [50, 25, -10]
    assert estado["p"]["proporcao"] == 65
    atos = [Ato(codigo=f"R.{i}", descricao="Aquisição de MARIA") for i in range(1, 4)]
    evidencia = evidencias_cadeia([{"nome": "MARIA", "cpf": "12345678901"}], atos, "", rastro=rastro)[0]
    assert evidencia["fonte"] == "R.2"
    assert evidencia["atos_aquisicao"] == ["R.1", "R.2"]


def test_retificacoes_de_cpf_e_nome_preservam_vinculo_com_aquisicao():
    estado, rastro = {}, []
    observador = ObservadorCadeia(estado, rastro)
    observador.iniciar("R.1", "TRANSMISSAO")
    estado["p"] = _pessoa(nome="MARIA ANTIGA")
    observador.iniciar("AV.2", "RETIFICACAO")
    estado["p"]["cpf_original"] = "98765432100"
    observador.iniciar("AV.3", "RETIFICACAO")
    estado["p"]["nome"] = "MARIA NOVA"
    observador.concluir()
    historico = historico_proprietario({"nome": "MARIA NOVA", "cpf": "98765432100"}, rastro)
    assert [e["ato"] for e in historico] == ["R.1", "AV.2", "AV.3"]
    assert historico[0]["nome_no_ato"] == "MARIA ANTIGA"
    assert "cpf" not in json.dumps(historico)


def test_partilha_agrupada_aponta_atos_de_cada_adquirente():
    estado, rastro = {}, []
    observador = ObservadorCadeia(estado, rastro)
    observador.iniciar("R.1", "PARTILHA")
    observador.efeito("PARTILHA", [("R.1", [{"nome": "MARIA", "cpf": "12345678901"}]),
                                  ("R.2", [{"nome": "ANA", "cpf": "98765432100"}])])
    estado["m"] = _pessoa(proporcao=50)
    estado["a"] = _pessoa(nome="ANA", cpf="98765432100", proporcao=50)
    observador.concluir()
    assert historico_proprietario({"nome": "ANA", "cpf": "98765432100"}, rastro)[0]["atos"] == ["R.2"]


def test_reaquisicao_nao_herda_origem_de_dominio_ja_vendido():
    estado, rastro = {}, []
    observador = ObservadorCadeia(estado, rastro)
    observador.iniciar("R.1", "TRANSMISSAO")
    estado["p"] = _pessoa()
    observador.iniciar("R.2", "TRANSMISSAO")
    estado.clear()
    observador.iniciar("R.3", "TRANSMISSAO")
    estado["p"] = _pessoa()
    observador.concluir()
    historico = historico_proprietario({"nome": "MARIA", "cpf": "12345678901"}, rastro)
    assert [e["ato"] for e in historico] == ["R.3"]


def test_renormalizacao_territorial_nao_e_nova_aquisicao():
    estado, rastro = {}, []
    observador = ObservadorCadeia(estado, rastro)
    observador.iniciar("Cabeçalho", "ABERTURA")
    estado["p"] = _pessoa(proporcao=50)
    observador.iniciar("AV.2", "ALTERACAO_TERRITORIAL")
    estado["p"]["proporcao"] = 100
    observador.concluir()
    evidencia = evidencias_cadeia([{"nome": "MARIA", "cpf": "12345678901"}], [],
                                 "PROPRIETÁRIA: MARIA.", rastro=rastro)[0]
    assert evidencia["atos_aquisicao"] == ["Cabeçalho"]


def test_onus_e_cancelamento_tem_trecho_decisivo_apos_420_caracteres():
    inicio = "Qualificação e descrição do imóvel. " * 30
    atos = [
        Ato(codigo="R.01", descricao=inicio+"Constitui hipoteca sobre o imóvel.", categoria="ÔNUS",
            tipo_onus="HIPOTECA", status="CANCELADO", cancelado_por="AV.2"),
        Ato(codigo="AV.02", descricao=inicio+"Fica cancelada a hipoteca do R.01 por quitação.",
            categoria="CANCELAMENTO", cancela_atos=["R.01"]),
    ]
    evidencias = evidencias_atos(atos)
    assert "Constitui hipoteca" in evidencias[0]["trecho"]
    assert "Fica cancelada" in evidencias[0]["cancelamento"]["trecho"]
    assert evidencias[1]["atos_cancelados"] == ["R.01"]
    assert [a.status for a in atos] == ["CANCELADO", "ATIVO"]


def test_trecho_preserva_offsets_do_texto_original():
    texto = "ß Á " * 250 + "Fica cancelada a hipoteca."
    assert "Fica cancelada a hipoteca" in trecho_por_padroes(texto, [r"FICA CANCELADA"])


def test_assinatura_inclui_modulos_que_mudam_interpretacao():
    for arquivo in ("analise/onus.py", "analise/cadeia.py", "analise/evidencias.py",
                    "analise/rastro_cadeia.py", "analise/cobertura_atos.py", "servicos/analise_matricula.py"):
        assert arquivo in ARQUIVOS_REGRAS
    assert len(versao_indice_motor()) <= 30


def test_cobertura_independente_detecta_cabecalho_que_parser_descartou():
    texto = "R.01-100 - VENDA.\nAV.01-100 - CANCELAMENTO."
    atos = processar_atos(texto)
    cobertura = conferir_cobertura_texto(texto, atos)
    assert cobertura["nao_segmentados"] == ["AV.1"]
    assert not cobertura["altera_resultado_oficial"]


def test_cobertura_nao_inventa_atos_por_lacuna_numerica():
    texto = "R.05-100 - HIPOTECA. Referência ao R.01 de outra matrícula."
    cobertura = conferir_cobertura_texto(texto, processar_atos(texto))
    assert cobertura["estado"] == "CONFERIDA"
    assert cobertura["codigos_texto"] == ["R.5"]


def _resposta_atos(*codigos):
    return {"numero_matricula": "100", "atos": [{"ato": c, "status": "Registrado"} for c in codigos]}


@pytest.mark.parametrize("resposta", [None, {}, {"atos": [None]}, {"atos": [{"status": "Registrado", "ato": "???"}]}])
def test_resposta_invalida_nao_e_apresentada_como_conferencia(resposta):
    cobertura = conferir_cobertura_texto(TEXTO, processar_atos(TEXTO))
    assert comparar_atos_tri7(cobertura, resposta)["tri7"]["estado"] == "RESPOSTA_INVALIDA"


def test_recupera_texto_quando_api_de_atos_esta_mais_atualizada():
    cliente = MagicMock()
    cliente.buscar_atos_matricula.return_value = _resposta_atos("R.1", "Av.2")
    cliente.buscar_texto_matricula.return_value = {"numero_matricula": "100", "texto": TEXTO+CADASTRO}
    matricula, resultado = _conferir_atos_na_tri7(cliente, {"numero_matricula": "100", "texto": TEXTO}, analisar_matricula(TEXTO), [])
    assert matricula["texto"] == TEXTO+CADASTRO
    assert resultado["meta"]["cobertura_atos"]["estado"] == "CONFERIDA"
    cliente.buscar_texto_matricula.assert_called_once_with("100")


def test_indisponibilidade_da_api_nao_apaga_resultado():
    cliente = MagicMock()
    cliente.buscar_atos_matricula.side_effect = ErroTri7("indisponível")
    anterior = analisar_matricula(TEXTO)
    _, resultado = _conferir_atos_na_tri7(cliente, {"numero_matricula": "100", "texto": TEXTO}, anterior, [])
    assert resultado["proprietarios_atuais"] == anterior["proprietarios_atuais"]
    assert resultado["meta"]["cobertura_atos"]["tri7"]["estado"] == "INDISPONIVEL"
    cliente.buscar_texto_matricula.assert_not_called()


def test_divergencia_persistente_nao_vira_negativa_bloqueada_nem_ato_inventado():
    cliente = MagicMock()
    cliente.buscar_texto_matricula.return_value = {"numero_matricula": "100", "texto": TEXTO}
    cliente.buscar_atos_matricula.return_value = _resposta_atos("R.1", "Av.2")
    with patch("backend.app.rotas.analisador.cliente_tri7", return_value=cliente), \
         patch("backend.app.rotas.analisador._regras_aprovadas", return_value=[]), \
         patch("backend.app.rotas.analisador.registrar_auditoria"), \
         patch("backend.app.rotas.analisador._executar_agente_na_matricula", return_value={"estado": "CONCLUIDA", "parecer": {"analises": []}}):
        resultado = analisar_por_numero({"numero_matricula": "100"}, MagicMock(), "teste")
    assert resultado["resultado"] == "NEGATIVA PARA ÔNUS"
    assert resultado["controle_qualidade"]["estado"] == "REVISAR"
    assert resultado["meta"]["cobertura_atos"]["tri7"]["faltantes_no_texto"] == ["AV.2"]
    assert cliente.buscar_texto_matricula.call_count == 2
    assert not any(a["codigo"] == "AV.02" for a in resultado["atos"])
