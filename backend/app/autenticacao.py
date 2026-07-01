import base64
import hashlib
import hmac
import os
import secrets
import time

from fastapi import HTTPException, Request

from backend.app.database import conectar

COOKIE_SESSAO = "aeri_sessao"
SESSAO_SEGUNDOS = 60 * 60 * 12


def hash_senha(senha: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    derivada = hashlib.pbkdf2_hmac("sha256", senha.encode(), salt, 310_000)
    return f"pbkdf2_sha256${base64.urlsafe_b64encode(salt).decode()}${base64.urlsafe_b64encode(derivada).decode()}"


def verificar_senha(senha: str, armazenada: str) -> bool:
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


def segredo_sessao() -> bytes:
    segredo = os.getenv("AERI_SESSION_SECRET")
    if not segredo:
        raise RuntimeError("Configure AERI_SESSION_SECRET no Vercel.")
    return segredo.encode()


def criar_token(usuario: str) -> str:
    payload = f"{usuario}|{int(time.time())}"
    assinatura = hmac.new(segredo_sessao(), payload.encode(), hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(f"{payload}|{assinatura}".encode()).decode()


def ler_token(token: str | None) -> str | None:
    if not token:
        return None
    try:
        usuario, timestamp, assinatura = base64.urlsafe_b64decode(token.encode()).decode().split("|", 2)
        payload = f"{usuario}|{timestamp}"
        esperada = hmac.new(segredo_sessao(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(assinatura, esperada):
            return None
        if time.time() - int(timestamp) > SESSAO_SEGUNDOS:
            return None
        return usuario
    except (ValueError, TypeError):
        return None


def autenticar(usuario: str, senha: str) -> bool:
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute("SELECT senha_hash FROM usuarios_aeri WHERE usuario = %s", (usuario,))
            registro = cursor.fetchone()
    return bool(registro and verificar_senha(senha, registro["senha_hash"]))


def usuario_atual(request: Request) -> str:
    usuario = ler_token(request.cookies.get(COOKIE_SESSAO))
    if not usuario:
        raise HTTPException(status_code=401, detail="Faça login para continuar.")
    return usuario
