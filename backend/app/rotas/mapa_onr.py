from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse

from backend.app.autenticacao import exigir_permissao, proteger_csrf
from backend.app.database import preparar_banco
from backend.app.seguranca_web import registrar_auditoria
from backend.app.servicos.analise_matricula import analisar_matricula
from backend.app.servicos.mapa_onr import construir_contexto_mapa_onr
from backend.app.servicos.tri7 import (
    ConfiguracaoTri7Invalida,
    ErroTri7,
    MatriculaTri7NaoEncontrada,
    MatriculaTri7SemTexto,
    cliente_tri7,
    normalizar_numero_matricula,
)


router = APIRouter(
    prefix="/api/mapa-onr",
    tags=["mapa-onr"],
    dependencies=[Depends(preparar_banco)],
)
CONVERSOR_HTML = Path(__file__).resolve().parents[2] / "private" / "mapa_onr.html"


@router.get("/conversor", response_class=FileResponse)
def abrir_conversor_mapa_onr(
    _usuario: str = Depends(exigir_permissao("acessar_mapa_onr")),
):
    return FileResponse(CONVERSOR_HTML, media_type="text/html")


@router.post("/matricula", dependencies=[Depends(proteger_csrf)])
def consultar_matricula_mapa_onr(
    dados: dict,
    request: Request,
    usuario: str = Depends(exigir_permissao("acessar_mapa_onr")),
):
    try:
        numero = normalizar_numero_matricula(dados.get("numero_matricula"))
    except ValueError as erro:
        raise HTTPException(status_code=422, detail=str(erro)) from erro

    try:
        matricula = cliente_tri7().buscar_texto_matricula(numero)
    except (MatriculaTri7NaoEncontrada, MatriculaTri7SemTexto) as erro:
        raise HTTPException(status_code=404, detail=str(erro)) from erro
    except ConfiguracaoTri7Invalida as erro:
        raise HTTPException(status_code=503, detail=str(erro)) from erro
    except ErroTri7 as erro:
        raise HTTPException(status_code=502, detail=str(erro)) from erro

    texto = matricula["texto"]
    resultado_aeri = analisar_matricula(
        texto,
        numero_matricula=matricula["numero_matricula"],
    )
    tipo = str(resultado_aeri.get("imovel", {}).get("tipo", "")).lower()
    registrar_auditoria(
        request,
        "consultar_matricula_mapa_onr",
        "sucesso",
        usuario,
        numero,
    )
    return {
        "numero_matricula": matricula["numero_matricula"],
        "tipo_imovel": tipo if tipo in {"rural", "urbano"} else None,
        "texto": texto,
        "contexto_aeri": construir_contexto_mapa_onr(texto, resultado_aeri),
    }
