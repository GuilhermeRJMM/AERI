"""Regressões da revisão interrompida pela matrícula 8.787, sem dados reais."""
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

from backend.app import proprietarios
from backend.app.rotas import buscas_indexacao as indice


@pytest.mark.parametrize("texto", [None, "", " ", "\n", "\t \r\n", "; ;", "1- "])
def test_extrator_aceita_bloco_sem_pessoas(texto):
    assert proprietarios.extrair_pessoas(texto) == []


def test_extrator_aceita_bloco_esvaziado_pela_limpeza():
    with patch.object(proprietarios, "_limpar_bloco_de_pessoas", return_value=("  ", None, [])):
        assert proprietarios.extrair_pessoas("trecho antes da limpeza") == []


@pytest.mark.parametrize("modo", ["INICIAL", "REVISAO", "NOVOS", "ERROS"])
def test_falha_de_uma_matricula_nao_perde_lote_nem_expoe_dados(modo, caplog):
    estado = dict(id=1, proximo_inicial=8786, limite_inicial=8788,
                  ultimo_conhecido=8785, proximo_revisao=1)
    cursor = MagicMock()
    cursor.fetchone.return_value = estado
    cursor.fetchall.return_value = [{"numero": n} for n in (8786, 8787, 8788)]
    conexao = MagicMock()
    conexao.__enter__.return_value = conexao
    conexao.cursor.return_value.__enter__.return_value = cursor
    gravadas, transacoes = [], []

    @contextmanager
    def transacao():
        anteriores = list(gravadas)
        try:
            yield
        except Exception:
            gravadas[:] = anteriores
            transacoes.append("rollback")
            raise
        else:
            transacoes.append("ok")

    conexao.transaction.side_effect = transacao

    def salvar(_cursor, numero, _texto, **_opcoes):
        gravadas.append(numero)
        if numero == 8787:
            raise IndexError("CONTEUDO_PRIVADO_NAO_PODE_IR_AO_LOG")
        return ({"situacao": "ATIVA"}, True, False,
                {"estado": "VALIDADA_AUTOMATICAMENTE"}, False)

    resultados = [{"numero": n, "status": "OK", "texto": "texto sintético"}
                  for n in (8786, 8787, 8788)]
    with patch.object(indice, "conectar", return_value=conexao), \
            patch.object(indice, "validar_configuracao_buscas"), \
            patch.object(indice, "_consultar_lote", return_value=(resultados, None)), \
            patch.object(indice, "_selecionar_numeros_novos", return_value=([8786, 8787, 8788], 0, 3)), \
            patch.object(indice, "_salvar_indice", side_effect=salvar) as salvar_indice, \
            patch.object(indice, "_salvar_ausencia") as salvar_ausencia, \
            patch.object(indice, "_registrar_erro") as registrar_erro, \
            patch.object(indice, "_estado_json", return_value={}), \
            patch.object(indice, "registrar_auditoria_cursor"):
        resposta = indice._executar_sincronizacao(modo, 3, 0, MagicMock(), "TESTE")

    assert salvar_indice.call_count == 3
    assert gravadas == [8786, 8788]
    assert transacoes == ["ok", "rollback", "ok"]
    assert resposta["processados"] == 3
    assert resposta["encontradas"] == resposta["ativas"] == 2
    assert resposta["auditoriasValidadas"] == 2
    assert resposta["falhas"] == 1
    assert resposta["ausentes"] == 0
    assert resposta["falha"] is None
    assert resposta["erros"][0]["numero"] == 8787
    assert "IndexError" in resposta["erros"][0]["erro"]
    registrar_erro.assert_called_once()
    assert registrar_erro.call_args.args[1:3] == (8787, modo)
    assert "CONTEUDO_PRIVADO" not in str(registrar_erro.call_args.args[3])
    assert "CONTEUDO_PRIVADO" not in caplog.text
    assert "8787" in caplog.text and "IndexError" in caplog.text
    salvar_ausencia.assert_not_called()
