import json
from datetime import datetime, timezone
from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse

from backend.app.autenticacao import (
    COOKIE_SESSAO,
    MAX_TENTATIVAS,
    SESSAO_SEGUNDOS,
    contar_tentativas_invalidas,
    criar_sessao_cursor,
    hash_senha,
    csrf_atual,
    permissoes_sessao,
    proteger_csrf,
    registrar_tentativa_cursor,
    revogar_sessao,
    usuario_atual,
    verificar_senha_login,
)
from backend.app.database import conectar, preparar_banco
from backend.app.permissoes import permissoes_efetivas_cursor
from backend.app.seguranca_web import (
    ip_cliente,
    politica_samesite_sessao,
    registrar_auditoria,
    registrar_auditoria_cursor,
    validar_origem,
)
from backend.app.seguranca_mfa import decifrar_segredo, validar_totp
from backend.app.servicos.sso_sync import (
    SsoSyncConfiguracaoInvalida,
    SsoSyncTicketInvalido,
    validar_ticket_sync,
)


router = APIRouter(prefix="/api", tags=["autenticação"])


@router.post("/login")
def login(dados: dict, request: Request):
    preparar_banco()
    validar_origem(request)
    usuario = str(dados.get("usuario", "")).strip().upper()[:80]
    senha = str(dados.get("senha", ""))[:256]
    ip = ip_cliente(request)

    with conectar() as conexao:
        with conexao.cursor() as cursor:
            if contar_tentativas_invalidas(cursor, usuario, ip) >= MAX_TENTATIVAS:
                registrar_auditoria_cursor(cursor, request, "login", "bloqueado", usuario)
                conexao.commit()
                raise HTTPException(status_code=429, detail="Muitas tentativas. Aguarde 15 minutos.")

            cursor.execute(
                """SELECT * FROM usuarios_aeri
                WHERE UPPER(usuario)=UPPER(%s) AND ativo=TRUE""",
                (usuario,),
            )
            conta = cursor.fetchone()
            if not verificar_senha_login(senha, conta):
                registrar_tentativa_cursor(cursor, usuario, ip, False)
                registrar_auditoria_cursor(cursor, request, "login", "falha", usuario)
                conexao.commit()
                raise HTTPException(status_code=401, detail="Usuário ou senha inválidos.")

            if (
                conta.get("deve_trocar_senha")
                and conta.get("senha_temporaria_expira_em")
                and conta["senha_temporaria_expira_em"] <= datetime.now(timezone.utc)
            ):
                registrar_auditoria_cursor(cursor, request, "login", "senha_temporaria_expirada", conta["usuario"])
                conexao.commit()
                raise HTTPException(
                    status_code=403,
                    detail="A senha temporária expirou. Solicite uma nova ao administrador.",
                )

            if conta.get("mfa_ativo"):
                try:
                    valido_mfa = validar_totp(
                        decifrar_segredo(conta["mfa_segredo_criptografado"]), dados.get("codigoMfa"),
                    )
                except RuntimeError as erro:
                    registrar_auditoria_cursor(cursor, request, "login", "falha_mfa_configuracao", conta["usuario"])
                    conexao.commit()
                    raise HTTPException(status_code=503, detail=str(erro)) from erro
                if not valido_mfa:
                    registrar_tentativa_cursor(cursor, conta["usuario"], ip, False)
                    registrar_auditoria_cursor(cursor, request, "login", "mfa_pendente", conta["usuario"])
                    conexao.commit()
                    raise HTTPException(status_code=428, detail="Informe o código de 6 dígitos do autenticador.")

            if not conta["senha_hash"].startswith("$argon2id$"):
                cursor.execute(
                    "UPDATE usuarios_aeri SET senha_hash=%s WHERE usuario=%s",
                    (hash_senha(senha), conta["usuario"]),
                )
            conta["permissoes_relacionais"] = permissoes_efetivas_cursor(
                cursor, conta["usuario"], conta["perfil"]
            )
            registrar_tentativa_cursor(cursor, conta["usuario"], ip, True)
            token, csrf = criar_sessao_cursor(cursor, conta["usuario"], request)
            registrar_auditoria_cursor(cursor, request, "login", "sucesso", conta["usuario"])
        conexao.commit()

    resposta = JSONResponse({
        "usuario": conta["usuario"], "nome": conta["nome"], "perfil": conta["perfil"], "cargo": conta["perfil"],
        "deveTrocarSenha": conta["deve_trocar_senha"], "csrfToken": csrf,
        "mfaAtivo": bool(conta.get("mfa_ativo")),
        "permissoes": permissoes_sessao(conta),
    })
    resposta.set_cookie(
        COOKIE_SESSAO, token, max_age=SESSAO_SEGUNDOS, httponly=True,
        secure=True, samesite=politica_samesite_sessao(), path="/",
    )
    return resposta


async def _ler_ticket_sync(request: Request) -> str:
    corpo = await request.body()
    if not corpo or len(corpo) > 10_000:
        raise HTTPException(status_code=400, detail="Solicitação de acesso do Sync inválida.")
    tipo = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    try:
        if tipo == "application/x-www-form-urlencoded":
            campos = parse_qs(corpo.decode("utf-8"), keep_blank_values=True, max_num_fields=8)
            ticket = (campos.get("ticket") or [""])[0]
        elif tipo == "application/json":
            dados = json.loads(corpo.decode("utf-8"))
            ticket = dados.get("ticket", "") if isinstance(dados, dict) else ""
        else:
            raise HTTPException(status_code=415, detail="Envie o ticket do Sync como formulário ou JSON.")
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as erro:
        raise HTTPException(status_code=400, detail="Solicitação de acesso do Sync inválida.") from erro
    if not isinstance(ticket, str) or not ticket.strip():
        raise HTTPException(status_code=400, detail="Ticket do Sync não informado.")
    return ticket.strip()


