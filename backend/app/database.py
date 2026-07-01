import os
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row


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
    from backend.app.autenticacao import hash_senha

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
                    protocolo VARCHAR(10) NOT NULL UNIQUE,
                    credor VARCHAR(160) NOT NULL,
                    devedor VARCHAR(160) NOT NULL,
                    ultimo_andamento DATE NOT NULL,
                    ultima_conferencia DATE,
                    historico JSONB NOT NULL DEFAULT '[]'::jsonb,
                    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )

            usuario = os.getenv("AERI_ADMIN_USER")
            senha = os.getenv("AERI_ADMIN_PASSWORD")
            if usuario and senha:
                cursor.execute(
                    """
                    INSERT INTO usuarios_aeri (usuario, senha_hash)
                    VALUES (%s, %s)
                    ON CONFLICT (usuario) DO NOTHING
                    """,
                    (usuario, hash_senha(senha)),
                )
        conexao.commit()
