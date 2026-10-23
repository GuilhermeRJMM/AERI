"""Regressões da atualização contínua, sem banco/API de produção."""
import threading
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from backend.app.rotas import registros_auxiliares as rotas_ra
from backend.app.servicos import buscas_movimentacoes as sinais
from backend.app.servicos import custas
from backend.app.servicos.buscas import hash_documento
from backend.app.servicos.fila_auxiliares import concluir_auxiliar
from backend.app.servicos.registros_auxiliares import extrair_indice_registro_auxiliar, registro_auxiliar_json
from backend.app.servicos.tri7 import ConfiguracaoTri7
from scripts import worker_operacional as worker


@pytest.fixture(autouse=True)
def chave_teste(monkeypatch):
    monkeypatch.setenv("AERI_BUSCAS_HMAC_KEY", "chave-exclusiva-dos-testes-nao-producao")


def pedido(**extra):
    return {"nome": "JOAO DA SILVA", "documento": "12345678901", "produto": "SOJA",
            "safra": "2026/2027", "modalidade": "PENHOR", **extra}


def registro(**extra):
    return {"numero": 29667, "pessoas": [{"nome": "JOAO DA SILVA", "documento": ""}],
            "nomes_busca": "JOAO DA SILVA", "documentos_hash": [], "produtos": ["SOJA"],
            "safras": ["2026/2027"], "modalidade": "PENHOR", "situacao": "ATIVO", **extra}


def conexao():
    con = MagicMock()
    con.__enter__.return_value = con
    return con, con.cursor.return_value.__enter__.return_value


def test_cpf_confirma_mesmo_com_nome_diferente():
    protegido = hash_documento(pedido()["documento"])
    assert custas._identidade_compativel(
        registro(pessoas=[{"nome": "OUTRO NOME"}], documentos_hash=[protegido]), pedido(), protegido)


def test_nome_igual_nao_anula_cpf_expressamente_divergente():
    protegido = hash_documento(pedido()["documento"])
    outro = hash_documento("98765432100")
    assert not custas._identidade_compativel(registro(pessoas=[{
        "nome": "JOAO DA SILVA", "documento_hash": outro,
    }], documentos_hash=[outro]), pedido(), protegido)


def test_mascara_legada_divergente_descarta_homonimo():
    assert not custas._identidade_compativel(registro(pessoas=[{
        "nome": "JOAO DA SILVA", "documento": "***.***.321-00",
    }]), pedido(), hash_documento(pedido()["documento"]))


def test_nome_continua_valendo_quando_acervo_nao_tem_cpf():
    assert custas._identidade_compativel(registro(), pedido(), hash_documento(pedido()["documento"]))


@pytest.mark.parametrize("campo,valor", [("produtos", ["MILHO"]), ("safras", ["2025/2026"]),
                                        ("situacao", "BAIXADO"), ("modalidade", "ALIENAÇÃO")])
def test_recuperacao_nao_relaxa_filtros_do_resultado(campo, valor):
    assert not custas._registro_atende_custas(registro(**{campo: valor}), pedido(), "")


def test_pedido_sem_nome_ou_documento_nao_pesquisa_todo_o_banco():
    cur = MagicMock()
    assert custas.localizar_registros_custas(cur, pedido(nome="NÃO CONSTA", documento=""), recuperar=True) == []
    cur.execute.assert_not_called()