@router.post("/login/sync")
async def login_sync(request: Request):
    """Abre a sessão AERI a partir de ticket assinado e de uso único do Sync.

    O endpoint não aceita senha nem usa sessão do Sync diretamente. O ticket
    é validado com a chave pública e consumido no mesmo commit da sessão AERI.
    """
    ticket_bruto = await _ler_ticket_sync(request)
    try:
        ticket = validar_ticket_sync(ticket_bruto)
    except SsoSyncConfiguracaoInvalida as erro:
        raise HTTPException(status_code=503, detail=str(erro)) from erro
    except SsoSyncTicketInvalido as erro:
        raise HTTPException(status_code=401, detail="O acesso enviado pelo Sync é inválido ou expirou.") from erro

    preparar_banco()
    estado_erro = None
    sessao_nova = None
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(
                """INSERT INTO tickets_sso_sync_aeri (jti_hash, expira_em)
                VALUES (%s, to_timestamp(%s))
                ON CONFLICT (jti_hash) DO NOTHING
                RETURNING jti_hash""",
                (ticket.jti_hash, ticket.expira_em),
            )
            ticket_novo = cursor.fetchone()
            if not ticket_novo:
                estado_erro = (409, "Este acesso do Sync já foi utilizado. Gere um novo acesso no Sync.")
                registrar_auditoria_cursor(
                    cursor, request, "login_sync", "ticket_reutilizado", ticket.usuario,
                    detalhes={"origem": "SYNC"},
                )
            else:
                cursor.execute(
                    """SELECT * FROM usuarios_aeri
                    WHERE UPPER(usuario)=UPPER(%s) AND ativo=TRUE""",
                    (ticket.usuario,),
                )
                conta = cursor.fetchone()
                if not conta:
                    estado_erro = (403, "Seu usuário do Sync ainda não está habilitado no AERI.")
                    registrar_auditoria_cursor(
                        cursor, request, "login_sync", "usuario_nao_habilitado", ticket.usuario,
                        detalhes={"origem": "SYNC"},
                    )
                elif conta.get("mfa_ativo") and "mfa" not in ticket.metodos_autenticacao:
                    estado_erro = (403, "O Sync precisa confirmar a autenticação em dois fatores para este usuário.")
                    registrar_auditoria_cursor(
                        cursor, request, "login_sync", "mfa_nao_confirmado", conta["usuario"],
                        detalhes={"origem": "SYNC"},
                    )
                else:
                    conta["permissoes_relacionais"] = permissoes_efetivas_cursor(
                        cursor, conta["usuario"], conta["perfil"]
                    )
                    token_sessao, csrf = criar_sessao_cursor(cursor, conta["usuario"], request)
                    sessao_nova = (token_sessao, csrf)
                    registrar_auditoria_cursor(
                        cursor, request, "login_sync", "sucesso", conta["usuario"],
                        detalhes={"origem": "SYNC"},
                    )
        conexao.commit()

    if estado_erro:
        raise HTTPException(status_code=estado_erro[0], detail=estado_erro[1])
    if not sessao_nova:
        raise HTTPException(status_code=500, detail="Não foi possível iniciar a sessão do AERI.")

    token_sessao, _csrf = sessao_nova
    resposta = RedirectResponse("/", status_code=303)
    resposta.set_cookie(
        COOKIE_SESSAO, token_sessao, max_age=SESSAO_SEGUNDOS, httponly=True,
        secure=True,
        # Lax permite a navegação de retorno do POST iniciado no Sync. Para
        # incorporação em iframe, a configuração existente de SYNC_ORIGINS
        # muda a política para None (sempre Secure).
        samesite=("lax" if politica_samesite_sessao() == "strict" else politica_samesite_sessao()),
        path="/",
    )
    resposta.headers["Cache-Control"] = "no-store"
    resposta.headers["Pragma"] = "no-cache"
    resposta.headers["Referrer-Policy"] = "no-referrer"
    return resposta


@router.get("/sessao", dependencies=[Depends(preparar_banco)])
def sessao(request: Request, usuario: str = Depends(usuario_atual)):
    conta = request.state.sessao
    return {
        "usuario": usuario, "nome": conta["nome"], "perfil": conta["perfil"], "cargo": conta["perfil"],
        "deveTrocarSenha": conta["deve_trocar_senha"], "csrfToken": csrf_atual(request),
        "mfaAtivo": bool(conta.get("mfa_ativo")),
        "permissoes": permissoes_sessao(conta),
    }


@router.post("/logout", dependencies=[Depends(usuario_atual), Depends(proteger_csrf)])
def logout(request: Request):
    usuario = request.state.sessao["usuario"]
    revogar_sessao(request)
    registrar_auditoria(request, "logout", "sucesso", usuario)
    resposta = Response(status_code=204)
    resposta.delete_cookie(
        COOKIE_SESSAO,
        path="/",
        secure=True,
        samesite=politica_samesite_sessao(),
    )
    return resposta
