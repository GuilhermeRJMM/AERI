from fastapi import APIRouter, Depends

from backend.app.autenticacao import usuario_atual
from backend.app.servicos.analise_matricula import analisar_matricula


router = APIRouter(tags=["analisador"])


@router.post("/analisar")
def analisar(dados: dict, _usuario: str = Depends(usuario_atual)):
    return analisar_matricula(str(dados.get("texto", "")))
