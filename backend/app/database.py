import os
import logging
from contextlib import contextmanager
from pathlib import Path
from threading import Lock

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool


MIGRACOES_DIR = Path(__file__).resolve().parent / "migrations"
_banco_preparado = False
_bloqueio_preparacao = Lock()
_pool = None
_bloqueio_pool = Lock()
_CHAVE_MIGRACOES = 1_095_062_089  # "AERI" em hexadecimal
logger = logging.getLogger("aeri.banco")


def database_url() -> str:
    url = os.getenv("POSTGRES_URL") or os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("Configure POSTGRES_URL ou DATABASE_URL no Vercel.")
    return url


@contextmanager
def conectar():
    with _obter_pool().connection() as conexao:
        yield conexao


def fechar_pool() -> None:
    """Encerra o pool antes do fim do processo.

    Sem isto o __del__ do psycopg_pool tenta juntar as threads durante o
    encerramento do interpretador e o Python levanta PythonFinalizationError --
    um traceback de quatro linhas depois de um ciclo bem-sucedido, que parece
    falha e nao e. A funcao serverless nao precisa disto (o processo nao encerra
    de forma ordenada), mas o executor da serventia sim.
    """
    global _pool
    with _bloqueio_pool:
        if _pool is not None:
            _pool.close()
            _pool = None


def _obter_pool() -> ConnectionPool:
    global _pool
    if _pool is not None:
        return _pool
    with _bloqueio_pool:
        if _pool is None:
            try:
                maximo = int(os.getenv("AERI_DB_POOL_MAX", "3"))
            except ValueError:
                maximo = 3
            maximo = min(max(maximo, 1), 5)
            # min_size=0 é essencial no serverless: uma instância aquecida que
            # não está recebendo tráfego não reserva conexões no Neon.
            _pool = ConnectionPool(
                conninfo=database_url(),
                min_size=0,
                max_size=maximo,
                timeout=10,
                max_idle=30,
                max_lifetime=900,
                check=ConnectionPool.check_connection,
                kwargs={"row_factory": dict_row, "connect_timeout": 10},
                open=True,
                name="aeri",
            )
    return _pool


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
        # ON CONFLICT DO NOTHING: sob cold starts concorrentes, duas
        # instâncias podem ver a mesma migração como pendente; sem isso, a
        # segunda esbarra em violação de chave única nesse INSERT e a
        # requisição inteira falha com 500 (mesmo com o DDL em si já sendo
        # idempotente).
        cursor.execute(
            "INSERT INTO migracoes_aeri (versao) VALUES (%s) ON CONFLICT (versao) DO NOTHING",
            (arquivo.name,),
        )


def _garantir_usuario_administrador(cursor) -> None:
    usuario = os.getenv("AERI_ADMIN_USER")
    senha = os.getenv("AERI_ADMIN_PASSWORD")
    if not usuario or not senha:
        return

    from backend.app.autenticacao import hash_senha, senha_forte

    if not senha_forte(senha):
        raise RuntimeError(
            "AERI_ADMIN_PASSWORD deve ter 10 caracteres, maiúscula, número e símbolo."
        )

    cursor.execute("SELECT perfil, ativo FROM usuarios_aeri WHERE usuario = %s", (usuario,))
    existente = cursor.fetchone()
    if existente:
        # Bootstrap é estritamente de primeira instalação. Uma conta existente
        # pode ter sido desativada por suspeita de comprometimento; nunca se
        # deve desfazer essa decisão num cold start.
        return

    cursor.execute(
        """
        INSERT INTO usuarios_aeri (usuario, senha_hash, nome, perfil, ativo)
        VALUES (%s, %s, %s, 'ADMIN', TRUE)
        ON CONFLICT (usuario) DO NOTHING
        """,
        (usuario, hash_senha(senha), usuario),
    )
    cursor.execute(
        """INSERT INTO auditoria_aeri (usuario, acao, resultado, detalhes)
        VALUES (%s, 'bootstrap_admin_criado', 'sucesso', '{}'::jsonb)""",
        (usuario,),
    )


def _limpar_dados_de_seguranca(cursor) -> None:
    try:
        retencao = int(os.getenv("AERI_AUDIT_RETENTION_DAYS", "180"))
    except ValueError:
        retencao = 180
    retencao = min(max(retencao, 30), 730)
    cursor.execute("DELETE FROM sessoes_aeri WHERE expira_em < NOW() - INTERVAL '7 days'")
    cursor.execute("DELETE FROM tentativas_login_aeri WHERE criada_em < NOW() - INTERVAL '2 days'")
    cursor.execute(
        "DELETE FROM auditoria_aeri WHERE criada_em < NOW() - (%s * INTERVAL '1 day')",
        (retencao,),
    )
    cursor.execute("DELETE FROM eventos_onr_aeri WHERE recebido_em < NOW() - INTERVAL '180 days'")


def executar_manutencao_banco() -> None:
    """Aplica retenção fora do cold start e sem competir entre instâncias."""
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_xact_lock(%s) AS obteve", (_CHAVE_MIGRACOES + 1,))
            if not cursor.fetchone()["obteve"]:
                return
            _limpar_dados_de_seguranca(cursor)
        conexao.commit()


def preparar_banco() -> None:
    global _banco_preparado

    if _banco_preparado:
        return

    with _bloqueio_preparacao:
        if _banco_preparado:
            return

        with conectar() as conexao:
            with conexao.cursor() as cursor:
                # O Lock acima protege apenas threads desta instância. O lock
                # transacional do Postgres serializa cold starts de todas as
                # instâncias da Vercel antes de executar DDL e bootstrap.
                cursor.execute("SELECT pg_advisory_xact_lock(%s)", (_CHAVE_MIGRACOES,))
                _executar_migracoes(cursor)
                from backend.app.permissoes import sincronizar_catalogo_cursor
                sincronizar_catalogo_cursor(cursor)
                _garantir_usuario_administrador(cursor)
            conexao.commit()
        _banco_preparado = True
