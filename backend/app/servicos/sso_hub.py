"""Contrato HUB Ed25519, independente do receptor Sync legado."""
import base64
import hashlib
import json
import os
import re
import time
from dataclasses import dataclass
from uuid import UUID

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

TOLERANCIA_SEGUNDOS = 5
LIMITE_CORPO = 8192


class ConfiguracaoHubInvalida(ValueError):
    pass


class TicketHubInvalido(ValueError):
    pass


def _pares_unicos(pares):
    resultado = {}
    for chave, valor in pares:
        if chave in resultado:
            raise TicketHubInvalido()
        resultado[chave] = valor
    return resultado


def _constante_invalida(_valor):
    raise TicketHubInvalido()


def objeto_json(bruto):
    try:
        dados = json.loads(bruto, object_pairs_hook=_pares_unicos, parse_constant=_constante_invalida)
        if not isinstance(dados, dict):
            raise TicketHubInvalido()
        return dados
    except (ValueError, UnicodeError, RecursionError) as erro:
        raise TicketHubInvalido() from erro


def _segmento(valor):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", valor):
        raise TicketHubInvalido()
    try:
        decodificado = base64.b64decode(valor + "=" * (-len(valor) % 4), altchars=b"-_", validate=True)
    except ValueError as erro:
        raise TicketHubInvalido() from erro
    if base64.urlsafe_b64encode(decodificado).decode().rstrip("=") != valor:
        raise TicketHubInvalido()
    return decodificado


def _uuid(valor):
    try:
        if not isinstance(valor, str) or str(UUID(valor)) != valor:
            raise TicketHubInvalido()
        return valor
    except (ValueError, AttributeError) as erro:
        raise TicketHubInvalido() from erro


@dataclass(frozen=True)
class TicketHub:
    sub: str
    jti: str
    exp: int


def validar_ticket_hub(ticket, *, agora=None):
    chave_hex = os.getenv("AERI_HUB_SSO_PUBLIC_KEY_HEX", "")
    kid = os.getenv("AERI_HUB_SSO_KID", "")
    if not re.fullmatch(r"[0-9a-f]{64}", chave_hex):
        raise ConfiguracaoHubInvalida()
    chave_bytes = bytes.fromhex(chave_hex)
    if kid != "sso-" + hashlib.sha256(chave_bytes).hexdigest()[:16]:
        raise ConfiguracaoHubInvalida()
    if not isinstance(ticket, str) or not 1 <= len(ticket) <= LIMITE_CORPO:
        raise TicketHubInvalido()
    partes = ticket.split(".")
    if len(partes) != 3:
        raise TicketHubInvalido()
    cabecalho = objeto_json(_segmento(partes[0]))
    if cabecalho != {"typ": "JWT", "alg": "EdDSA", "kid": kid}:
        raise TicketHubInvalido()
    try:
        Ed25519PublicKey.from_public_bytes(chave_bytes).verify(
            _segmento(partes[2]), f"{partes[0]}.{partes[1]}".encode("ascii"),
        )
    except (InvalidSignature, ValueError) as erro:
        raise TicketHubInvalido() from erro
    claims = objeto_json(_segmento(partes[1]))
    if claims.get("iss") != "sync-hub" or claims.get("aud") != "aeri":
        raise TicketHubInvalido()
    instante = int(time.time()) if agora is None else agora
    iat, exp = claims.get("iat"), claims.get("exp")
    if (type(iat) is not int or type(exp) is not int or not 0 < exp - iat <= 60
            or iat > instante + TOLERANCIA_SEGUNDOS or exp <= instante - TOLERANCIA_SEGUNDOS):
        raise TicketHubInvalido()
    if "nbf" in claims and (type(claims["nbf"]) is not int or claims["nbf"] > instante + TOLERANCIA_SEGUNDOS):
        raise TicketHubInvalido()
    return TicketHub(sub=_uuid(claims.get("sub")), jti=_uuid(claims.get("jti")), exp=exp)
