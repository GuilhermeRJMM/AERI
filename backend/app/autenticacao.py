import base64
import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import Depends, HTTPException, Request

from backend.app.database import conectar
from backend.app.seguranca_web import ip_cliente, validar_origem


COOKIE_SESSAO = "__Host-aeri_sessao"
SESSAO_SEGUNDOS = 60 * 60 * 8
INATIVIDADE_SEGUNDOS = 60 * 30
MAX_TENTATIVAS = 5
JANELA_TENTATIVAS_MINUTOS = 15
PERMISSOES = {
    "processar_matricula": "pode_processar_matricula",
    "processar_incra": "pode_processar_incra",
    "ver_intimacoes": "pode_ver_intimacoes",
    "criar_intimacoes": "pode_criar_intimacoes",
    "alterar_intimacoes": "pode_alterar_intimacoes",
    "conferir_intimacoes": "pode_conferir_intimacoes",
}
_argon2 = PasswordHasher(time_cost=2, memory_cost=19_456, parallelism=1)
_HASH_SIMULADO = _argon2.hash("senha-inexistente-para-tempo-constante")


def senha_forte(senha: str) -> bool:
    return (
        len(senha) >= 14
        and any(c.isupper() for c in senha)
        and any(c.islower() for c in senha)
        and any(c.isdigit() for c in senha)
        and any(not c.isalnum() for c in senha)
    )


def hash_senha(senha: str) -> str:
    return _argon2.hash(senha)


def verificar_senha(senha: str, armazenada: str) -> bool:
    if armazenada.startswith("$argon2id$"):
        try:
            return _argon2.verify(armazenada, senha)
        except (VerifyMismatchError, InvalidHashError):
            return False
    try:
        algoritmo, salt_b64, hash_b64 = armazenada.split("$", 2)
        if algoritmo != "pbkdf2_sha256":
            return False
        salt = base64.urlsafe_b64decode(salt_b64)
        esperado = base64.urlsafe_b64decode(hash_b64)
        obtido = hashlib.pbkdf2_hmac("sha256", senha.encode(), salt, 310_000)
        return hmac.compare_digest(obtido, esperado)
    except (ValueError, TypeError):
        return False


def verificar_senha_login(senha: str, registro: dict | None) -> bool:
    armazenada = registro["senha_hash"] if registro else _HASH_SIMULADO
    return verificar_senha(senha, armazenada) and registro is not None


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def verificar_bloqueio(usuario: str, ip: str) -> int:
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            total = contar_tentativas_invalidas(cursor, usuario, ip)
    return max(0, MAX_TENTATIVAS - total)


def contar_tentativas_invalidas(cursor, usuario: str, ip: str) -> int:
    cursor.execute(
        """SELECT COUNT(*) AS total FROM tentativas_login_aeri
        WHERE usuario=%s AND ip=%s AND sucesso=FALSE
        AND criada_em > NOW() - (%s * INTERVAL '1 minute')""",
        (usuario, ip, JANELA_TENTATIVAS_MINUTOS),
    )
    return cursor.fetchone()["total"]


def registrar_tentativa_cursor(cursor, usuario: str, ip: str, sucesso: bool) -> None:
    if sucesso:
        cursor.execute("DELETE FROM tentativas_login_aeri WHERE usuario=%s AND ip=%s", (usuario, ip))
    else:
        cursor.execute(
            "INSERT INTO tentativas_login_aeri (usuario, ip, sucesso) VALUES (%s, %s, FALSE)",
            (usuario, ip),
        )
    cursor.execute("DELETE FROM tentativas_login_aeri WHERE criada_em < NOW() - INTERVAL '2 days'")


def registrar_tentativa(usuario: str, ip: str, sucesso: bool) -> None:
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            registrar_tentativa_cursor(cursor, usuario, ip, sucesso)
        conexao.commit()


def autenticar(usuario: str, senha: str) -> bool:
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(
                "SELECT senha_hash FROM usuarios_aeri WHERE UPPER(usuario)=UPPER(%s) AND ativo=TRUE",
                (usuario,),
            )
            registro = cursor.fetchone()
            armazenada = registro["senha_hash"] if registro else _HASH_SIMULADO
            valido = verificar_senha(senha, armazenada) and registro is not None
            if valido and not registro["senha_hash"].startswith("$argon2id$"):
                cursor.execute("UPDATE usuarios_aeri SET senha_hash=%s WHERE usuario=%s", (hash_senha(senha), usuario))
        conexao.commit()
    return valido


def criar_sessao(usuario: str, request: Request) -> tuple[str, str]:
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            token, csrf = criar_sessao_cursor(cursor, usuario, request)
        conexao.commit()
    return token, csrf


