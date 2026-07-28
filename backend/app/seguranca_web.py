import os
from ipaddress import ip_address
from urllib.parse import urlsplit

from fastapi import HTTPException, Request
from psycopg.types.json import Jsonb

from backend.app.database import conectar


METODOS_SEGUROS = {"GET", "HEAD", "OPTIONS"}


def _host_http_interno(hostname: str) -> bool:
    host = hostname.lower().rstrip(".")
    if host == "localhost" or host.endswith(".local"):
        return True
    try:
        endereco = ip_address(host)
    except ValueError:
        return False
    return endereco.is_private or endereco.is_loopback


def origem_sync_autorizada() -> str | None:
    """Retorna a origem exata autorizada a incorporar o AERI.

    A validação impede que uma variável de ambiente malformada injete novas
    diretivas na CSP. Caminhos, credenciais, query string e fragmentos não são
    aceitos porque ``frame-ancestors`` trabalha com origens, não com URLs.
    HTTPS é obrigatório para domínios públicos; HTTP só é aceito em hosts
    internos (``.local``, localhost ou endereços IP privados/loopback).
    """
    valor = os.getenv("SYNC_ORIGIN", "").strip().rstrip("/")
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


def politica_frame_ancestors() -> str:
    origem_sync = origem_sync_autorizada()
    return f"'self' {origem_sync}" if origem_sync else "'none'"


def politica_samesite_sessao() -> str:
    # Cookies em iframe entre sites exigem SameSite=None e Secure. Quando a
    # incorporação não está configurada, preservamos a política Strict atual.
    return "none" if origem_sync_autorizada() else "strict"


def ip_cliente(request: Request) -> str:
    encaminhado = request.headers.get("x-forwarded-for", "")
    if encaminhado:
        return encaminhado.split(",", 1)[0].strip()[:64]
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
    except Exception:
        # Auditoria nunca deve expor dados nem derrubar a operacao principal.
        pass


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
