import os

from fastapi import HTTPException, Request
from psycopg.types.json import Jsonb

from backend.app.database import conectar


METODOS_SEGUROS = {"GET", "HEAD", "OPTIONS"}


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
                cursor.execute(
                    """INSERT INTO auditoria_aeri
                    (usuario, acao, recurso, resultado, ip, detalhes)
                    VALUES (%s, %s, %s, %s, %s, %s)""",
                    (usuario, acao, recurso, resultado, ip_cliente(request), Jsonb(detalhes or {})),
                )
            conexao.commit()
    except Exception:
        # Auditoria nunca deve expor dados nem derrubar a operacao principal.
        pass


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
