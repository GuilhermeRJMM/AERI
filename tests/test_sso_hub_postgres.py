"""Integração opt-in. Somente banco de testes explicitamente configurado."""
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import psycopg
from psycopg import sql
import pytest


@pytest.fixture
def banco_hub():
    dsn = os.getenv("AERI_TEST_POSTGRES_URL")
    if not dsn:
        pytest.skip("Configure exclusivamente um Postgres de testes para verificar transações concorrentes.")
    esquema = "teste_sso_hub_" + uuid4().hex
    with psycopg.connect(dsn, autocommit=True) as c:
        c.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(esquema)))
        c.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(esquema)))
        try:
            c.execute("CREATE TABLE usuarios_aeri (usuario VARCHAR(80) PRIMARY KEY)")
            migracao = Path(__file__).resolve().parents[1] / "backend/app/migrations/063_sso_hub.sql"
            c.execute(migracao.read_text(encoding="utf-8"))
            c.execute("CREATE TABLE sessoes_aeri (id UUID PRIMARY KEY, revogada_em TIMESTAMPTZ)")
            yield dsn, esquema
        finally:
            # Somente os objetos conhecidos do esquema aleatório criado aqui.
            for tabela in ("sessoes_aeri", "tickets_sso_hub_aeri", "vinculos_sso_hub_aeri", "usuarios_aeri"):
                c.execute(sql.SQL("DROP TABLE IF EXISTS {}.{}").format(sql.Identifier(esquema), sql.Identifier(tabela)))
            c.execute(sql.SQL("DROP SCHEMA {}").format(sql.Identifier(esquema)))


def test_duas_transacoes_mesmo_jti_no_maximo_um_consumo(banco_hub):
    dsn, esquema = banco_hub
    jti = uuid4()
    barreira = Barrier(2)

    def consumir():
        with psycopg.connect(dsn) as c:
            c.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(esquema)))
            barreira.wait(timeout=10)
            return c.execute("""INSERT INTO tickets_sso_hub_aeri (emissor,jti,expira_em)
                VALUES ('sync-hub',%s,NOW()+INTERVAL '65 seconds')
                ON CONFLICT (emissor,jti) DO NOTHING RETURNING jti""", (jti,)).fetchone() is not None

    with ThreadPoolExecutor(max_workers=2) as pool:
        resultados = list(pool.map(lambda _: consumir(), range(2)))
    assert sorted(resultados) == [False, True]


def test_rollback_preserva_sessao_anterior_e_ticket(banco_hub):
    dsn, esquema = banco_hub
    sessao, jti = uuid4(), uuid4()
    with psycopg.connect(dsn) as c:
        c.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(esquema)))
        c.execute("INSERT INTO sessoes_aeri VALUES (%s,NULL)", (sessao,))
        c.commit()
        with pytest.raises(RuntimeError):
            with c.transaction():
                c.execute("INSERT INTO tickets_sso_hub_aeri VALUES ('sync-hub',%s,NOW()+INTERVAL '65 seconds',NOW())", (jti,))
                c.execute("UPDATE sessoes_aeri SET revogada_em=NOW() WHERE id=%s", (sessao,))
                raise RuntimeError("falha sintética ao criar sessão nova")
        assert c.execute("SELECT revogada_em FROM sessoes_aeri WHERE id=%s", (sessao,)).fetchone() == (None,)
        assert c.execute("SELECT COUNT(*) FROM tickets_sso_hub_aeri WHERE jti=%s", (jti,)).fetchone() == (0,)