def criar_sessao_cursor(cursor, usuario: str, request: Request) -> tuple[str, str]:
    token = secrets.token_urlsafe(48)
    csrf = secrets.token_urlsafe(32)
    agora = datetime.now(timezone.utc)
    cursor.execute("DELETE FROM sessoes_aeri WHERE expira_em < NOW() OR revogada_em IS NOT NULL")
    cursor.execute(
        """INSERT INTO sessoes_aeri
        (id, usuario, token_hash, csrf_hash, ip, user_agent, expira_em)
        VALUES (%s, %s, %s, %s, %s, %s, %s)""",
        (uuid4(), usuario, _hash_token(token), _hash_token(csrf), ip_cliente(request),
         request.headers.get("user-agent", "")[:300], agora + timedelta(seconds=SESSAO_SEGUNDOS)),
    )
    return token, csrf


def _obter_sessao(request: Request) -> dict | None:
    token = request.cookies.get(COOKIE_SESSAO)
    if not token:
        return None
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(
                """SELECT s.*, u.perfil, u.nome, u.ativo, u.deve_trocar_senha,
                u.pode_processar_matricula, u.pode_processar_incra,
                u.pode_ver_intimacoes, u.pode_criar_intimacoes,
                u.pode_alterar_intimacoes, u.pode_conferir_intimacoes
                FROM sessoes_aeri s JOIN usuarios_aeri u ON u.usuario=s.usuario
                WHERE s.token_hash=%s AND s.revogada_em IS NULL AND u.ativo=TRUE
                AND s.expira_em > NOW() AND s.ultimo_acesso > NOW() - (%s * INTERVAL '1 second')""",
                (_hash_token(token), INATIVIDADE_SEGUNDOS),
            )
            sessao = cursor.fetchone()
            if sessao:
                cursor.execute("UPDATE sessoes_aeri SET ultimo_acesso=NOW() WHERE id=%s", (sessao["id"],))
        conexao.commit()
    return sessao


def usuario_atual(request: Request) -> str:
    sessao = _obter_sessao(request)
    if not sessao:
        raise HTTPException(status_code=401, detail="Faça login para continuar.")
    request.state.sessao = sessao
    return sessao["usuario"]


def permissoes_sessao(sessao: dict) -> dict:
    if sessao["perfil"] == "ADMIN":
        return {chave: True for chave in PERMISSOES}
    return {chave: bool(sessao.get(coluna)) for chave, coluna in PERMISSOES.items()}


def exigir_perfis(*perfis: str):
    def verificar(request: Request, usuario: str = Depends(usuario_atual)) -> str:
        sessao = request.state.sessao
        if sessao["deve_trocar_senha"]:
            raise HTTPException(status_code=403, detail="Troque sua senha temporária para continuar.")
        if sessao["perfil"] not in perfis:
            raise HTTPException(status_code=403, detail="Você não possui permissão para esta operação.")
        return usuario
    return verificar


def exigir_permissao(permissao: str):
    if permissao not in PERMISSOES:
        raise RuntimeError(f"Permissão desconhecida: {permissao}")

    def verificar(request: Request, usuario: str = Depends(usuario_atual)) -> str:
        sessao = request.state.sessao
        if sessao["deve_trocar_senha"]:
            raise HTTPException(status_code=403, detail="Troque sua senha temporária para continuar.")
        if sessao["perfil"] == "ADMIN" or bool(sessao.get(PERMISSOES[permissao])):
            return usuario
        raise HTTPException(status_code=403, detail="Você não possui permissão para esta operação.")

    return verificar


def proteger_csrf(request: Request) -> None:
    validar_origem(request)
    sessao = getattr(request.state, "sessao", None) or _obter_sessao(request)
    token = request.headers.get("x-csrf-token", "")
    if not sessao or not token or not hmac.compare_digest(_hash_token(token), sessao["csrf_hash"]):
        raise HTTPException(status_code=403, detail="Validação de segurança expirada.")


def renovar_csrf(request: Request) -> str:
    sessao = getattr(request.state, "sessao", None)
    if not sessao:
        raise HTTPException(status_code=401, detail="Faça login para continuar.")
    csrf = secrets.token_urlsafe(32)
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute("UPDATE sessoes_aeri SET csrf_hash=%s WHERE id=%s", (_hash_token(csrf), sessao["id"]))
        conexao.commit()
    return csrf


def revogar_sessao(request: Request) -> None:
    token = request.cookies.get(COOKIE_SESSAO)
    if not token:
        return
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute("UPDATE sessoes_aeri SET revogada_em=NOW() WHERE token_hash=%s", (_hash_token(token),))
        conexao.commit()
