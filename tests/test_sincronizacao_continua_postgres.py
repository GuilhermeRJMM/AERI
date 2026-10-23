"""SQL real em tabelas TEMP, com conexão opt-in e rollback integral.

Nenhuma migração, índice ou sequência da aplicação é alterado. As tabelas
clonadas possuem chaves numéricas explícitas, sem serial de produção.
"""
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import psycopg
import pytest
from psycopg.rows import dict_row

from backend.app.rotas.registros_auxiliares import _salvar_indice, _proximo_modo_automatico
from backend.app.servicos.custas import localizar_registros_custas
from backend.app.servicos.fila_auxiliares import enfileirar_auxiliares, concluir_auxiliar


@pytest.fixture
def banco(monkeypatch):
    url = os.getenv("AERI_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("Conexão para teste isolado em tabelas temporárias não configurada.")
    monkeypatch.setenv("AERI_BUSCAS_HMAC_KEY", "chave-apenas-do-teste-isolado")
    con = psycopg.connect(url, row_factory=dict_row, connect_timeout=8)
    try:
        with con.cursor() as cur:
            cur.execute("SET LOCAL search_path=pg_temp")
            for tabela in ("registros_auxiliares_aeri", "registros_auxiliares_erros_aeri",
                           "registros_auxiliares_varredura_aeri", "sincronizacao_registros_auxiliares_aeri",
                           "fila_protocolos_busca_aeri"):
                cur.execute(f"CREATE TEMP TABLE {tabela} (LIKE public.{tabela} INCLUDING ALL) ON COMMIT DROP")
            migracao = (Path(__file__).parents[1] / "backend/app/migrations/062_sincronizacao_continua.sql").read_text(encoding="utf-8")
            cur.execute(migracao.replace("CREATE TABLE IF NOT EXISTS", "CREATE TEMP TABLE IF NOT EXISTS"))
            yield cur
    finally:
        con.rollback()
        con.close()


TEXTO = "R.01 - PENHOR. EMITENTE/DEVEDOR: João da Silva, CPF 123.456.789-01. OBJETO DA GARANTIA: SOJA, safra 2026/2027."
PEDIDO = {"nome": "JOAO DA SILVA", "documento": "12345678901", "produto": "SOJA", "safra": "2026/2027", "modalidade": "PENHOR"}


def test_sql_novo_indice_preserva_filtros_e_nome_legado(banco):
    _salvar_indice(banco, 29667, TEXTO)
    assert localizar_registros_custas(banco, PEDIDO) == [29667]
    assert localizar_registros_custas(banco, {**PEDIDO, "nome": "NOME DIVERGENTE"}) == [29667]
    assert localizar_registros_custas(banco, {**PEDIDO, "documento": ""}) == [29667]
    assert localizar_registros_custas(banco, {**PEDIDO, "documento": "98765432100"}) == []
    for campo, valor in (("produto", "MILHO"), ("safra", "2025/2026"), ("modalidade", "ALIENACAO_FIDUCIARIA")):
        assert localizar_registros_custas(banco, {**PEDIDO, campo: valor}) == []


def test_sql_recupera_safra_sem_varredura_integral(banco):
    _salvar_indice(banco, 29667, TEXTO)
    banco.execute("UPDATE registros_auxiliares_aeri SET safras='[]'::jsonb")
    from backend.app.servicos.tri7 import ConfiguracaoTri7
    from unittest.mock import MagicMock
    original = MagicMock(configuracao=ConfiguracaoTri7("https://teste.invalid", "", "", access_token="teste"))
    with patch("backend.app.servicos.tri7.cliente_tri7", return_value=original), \
         patch("backend.app.servicos.tri7.ClienteTri7") as cliente, \
         patch("backend.app.servicos.custas.revalidar_negativas_custas", return_value=[]):
        cliente.return_value.buscar_texto_registro_auxiliar.return_value = {"texto": TEXTO}
        assert localizar_registros_custas(banco, PEDIDO, recuperar=True) == [29667]
    banco.execute("SELECT safras FROM registros_auxiliares_aeri WHERE numero=29667")
    assert banco.fetchone()["safras"] == ["2026/2027"]


def test_sql_fila_preserva_solicitacao_concorrente_e_prioriza_sem_zerar_cursor(banco):
    enfileirar_auxiliares(banco, [29667, 29667], "LIVRO_PROTOCOLOS")
    enfileirar_auxiliares(banco, [29667], "MOVIMENTACAO_RECENTE")
    passado = datetime.now(timezone.utc) - timedelta(minutes=1)
    concluir_auxiliar(banco, 29667, passado)
    banco.execute("SELECT COUNT(*) AS total FROM fila_registros_auxiliares_aeri")
    assert banco.fetchone()["total"] == 1
    banco.execute("""INSERT INTO sincronizacao_registros_auxiliares_aeri
        (id, limite_inicial, proximo_inicial, ciclo_automatico) VALUES (1,29667,29668,0)""")
    assert _proximo_modo_automatico(banco) == "PRIORITARIA"
    banco.execute("SELECT proximo_inicial FROM sincronizacao_registros_auxiliares_aeri WHERE id=1")
    assert banco.fetchone()["proximo_inicial"] == 29668
    concluir_auxiliar(banco, 29667, datetime.now(timezone.utc) + timedelta(minutes=1))
    banco.execute("SELECT COUNT(*) AS total FROM fila_registros_auxiliares_aeri")
    assert banco.fetchone()["total"] == 0
