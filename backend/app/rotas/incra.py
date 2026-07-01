from fastapi import APIRouter, Depends, Request

from backend.app.autenticacao import usuario_atual
from backend.app.incra import extrair_protocolos


router = APIRouter(tags=["incra"])


@router.post("/analisar-incra")
async def analisar_incra(request: Request, _usuario: str = Depends(usuario_atual)):
    try:
        pdf_bytes = await request.body()
        if not pdf_bytes.startswith(b"%PDF"):
            return {"erro": "Envie um arquivo PDF válido."}
        return extrair_protocolos(pdf_bytes)
    except Exception as exc:
        return {"erro": str(exc)}
