from fastapi import APIRouter, Depends, HTTPException, Request

from backend.app.autenticacao import exigir_permissao, proteger_csrf
from backend.app.incra import extrair_protocolos
from backend.app.seguranca_web import registrar_auditoria


router = APIRouter(tags=["incra"])


@router.post("/analisar-incra", dependencies=[Depends(proteger_csrf)])
async def analisar_incra(request: Request, usuario: str = Depends(exigir_permissao("processar_incra"))):
    try:
        tamanho = int(request.headers.get("content-length", "0") or 0)
        if tamanho > 15_000_000:
            raise HTTPException(status_code=413, detail="O PDF excede o limite de 15 MB.")
        pdf_bytes = await request.body()
        if len(pdf_bytes) > 15_000_000:
            raise HTTPException(status_code=413, detail="O PDF excede o limite de 15 MB.")
        if not pdf_bytes.startswith(b"%PDF") or b"%%EOF" not in pdf_bytes[-2048:]:
            raise HTTPException(status_code=422, detail="Envie um arquivo PDF válido.")
        resultado = extrair_protocolos(pdf_bytes)
        registrar_auditoria(request, "analisar_incra", "sucesso", usuario)
        return resultado
    except HTTPException:
        raise
    except Exception as exc:
        registrar_auditoria(request, "analisar_incra", "falha", usuario)
        raise HTTPException(status_code=422, detail="Não foi possível processar o PDF.") from exc
