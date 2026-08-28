"""TOTP para cargos administrativos, com segredo cifrado no banco."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import struct
import time
from urllib.parse import quote

from cryptography.fernet import Fernet, InvalidToken


def _fernet() -> Fernet:
    raiz = os.getenv("AERI_MFA_ENCRYPTION_KEY") or os.getenv("AERI_BUSCAS_HMAC_KEY")
    if not raiz or len(raiz) < 32:
        raise RuntimeError("Configure AERI_MFA_ENCRYPTION_KEY para habilitar MFA.")
    chave = base64.urlsafe_b64encode(hashlib.sha256(("AERI:MFA:" + raiz).encode()).digest())
    return Fernet(chave)


def novo_segredo() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def cifrar_segredo(segredo: str) -> str:
    return _fernet().encrypt(segredo.encode()).decode()


def decifrar_segredo(valor: str) -> str:
    try:
        return _fernet().decrypt(valor.encode()).decode()
    except InvalidToken as exc:
        raise RuntimeError("Não foi possível validar a configuração MFA.") from exc


def codigo_totp(segredo: str, instante: int | None = None) -> str:
    instante = instante if instante is not None else int(time.time())
    contador = instante // 30
    preenchido = segredo + "=" * ((8 - len(segredo) % 8) % 8)
    chave = base64.b32decode(preenchido, casefold=True)
    resumo = hmac.new(chave, struct.pack(">Q", contador), hashlib.sha1).digest()
    deslocamento = resumo[-1] & 0x0F
    numero = (struct.unpack(">I", resumo[deslocamento:deslocamento + 4])[0] & 0x7FFFFFFF) % 1_000_000
    return f"{numero:06d}"


def validar_totp(segredo: str, codigo: object) -> bool:
    informado = "".join(c for c in str(codigo or "") if c.isdigit())
    if len(informado) != 6:
        return False
    agora = int(time.time())
    return any(hmac.compare_digest(codigo_totp(segredo, agora + passo * 30), informado) for passo in (-1, 0, 1))


def uri_totp(usuario: str, segredo: str) -> str:
    return f"otpauth://totp/{quote('AERI:' + usuario)}?secret={segredo}&issuer=AERI&algorithm=SHA1&digits=6&period=30"
