import os
import logging
from ipaddress import ip_address
from urllib.parse import urlsplit

from fastapi import HTTPException, Request
from psycopg.types.json import Jsonb

from backend.app.database import conectar


METODOS_SEGUROS = {"GET", "HEAD", "OPTIONS"}
logger = logging.getLogger("aeri.auditoria")


def _host_http_interno(hostname: str) -> bool:
    host = hostname.lower().rstrip(".")
    if host == "localhost" or host.endswith(".local"):
        return True
    try:
        endereco = ip_address(host)
    except ValueError:
        return False
    return endereco.is_private or endereco.is_loopback


def _normalizar_origem_sync(valor: str) -> str | None:
    valor = valor.strip().rstrip("/")
    if not valor or any(caractere.isspace() for caractere in valor):
        return None
    partes = urlsplit(valor)
    if (
        partes.scheme not in {"http", "https"}
        or not partes.hostname
        or partes.username
        or partes.password
        or partes.path
        or partes.query
        or partes.fragment
    ):
        return None
    if partes.scheme == "http" and not _host_http_interno(partes.hostname):
        return None
    try:
        porta_numero = partes.port
    except ValueError:
        return None
    porta = f":{porta_numero}" if porta_numero else ""
    return f"{partes.scheme}://{partes.hostname.lower()}{porta}"


def origens_sync_autorizadas() -> tuple[str, ...]:
    """Retorna as origens exatas autorizadas a incorporar o AERI.

    A validação impede que uma variável de ambiente malformada injete novas
    diretivas na CSP. Caminhos, credenciais, query string e fragmentos não são
    aceitos porque ``frame-ancestors`` trabalha com origens, não com URLs.
    HTTPS é obrigatório para domínios públicos; HTTP só é aceito em hosts
    internos (``.local``, localhost ou endereços IP privados/loopback).
    """
    bruto = os.getenv("SYNC_ORIGINS") or os.getenv("SYNC_ORIGIN", "")
    valores = [valor for valor in bruto.split(",") if valor.strip()]
    if not valores:
        return ()
    normalizadas = [_normalizar_origem_sync(valor) for valor in valores]
    if any(origem is None for origem in normalizadas):
        return ()
    return tuple(dict.fromkeys(origem for origem in normalizadas if origem))


def origem_sync_autorizada() -> str | None:
    """Mantém compatibilidade retornando a primeira origem autorizada."""
    origens = origens_sync_autorizadas()
    return origens[0] if origens else None


def politica_frame_ancestors() -> str:
    origens_sync = origens_sync_autorizadas()
    return f"'self' {' '.join(origens_sync)}" if origens_sync else "'none'"


def politica_samesite_sessao() -> str:
    # Cookies em iframe entre sites exigem SameSite=None e Secure. Quando a
    # incorporação não está configurada, preservamos a política Strict atual.
    return "none" if origens_sync_autorizadas() else "strict"


def ip_cliente(request: Request) -> str:
    # A Vercel fornece uma cópia própria do endereço e sobrescreve o XFF na
    # entrada. Preferi-la evita ambiguidades quando existe outro proxy antes
    # do deployment; fora da Vercel preservamos o fallback anterior.
    vercel = request.headers.get("x-vercel-forwarded-for", "")
    if os.getenv("VERCEL") and vercel:
        return vercel.split(",")[0].strip()[:64]
    encaminhado = request.headers.get("x-forwarded-for", "")
    if encaminhado:
        # O último salto é o adicionado pelo proxy confiável (Vercel); os
        # anteriores vêm do próprio cliente e podem ser forjados livremente.
        # Usar o primeiro permitia burlar o bloqueio de tentativas de login
        # (e falsificar a auditoria) trocando esse valor a cada requisição.
        return encaminhado.split(",")[-1].strip()[:64]
    return (request.client.host if request.client else "desconhecido")[:64]


def registrar_auditoria(
    request: Request,
    acao: str,
    resultado: str,
    usuario: str | None = None,
    recurso: str | None = None,
    detalhes: dict | None = None,
) -> None:
    try:
        with conectar() as conexao:
            with conexao.cursor() as cursor:
                registrar_auditoria_cursor(cursor, request, acao, resultado, usuario, recurso, detalhes)
            conexao.commit()
    except Exception as erro:
        # Auditoria nunca deve expor dados nem derrubar a operacao principal.
        # A exceção é registrada sem detalhes operacionais/sensíveis: perder a
        # trilha de auditoria silenciosamente também é uma falha de segurança.
        logger.error(
            "auditoria_persistencia_falhou acao=%s tipo=%s",
            acao,
            type(erro).__name__,
        )


def registrar_auditoria_cursor(
    cursor,
    request: Request,
    acao: str,
    resultado: str,
    usuario: str | None = None,
    recurso: str | None = None,
    detalhes: dict | None = None,
) -> None:
    cursor.execute(
        """INSERT INTO auditoria_aeri
        (usuario, acao, recurso, resultado, ip, detalhes)
        VALUES (%s, %s, %s, %s, %s, %s)""",
        (usuario, acao, recurso, resultado, ip_cliente(request), Jsonb(detalhes or {})),
    )


def validar_origem(request: Request) -> None:
    if request.method in METODOS_SEGUROS:
        return
    if request.headers.get("sec-fetch-site") == "cross-site":
        raise HTTPException(status_code=403, detail="Requisição entre sites bloqueada.")
    origem = request.headers.get("origin")
    if origem:
        permitidas = {str(request.base_url).rstrip("/")}
        if os.getenv("AERI_ORIGIN"):
            permitidas.add(os.environ["AERI_ORIGIN"].rstrip("/"))
        if origem.rstrip("/") not in permitidas:
            raise HTTPException(status_code=403, detail="Origem não autorizada.")
