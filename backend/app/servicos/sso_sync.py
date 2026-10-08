"""Validação de tickets SSO assinados pelo Sync.

O Sync mantém a chave privada. O AERI recebe somente a chave pública RSA e
aceita tickets RS256 curtos, destinados exclusivamente ao AERI e de uso único.
"""

import base64
import binascii
import hashlib
import json
import os
import re
import time
from dataclasses import dataclass

from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa


TEMPO_MAXIMO_TICKET_SEGUNDOS = 90
TOLERANCIA_RELOGIO_SEGUNDOS = 15
TAMANHO_MAXIMO_TICKET = 8_192


class SsoSyncConfiguracaoInvalida(RuntimeError):
    """O receptor SSO ainda não recebeu a chave pública/configuração do Sync."""


class SsoSyncTicketInvalido(ValueError):
    """O ticket recebido não atende ao contrato de segurança do SSO."""


@dataclass(frozen=True)
class TicketSync:
    usuario: str
    jti_hash: str
    expira_em: int
    metodos_autenticacao: frozenset[str]


def _decodificar_segmento_b64url(valor: str) -> bytes:
    try:
        preenchimento = "=" * (-len(valor) % 4)
        return base64.b64decode(valor + preenchimento, altchars=b"-_", validate=True)
    except (ValueError, binascii.Error) as erro:
        raise SsoSyncTicketInvalido("Ticket SSO inválido.") from erro


def _objeto_json(segmento: str) -> dict:
    try:
        valor = json.loads(_decodificar_segmento_b64url(segmento).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as erro:
        raise SsoSyncTicketInvalido("Ticket SSO inválido.") from erro
    if not isinstance(valor, dict):
        raise SsoSyncTicketInvalido("Ticket SSO inválido.")
    return valor


def _chave_publica_configurada() -> rsa.RSAPublicKey:
    pem = os.getenv("AERI_SYNC_SSO_PUBLIC_KEY_PEM", "").strip()
    if not pem:
        raise SsoSyncConfiguracaoInvalida("O recebimento SSO do Sync ainda não foi configurado.")
    try:
        chave = serialization.load_pem_public_key(pem.replace("\\n", "\n").encode("utf-8"))
    except (ValueError, TypeError, UnsupportedAlgorithm) as erro:
        raise SsoSyncConfiguracaoInvalida("A chave pública do Sync está inválida.") from erro
    if not isinstance(chave, rsa.RSAPublicKey) or chave.key_size < 2048:
        raise SsoSyncConfiguracaoInvalida("A chave pública do Sync deve ser RSA de pelo menos 2048 bits.")
    return chave


def validar_ticket_sync(token: str, *, agora: int | None = None) -> TicketSync:
    """Valida JWT RS256 e retorna apenas os campos necessários ao login."""
    if not isinstance(token, str) or not token or len(token) > TAMANHO_MAXIMO_TICKET:
        raise SsoSyncTicketInvalido("Ticket SSO inválido.")

    partes = token.split(".")
    if len(partes) != 3 or any(not parte for parte in partes):
        raise SsoSyncTicketInvalido("Ticket SSO inválido.")
    cabecalho = _objeto_json(partes[0])
    claims = _objeto_json(partes[1])
    if cabecalho.get("alg") != "RS256" or cabecalho.get("typ", "JWT") != "JWT":
        raise SsoSyncTicketInvalido("Algoritmo de assinatura do ticket não aceito.")

    chave = _chave_publica_configurada()
    assinatura = _decodificar_segmento_b64url(partes[2])
    try:
        chave.verify(
            assinatura,
            f"{partes[0]}.{partes[1]}".encode("ascii"),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
    except (InvalidSignature, ValueError, TypeError) as erro:
        raise SsoSyncTicketInvalido("Assinatura do ticket não confere.") from erro

    emissor = os.getenv("AERI_SYNC_SSO_ISSUER", "sync").strip()
    audiencia = os.getenv("AERI_SYNC_SSO_AUDIENCE", "aeri").strip()
    if not emissor or claims.get("iss") != emissor:
        raise SsoSyncTicketInvalido("Emissor do ticket não autorizado.")
    aud_claim = claims.get("aud")
    if isinstance(aud_claim, str):
        audiencias = {aud_claim}
    elif isinstance(aud_claim, list) and all(isinstance(x, str) for x in aud_claim):
        audiencias = set(aud_claim)
    else:
        audiencias = set()
    if not audiencia or audiencia not in audiencias:
        raise SsoSyncTicketInvalido("Destinatário do ticket não autorizado.")

    instante = int(time.time()) if agora is None else int(agora)
    emitido = claims.get("iat")
    expira = claims.get("exp")
    nao_antes = claims.get("nbf", emitido)
    if (
        not isinstance(emitido, int)
        or isinstance(emitido, bool)
        or not isinstance(expira, int)
        or isinstance(expira, bool)
        or not isinstance(nao_antes, int)
        or isinstance(nao_antes, bool)
    ):
        raise SsoSyncTicketInvalido("Validade do ticket inválida.")
    if emitido > instante + TOLERANCIA_RELOGIO_SEGUNDOS:
        raise SsoSyncTicketInvalido("Ticket emitido no futuro.")
    if nao_antes > instante + TOLERANCIA_RELOGIO_SEGUNDOS:
        raise SsoSyncTicketInvalido("Ticket ainda não está válido.")
    if expira <= instante - TOLERANCIA_RELOGIO_SEGUNDOS or expira <= emitido:
        raise SsoSyncTicketInvalido("Ticket expirado.")
    if expira - emitido > TEMPO_MAXIMO_TICKET_SEGUNDOS:
        raise SsoSyncTicketInvalido("Ticket com validade acima do limite.")

    jti = claims.get("jti")
    if not isinstance(jti, str) or not re.fullmatch(r"[A-Za-z0-9_-]{16,128}", jti):
        raise SsoSyncTicketInvalido("Identificador único do ticket inválido.")
    usuario = claims.get("sub")
    if not isinstance(usuario, str) or not usuario.strip() or len(usuario.strip()) > 80:
        raise SsoSyncTicketInvalido("Usuário do ticket inválido.")

    amr = claims.get("amr", [])
    if not isinstance(amr, list) or any(not isinstance(item, str) for item in amr):
        raise SsoSyncTicketInvalido("Métodos de autenticação do ticket inválidos.")

    return TicketSync(
        usuario=usuario.strip().upper(),
        jti_hash=hashlib.sha256(jti.encode("utf-8")).hexdigest(),
        expira_em=expira,
        metodos_autenticacao=frozenset(item.lower() for item in amr),
    )