def test_recupera_candidato_que_safra_ausente_escondia():
    cur = MagicMock()
    antigo = registro(safras=[])
    cur.fetchall.side_effect = [[], [antigo]]
    original = MagicMock(configuracao=ConfiguracaoTri7("https://teste.invalid", "", "", access_token="teste"))
    cliente = MagicMock()
    cliente.buscar_texto_registro_auxiliar.return_value = {"texto": "texto de teste"}
    with patch("backend.app.servicos.tri7.cliente_tri7", return_value=original), \
         patch("backend.app.servicos.tri7.ClienteTri7", return_value=cliente), \
         patch.object(rotas_ra, "_salvar_indice", return_value=(registro(), False)) as salvar, \
         patch.object(custas, "revalidar_negativas_custas", return_value=[]) as revalidar:
        assert custas.localizar_registros_custas(cur, pedido(), recuperar=True) == [29667]
    cliente.buscar_texto_registro_auxiliar.assert_called_once_with(29667)
    assert salvar.call_args.kwargs["solicitada_ate"] is not None
    revalidar.assert_called_once()
    ampla = next(c.args[0] for c in cur.execute.call_args_list if "ORDER BY (produtos=" in c.args[0])
    assert "safras ?" not in ampla and "produtos ?" not in ampla


def test_registro_cancelado_na_reconsulta_sai_do_resultado():
    cur = MagicMock()
    cur.fetchall.side_effect = [[registro()], [registro()]]
    original = MagicMock(configuracao=ConfiguracaoTri7("https://teste.invalid", "", "", access_token="teste"))
    with patch("backend.app.servicos.tri7.cliente_tri7", return_value=original), \
         patch("backend.app.servicos.tri7.ClienteTri7") as cliente, \
         patch.object(rotas_ra, "_salvar_indice", return_value=(registro(situacao="BAIXADO"), False)), \
         patch.object(custas, "revalidar_negativas_custas", return_value=[]):
        cliente.return_value.buscar_texto_registro_auxiliar.return_value = {"texto": "cancelado"}
        assert custas.localizar_registros_custas(cur, pedido(), recuperar=True) == []


def test_orcamento_externo_e_por_relatorio_e_restante_fica_na_fila():
    cur = MagicMock()
    cur.fetchall.return_value = [registro(numero=n, safras=[]) for n in range(1, 9)]
    contexto = {}
    original = MagicMock(configuracao=ConfiguracaoTri7("https://teste.invalid", "", "", access_token="teste"))
    with patch("backend.app.servicos.tri7.cliente_tri7", return_value=original), \
         patch("backend.app.servicos.tri7.ClienteTri7") as cliente, \
         patch.object(rotas_ra, "_salvar_indice", return_value=(registro(), False)), \
         patch.object(custas, "revalidar_negativas_custas", return_value=[]):
        cliente.return_value.buscar_texto_registro_auxiliar.return_value = {"texto": "texto"}
        for _ in range(3):
            custas._recuperar_candidatos_custas(cur, pedido(), "", "JOAO DA SILVA", True, set(), contexto)
    assert cliente.return_value.buscar_texto_registro_auxiliar.call_count == 2
    insercoes = [c.args[0] for c in cur.execute.call_args_list if "INSERT INTO fila_registros" in c.args[0]]
    assert len(insercoes) == 3
    assert all("LIMIT" not in sql for sql in insercoes)


def test_falha_tri7_preserva_resultado_existente_e_fila():
    cur = MagicMock()
    cur.fetchall.return_value = [registro()]
    with patch("backend.app.servicos.tri7.cliente_tri7", side_effect=RuntimeError("falha")):
        assert custas._recuperar_candidatos_custas(
            cur, pedido(), "", "JOAO DA SILVA", True, {29667}, {}) == [29667]
    assert any("INSERT INTO fila_registros" in c.args[0] for c in cur.execute.call_args_list)


def test_hash_por_pessoa_nao_vaza_na_resposta_publica():
    indice = extrair_indice_registro_auxiliar(1, "R.01 - PENHOR. EMITENTE/DEVEDOR: João da Silva, CPF 123.456.789-01. SOJA safra 2026/2027.")
    assert indice["pessoas"][0]["documento_hash"] == hash_documento("12345678901")
    indice["consultado_em"] = datetime.now(timezone.utc)
    assert "documento_hash" not in registro_auxiliar_json(indice)["pessoas"][0]


