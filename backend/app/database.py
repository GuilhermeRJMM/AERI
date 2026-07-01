import os
from contextlib import contextmanager
from threading import Lock

import psycopg
from psycopg.rows import dict_row


_banco_preparado = False
_bloqueio_preparacao = Lock()


def database_url() -> str:
    url = os.getenv("POSTGRES_URL") or os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("Configure POSTGRES_URL ou DATABASE_URL no Vercel.")
    return url


@contextmanager
def conectar():
    with psycopg.connect(database_url(), row_factory=dict_row) as conexao:
        yield conexao


def preparar_banco() -> None:
    global _banco_preparado

    if _banco_preparado:
        return

    from backend.app.autenticacao import hash_senha

    with _bloqueio_preparacao:
        if _banco_preparado:
            return

        with conectar() as conexao:
            with conexao.cursor() as cursor:
                cursor.execute(
                    """
                CREATE TABLE IF NOT EXISTS usuarios_aeri (
                    usuario VARCHAR(80) PRIMARY KEY,
                    senha_hash TEXT NOT NULL,
                    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS intimacoes_aeri (
                    id UUID PRIMARY KEY,
                    protocolo VARCHAR(11) NOT NULL UNIQUE,
                    credor VARCHAR(160) NOT NULL,
                    devedor VARCHAR(160) NOT NULL,
                    ultimo_andamento DATE NOT NULL,
                    ultima_conferencia DATE,
                    historico JSONB NOT NULL DEFAULT '[]'::jsonb,
                    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );

                ALTER TABLE intimacoes_aeri
                    ALTER COLUMN protocolo TYPE VARCHAR(11);
                    """
                )

                usuario = os.getenv("AERI_ADMIN_USER")
                senha = os.getenv("AERI_ADMIN_PASSWORD")
                if usuario and senha:
                    cursor.execute("SELECT 1 FROM usuarios_aeri WHERE usuario = %s", (usuario,))
                    if not cursor.fetchone():
                        cursor.execute(
                            """
                            INSERT INTO usuarios_aeri (usuario, senha_hash)
                            VALUES (%s, %s)
                            ON CONFLICT (usuario) DO NOTHING
                            """,
                            (usuario, hash_senha(senha)),
                        )
            conexao.commit()
        _banco_preparado = True
