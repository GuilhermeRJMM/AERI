import os
from contextlib import contextmanager
from pathlib import Path
from threading import Lock

import psycopg
from psycopg.rows import dict_row


MIGRACOES_DIR = Path(__file__).resolve().parent / "migrations"
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


def _executar_migracoes(cursor) -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS migracoes_aeri (
            versao VARCHAR(120) PRIMARY KEY,
            aplicada_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    cursor.execute("SELECT versao FROM migracoes_aeri")
    aplicadas = {item["versao"] for item in cursor.fetchall()}

    for arquivo in sorted(MIGRACOES_DIR.glob("*.sql")):
        if arquivo.name in aplicadas:
            continue
        cursor.execute(arquivo.read_text(encoding="utf-8"))
        cursor.execute("INSERT INTO migracoes_aeri (versao) VALUES (%s)", (arquivo.name,))


def _garantir_usuario_administrador(cursor) -> None:
    usuario = os.getenv("AERI_ADMIN_USER")
    senha = os.getenv("AERI_ADMIN_PASSWORD")
    if not usuario or not senha:
        return

    cursor.execute("SELECT 1 FROM usuarios_aeri WHERE usuario = %s", (usuario,))
    if cursor.fetchone():
        return

    from backend.app.autenticacao import hash_senha

    cursor.execute(
        """
        INSERT INTO usuarios_aeri (usuario, senha_hash)
        VALUES (%s, %s)
        ON CONFLICT (usuario) DO NOTHING
        """,
        (usuario, hash_senha(senha)),
    )


def preparar_banco() -> None:
    global _banco_preparado

    if _banco_preparado:
        return

    with _bloqueio_preparacao:
        if _banco_preparado:
            return

        with conectar() as conexao:
            with conexao.cursor() as cursor:
                _executar_migracoes(cursor)
                _garantir_usuario_administrador(cursor)
            conexao.commit()
        _banco_preparado = True
