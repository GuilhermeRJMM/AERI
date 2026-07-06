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
    with psycopg.connect(database_url(), row_factory=dict_row, connect_timeout=10) as conexao:
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

    from backend.app.autenticacao import hash_senha, senha_forte

    if not senha_forte(senha):
        raise RuntimeError(
            "AERI_ADMIN_PASSWORD deve ter 14 caracteres, maiúscula, minúscula, número e símbolo."
        )

    cursor.execute("SELECT senha_hash FROM usuarios_aeri WHERE usuario = %s", (usuario,))
    existente = cursor.fetchone()
    if existente:
        cursor.execute(
            "UPDATE usuarios_aeri SET perfil='ADMIN', ativo=TRUE WHERE usuario=%s",
            (usuario,),
        )
        return

    cursor.execute(
        """
        INSERT INTO usuarios_aeri (usuario, senha_hash, nome, perfil, ativo)
        VALUES (%s, %s, %s, 'ADMIN', TRUE)
        ON CONFLICT (usuario) DO NOTHING
        """,
        (usuario, hash_senha(senha), usuario),
    )


def _limpar_dados_de_seguranca(cursor) -> None:
    retencao = int(os.getenv("AERI_AUDIT_RETENTION_DAYS", "180"))
    retencao = min(max(retencao, 30), 730)
    cursor.execute("DELETE FROM sessoes_aeri WHERE expira_em < NOW() - INTERVAL '7 days'")
    cursor.execute("DELETE FROM tentativas_login_aeri WHERE criada_em < NOW() - INTERVAL '2 days'")
    cursor.execute(
        "DELETE FROM auditoria_aeri WHERE criada_em < NOW() - (%s * INTERVAL '1 day')",
        (retencao,),
    )
    cursor.execute("DELETE FROM eventos_onr_aeri WHERE recebido_em < NOW() - INTERVAL '180 days'")


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
                _limpar_dados_de_seguranca(cursor)
            conexao.commit()
        _banco_preparado = True