def test_fonte_saudavel_nao_esconde_outra_sem_configuracao(monkeypatch):
    from fastapi import HTTPException
    con, cur = conexao()
    cur.fetchone.return_value = {"indexacao_pausada": False}
    primeiro = MagicMock(side_effect=HTTPException(503, "configuração"))
    segundo = MagicMock(return_value={"processados": 1})
    monkeypatch.setattr(worker, "conectar", lambda: con)
    monkeypatch.setattr(worker, "FONTES_INDEXACAO", (("M", "tabela_m", primeiro), ("RA", "tabela_ra", segundo)))
    assert worker.passo_indexacao() is False
    segundo.assert_called_once()


def test_sincronizadores_trabalham_enquanto_operacao_esta_ocupada(monkeypatch):
    indice, sinais_prontos, operacao_ocupada = threading.Event(), threading.Event(), threading.Event()
    parar = threading.Event()
    monkeypatch.setattr(worker, "ciclo_indexacao", indice.set)
    monkeypatch.setattr(worker, "recuperar_movimentacoes", sinais_prontos.set)
    # Simula OCR preso sem liberar o caminho operacional.
    operacao = threading.Thread(target=operacao_ocupada.wait, daemon=True)
    operacao.start()
    rotinas = worker.iniciar_sincronizadores(parar, 5)
    try:
        assert indice.wait(2) and sinais_prontos.wait(2)
        assert operacao.is_alive()
    finally:
        parar.set()
        operacao_ocupada.set()
        for rotina in [*rotinas, operacao]:
            rotina.join(2)
            assert not rotina.is_alive()


def test_erro_transitorio_nao_mata_o_laco():
    parar = threading.Event()
    chamadas = []
    def passo():
        chamadas.append(True)
        if len(chamadas) == 1:
            raise TimeoutError()
        parar.set()
    worker.executar_rotina_continua("teste", passo, parar, 0.001)
    assert len(chamadas) == 2


def test_prioridade_auxiliar_nao_reinicia_carga_inicial():
    cur = MagicMock()
    cur.fetchone.side_effect = [{"ciclo_automatico": 1, "proximo_inicial": 10, "limite_inicial": 29667}, {"total": 1}]
    assert rotas_ra._proximo_modo_automatico(cur) == "PRIORITARIA"


def test_conclusao_da_fila_preserva_pedido_que_chegou_durante_consulta():
    cur = MagicMock()
    inicio = datetime.now(timezone.utc)
    concluir_auxiliar(cur, 29667, inicio)
    assert cur.execute.call_args.args[1] == (29667, inicio)
    assert "solicitada_em<=%s" in cur.execute.call_args.args[0]


def test_falha_de_descoberta_libera_lease_sem_avancar_checkpoint():
    con, cur = conexao()
    prazo = datetime.now(timezone.utc)
    cur.fetchone.return_value = {"sinais_trava_ate": prazo}
    cliente = MagicMock()
    cliente.buscar_livro_protocolos.side_effect = TimeoutError()
    with patch.object(sinais, "conectar", return_value=con), pytest.raises(TimeoutError):
        sinais._descobrir_protocolos(cliente)
    sql = cur.execute.call_args.args[0]
    assert "sinais_trava_ate=NULL" in sql and "sinais_verificados_em=NOW()" not in sql
    assert cur.execute.call_args.args[1] == (prazo,)


def test_descoberta_sem_mudanca_nao_reenfileira_protocolo():
    con, cur = conexao()
    cur.fetchone.side_effect = [{"sinais_trava_ate": datetime.now(timezone.utc)}, None]
    cliente = MagicMock()
    with patch.object(sinais, "conectar", return_value=con), \
         patch.object(sinais, "montar_protocolos_do_dia", return_value=[{"numero": "185001", "status": "REGISTRADO"}]):
        assert sinais._descobrir_protocolos(cliente) == 1
    assert not any("INSERT INTO fila_protocolos" in c.args[0] for c in cur.execute.call_args_list)
