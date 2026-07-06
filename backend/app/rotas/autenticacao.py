from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from backend.app.autenticacao import (
    COOKIE_SESSAO,
    SESSAO_SEGUNDOS,
    autenticar,
    criar_sessao,
    permissoes_sessao,
    proteger_csrf,
    registrar_tentativa,
    renovar_csrf,
    revogar_sessao,
    usuario_atual,
    verificar_bloqueio,
)
from backend.app.database import conectar, preparar_banco
from backend.app.seguranca_web import ip_cliente, registrar_auditoria, validar_origem


router = APIRouter(prefix="/api", tags=["autenticação"])


@router.post("/login")
def login(dados: dict, request: Request):
    preparar_banco()
    validar_origem(request)
    usuario = str(dados.get("usuario", "")).strip().upper()[:80]
    senha = str(dados.get("senha", ""))[:256]
    ip = ip_cliente(request)
    restantes = verificar_bloqueio(usuario, ip)
    if restantes <= 0:
        registrar_auditoria(request, "login", "bloqueado", usuario)
        raise HTTPException(status_code=429, detail="Muitas tentativas. Aguarde 15 minutos.")
    if not autenticar(usuario, senha):
        registrar_tentativa(usuario, ip, False)
        registrar_auditoria(request, "login", "falha", usuario)
        raise HTTPException(status_code=401, detail="Usuário ou senha inválidos.")

    registrar_tentativa(usuario, ip, True)
    token, csrf = criar_sessao(usuario, request)
    registrar_auditoria(request, "login", "sucesso", usuario)
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(
                """SELECT nome, perfil, deve_trocar_senha,
                pode_processar_matricula, pode_processar_incra, pode_ver_intimacoes,
                pode_criar_intimacoes, pode_alterar_intimacoes, pode_conferir_intimacoes
                FROM usuarios_aeri WHERE usuario=%s""",
                (usuario,),
            )
            conta = cursor.fetchone()
    resposta = JSONResponse({
        "usuario": usuario, "nome": conta["nome"], "perfil": conta["perfil"],
        "deveTrocarSenha": conta["deve_trocar_senha"], "csrfToken": csrf,
        "permissoes": permissoes_sessao(conta),
    })
    resposta.set_cookie(
        COOKIE_SESSAO, token, max_age=SESSAO_SEGUNDOS, httponly=True,
        secure=True, samesite="strict", path="/",
    )
    return resposta


@router.get("/sessao", dependencies=[Depends(preparar_banco)])
def sessao(request: Request, usuario: str = Depends(usuario_atual)):
    conta = request.state.sessao
    return {
        "usuario": usuario, "nome": conta["nome"], "perfil": conta["perfil"],
        "deveTrocarSenha": conta["deve_trocar_senha"], "csrfToken": renovar_csrf(request),
        "permissoes": permissoes_sessao(conta),
    }


@router.post("/logout", dependencies=[Depends(usuario_atual), Depends(proteger_csrf)])
def logout(request: Request):
    usuario = request.state.sessao["usuario"]
    revogar_sessao(request)
    registrar_auditoria(request, "logout", "sucesso", usuario)
    resposta = Response(status_code=204)
    resposta.delete_cookie(COOKIE_SESSAO, path="/", secure=True, samesite="strict")
    return resposta
