from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from backend.app.autenticacao import (
    COOKIE_SESSAO,
    MAX_TENTATIVAS,
    SESSAO_SEGUNDOS,
    contar_tentativas_invalidas,
    criar_sessao_cursor,
    hash_senha,
    permissoes_sessao,
    proteger_csrf,
    registrar_tentativa_cursor,
    renovar_csrf,
    revogar_sessao,
    usuario_atual,
    verificar_senha_login,
)
from backend.app.database import conectar, preparar_banco
from backend.app.seguranca_web import (
    ip_cliente,
    registrar_auditoria,
    registrar_auditoria_cursor,
    validar_origem,
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
                """SELECT usuario, senha_hash, nome, perfil, deve_trocar_senha,
                pode_processar_matricula, pode_processar_incra, pode_ver_intimacoes,
                pode_criar_intimacoes, pode_alterar_intimacoes, pode_conferir_intimacoes
                FROM usuarios_aeri WHERE UPPER(usuario)=UPPER(%s) AND ativo=TRUE""",
                (usuario,),
            )
            conta = cursor.fetchone()
            if not verificar_senha_login(senha, conta):
                registrar_tentativa_cursor(cursor, usuario, ip, False)
                registrar_auditoria_cursor(cursor, request, "login", "falha", usuario)
                conexao.commit()
                raise HTTPException(status_code=401, detail="Usuário ou senha inválidos.")

            if not conta["senha_hash"].startswith("$argon2id$"):
                cursor.execute(
                    "UPDATE usuarios_aeri SET senha_hash=%s WHERE usuario=%s",
                    (hash_senha(senha), conta["usuario"]),
                )
            registrar_tentativa_cursor(cursor, conta["usuario"], ip, True)
            token, csrf = criar_sessao_cursor(cursor, conta["usuario"], request)
            registrar_auditoria_cursor(cursor, request, "login", "sucesso", conta["usuario"])
        conexao.commit()

    resposta = JSONResponse({
        "usuario": conta["usuario"], "nome": conta["nome"], "perfil": conta["perfil"],
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
