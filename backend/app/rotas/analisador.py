from fastapi import APIRouter, Depends, HTTPException, Request

from backend.app.autenticacao import exigir_permissao, proteger_csrf
from backend.app.seguranca_web import registrar_auditoria
from backend.app.servicos.analise_matricula import analisar_matricula


router = APIRouter(tags=["analisador"])


@router.post("/analisar", dependencies=[Depends(proteger_csrf)])
def analisar(dados: dict, request: Request, usuario: str = Depends(exigir_permissao("processar_matricula"))):
    texto = str(dados.get("texto", ""))
    if not texto.strip() or len(texto) > 5_000_000:
        raise HTTPException(status_code=413, detail="A matrícula excede o limite permitido.")
    resultado = analisar_matricula(texto)
    registrar_auditoria(request, "analisar_matricula", "sucesso", usuario)
    return resultado
