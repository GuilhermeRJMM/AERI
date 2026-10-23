"""Troca same-origin HUB → sessão normal AERI. Nunca recebe ticket em URL."""
import hashlib
import time

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from psycopg import Error as ErroPostgres
from starlette.concurrency import run_in_threadpool

from backend.app.autenticacao import COOKIE_SESSAO, SESSAO_SEGUNDOS, criar_sessao_cursor
from backend.app.database import conectar, preparar_banco
from backend.app.seguranca_web import politica_samesite_sessao, registrar_auditoria_cursor
from backend.app.servicos.sso_hub import (
    ConfiguracaoHubInvalida, TicketHubInvalido, LIMITE_CORPO, TOLERANCIA_SEGUNDOS,
    objeto_json, validar_ticket_hub,
)

router = APIRouter(prefix="/api/auth/hub", tags=["autenticação"])
ORIGEM = "https://aeri-two.vercel.app"
HOST = "aeri-two.vercel.app"
ERRO_ACESSO = "Não foi possível autenticar pelo HUB."


def _falha(status):
    return HTTPException(status_code=status, detail=ERRO_ACESSO, headers={"Cache-Control": "no-store"})


async def _ler_entrada(request):
    # Não confiar em X-Forwarded-Host enviado pelo chamador. A Vercel deve
    # preservar o Host público; outros domínios/previews não aceitam tickets.
    for nome, esperado in (("origin", ORIGEM), ("host", HOST), ("content-type", "application/json")):
        valores = request.headers.getlist(nome)
        if valores != [esperado]:
            raise _falha(415 if nome == "content-type" else 403)
    if request.url.query:
        raise _falha(400)
    tamanho = request.headers.get("content-length")
    if tamanho is not None:
        if not tamanho.isascii() or not tamanho.isdecimal():
            raise _falha(400)
        if len(tamanho) > 10 or int(tamanho) > LIMITE_CORPO:
            raise _falha(413)
    corpo = bytearray()
    async for trecho in request.stream():
        if len(corpo) + len(trecho) > LIMITE_CORPO:
            raise _falha(413)
        corpo.extend(trecho)
    try:
        dados = objeto_json(bytes(corpo).decode("utf-8"))
        if set(dados) != {"ticket"} or not isinstance(dados["ticket"], str):
            raise TicketHubInvalido()
        return validar_ticket_hub(dados["ticket"])
    except ConfiguracaoHubInvalida:
        raise _falha(503) from None
    except (TicketHubInvalido, UnicodeError):
        raise _falha(401) from None


def _trocar_sessao(ticket, request):
    try:
        preparar_banco()
        with conectar() as conexao:
            with conexao.cursor() as cursor:
                cursor.execute(
                    """SELECT u.usuario FROM vinculos_sso_hub_aeri v
                    JOIN usuarios_aeri u ON u.usuario=v.usuario
                    WHERE v.emissor='sync-hub' AND v.subject=%s AND u.ativo=TRUE
                    FOR UPDATE OF v, u""", (ticket.sub,),
                )
                conta = cursor.fetchone()
                if not conta:
                    raise _falha(401)
                # Uma espera por lock no banco não estende a validade.
                if ticket.exp <= int(time.time()) - TOLERANCIA_SEGUNDOS:
                    raise _falha(401)
                cursor.execute(
                    "DELETE FROM tickets_sso_hub_aeri WHERE expira_em < NOW()",
                )
                cursor.execute(
                    """INSERT INTO tickets_sso_hub_aeri (emissor, jti, expira_em)
                    VALUES ('sync-hub', %s, to_timestamp(%s))
                    ON CONFLICT (emissor, jti) DO NOTHING RETURNING jti""",
                    (ticket.jti, ticket.exp + TOLERANCIA_SEGUNDOS),
                )
                if not cursor.fetchone():
                    raise _falha(401)
                anterior = request.cookies.get(COOKIE_SESSAO)
                if anterior:
                    cursor.execute(
                        "UPDATE sessoes_aeri SET revogada_em=NOW() WHERE token_hash=%s AND revogada_em IS NULL",
                        (hashlib.sha256(anterior.encode()).hexdigest(),),
                    )
                token, _csrf = criar_sessao_cursor(cursor, conta["usuario"], request)
                registrar_auditoria_cursor(cursor, request, "login_hub", "sucesso", conta["usuario"])
            conexao.commit()
    except ErroPostgres:
        # Não propagar SQL, parâmetros, conta ou credenciais para resposta/log.
        raise _falha(503) from None
    resposta = JSONResponse({"ok": True}, headers={"Cache-Control": "no-store", "Pragma": "no-cache"})
    resposta.set_cookie(
        COOKIE_SESSAO, token, max_age=SESSAO_SEGUNDOS, httponly=True,
        secure=True, samesite=politica_samesite_sessao(), path="/",
    )
    return resposta


@router.post("/exchange")
async def trocar_ticket(request: Request):
    ticket = await _ler_entrada(request)
    # O acesso síncrono ao Postgres não deve bloquear o event loop FastAPI.
    return await run_in_threadpool(_trocar_sessao, ticket, request)
