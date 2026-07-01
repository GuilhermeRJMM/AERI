from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from backend.app.autenticacao import (
    COOKIE_SESSAO,
    SESSAO_SEGUNDOS,
    autenticar,
    criar_token,
    usuario_atual,
)
from backend.app.database import preparar_banco


router = APIRouter(prefix="/api", tags=["autenticação"])


@router.post("/login")
def login(dados: dict, request: Request):
    preparar_banco()
    usuario = str(dados.get("usuario", "")).strip()
    senha = str(dados.get("senha", ""))
    if not autenticar(usuario, senha):
        raise HTTPException(status_code=401, detail="Usuário ou senha inválidos.")

    resposta = JSONResponse({"usuario": usuario})
    resposta.set_cookie(
        COOKIE_SESSAO,
        criar_token(usuario),
        max_age=SESSAO_SEGUNDOS,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="lax",
    )
    return resposta


@router.get("/sessao")
def sessao(usuario: str = Depends(usuario_atual)):
    return {"usuario": usuario}


@router.post("/logout")
def logout():
    resposta = Response(status_code=204)
    resposta.delete_cookie(COOKIE_SESSAO)
    return resposta
