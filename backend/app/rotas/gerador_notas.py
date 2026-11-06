"""Rotas protegidas do módulo Gerador de Notas."""

import base64
import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse

from backend.app.autenticacao import exigir_permissao, proteger_csrf
from backend.app.database import preparar_banco
from backend.app.gerador_notas.servico import (
    catalogo_para_tela,
    gerar_documento_com_resumo,
    legislacao,
    previa,
    procurar_artigos,
    revisao,
)
from backend.app.seguranca_web import registrar_auditoria


router = APIRouter(
    prefix="/api/gerador-notas",
    tags=["gerador-notas"],
    dependencies=[Depends(preparar_banco)],
)
INTERFACES = Path(__file__).resolve().parents[2] / "private" / "gerador_notas"
MAXIMO_ITENS = 100
MAXIMO_TEXTO_CAMPO = 4_000


def _validar_carga(dados: object, exigir_titulo: bool = False) -> dict:
    if not isinstance(dados, dict):
        raise HTTPException(status_code=422, detail="Dados da nota inválidos.")
    titulo = str(dados.get("titulo", "")).strip()
    protocolo = str(dados.get("protocolo", "")).strip()
    especie = str(dados.get("especie", "")).strip()
    itens = dados.get("itens", [])
    if exigir_titulo and not titulo:
        raise HTTPException(status_code=422, detail="Informe o título apresentado.")
    if len(titulo) > 2_000 or len(protocolo) > 100 or len(especie) > 80:
        raise HTTPException(status_code=422, detail="Um dos campos gerais excede o limite permitido.")
    if not isinstance(itens, list) or len(itens) > MAXIMO_ITENS:
        raise HTTPException(status_code=422, detail="Quantidade de exigências inválida.")
    if exigir_titulo and not itens:
        raise HTTPException(status_code=422, detail="Selecione ao menos uma pendência.")
    for item in itens:
        if not isinstance(item, dict) or not isinstance(item.get("valores", {}), dict):
            raise HTTPException(status_code=422, detail="Exigência inválida.")
        if len(str(item.get("exigencia", ""))) > 100 or len(item.get("valores", {})) > 80:
            raise HTTPException(status_code=422, detail="Exigência excede o limite permitido.")
        if any(len(str(valor)) > MAXIMO_TEXTO_CAMPO for valor in item.get("valores", {}).values()):
            raise HTTPException(status_code=422, detail="Um campo da exigência excede o limite permitido.")
    return {**dados, "titulo": titulo, "protocolo": protocolo, "especie": especie, "itens": itens}


@router.get("/interface", response_class=FileResponse)
def abrir_interface(_usuario: str = Depends(exigir_permissao("acessar_gerador_notas"))):
    return FileResponse(INTERFACES / "index.html", media_type="text/html")


@router.get("/interface/legislacao", response_class=FileResponse)
def abrir_legislacao(_usuario: str = Depends(exigir_permissao("acessar_gerador_notas"))):
    return FileResponse(INTERFACES / "legislacao.html", media_type="text/html")


@router.get("/interface/revisao", response_class=FileResponse)
def abrir_revisao(_usuario: str = Depends(exigir_permissao("acessar_gerador_notas"))):
    return FileResponse(INTERFACES / "revisar.html", media_type="text/html")


@router.get("/catalogo")
def obter_catalogo(_usuario: str = Depends(exigir_permissao("acessar_gerador_notas"))):
    return catalogo_para_tela()


@router.post("/consultar-protocolo", dependencies=[Depends(proteger_csrf)])
def consultar_protocolo_nota(
    dados: dict,
    _usuario: str = Depends(exigir_permissao("acessar_gerador_notas")),
):
    """Consulta somente a descrição literal do título, sem expor partes ou GED."""
    from backend.app.servicos.tri7 import (
        cliente_tri7, ErroTri7, ProtocoloTri7NaoEncontrado,
        ConfiguracaoTri7Invalida, normalizar_numero_matricula,
    )
    valor = dados.get("protocolo")
    if not isinstance(valor, str) or not re.fullmatch(r"(?:[0-9]{1,10}|[0-9]{1,3}(?:\.[0-9]{3}){1,2})", valor.strip()):
        raise HTTPException(422, "Informe um número de protocolo válido.")
    try:
        numero = normalizar_numero_matricula(valor)
    except ValueError:
        raise HTTPException(422, "Informe um número de protocolo válido.") from None
    try:
        protocolo = cliente_tri7().buscar_protocolo_completo(numero)["protocolo"]
    except ProtocoloTri7NaoEncontrado:
        raise HTTPException(404, "Protocolo não encontrado na Tri7. Confira o número ou preencha o título manualmente.") from None
    except ConfiguracaoTri7Invalida:
        raise HTTPException(503, "Consulta à Tri7 indisponível. O preenchimento manual continua disponível.") from None
    except ErroTri7:
        raise HTTPException(502, "Não foi possível consultar a Tri7. Tente novamente ou preencha o título manualmente.") from None
    try:
        if normalizar_numero_matricula(protocolo.get("protocolo_numero")) != numero:
            raise ValueError()
    except ValueError:
        raise HTTPException(502, "A Tri7 não confirmou o protocolo solicitado. Nenhum campo foi preenchido.") from None
    titulo = protocolo.get("descricao_titulo")
    titulo = re.sub(r"\s+", " ", titulo).strip() if isinstance(titulo, str) else ""
    if len(titulo) > 2000:
        raise HTTPException(502, "A descrição do título excede o tamanho permitido. Preencha manualmente.")
    return {"protocolo": numero, "titulo": titulo, "fonte": "Tri7 · descrição do título"}


@router.get("/legislacao")
def obter_legislacao(_usuario: str = Depends(exigir_permissao("acessar_gerador_notas"))):
    return legislacao()


@router.get("/artigos")
def buscar_artigos(
    norma: str = Query(max_length=80),
    q: str = Query(default="", max_length=160),
    _usuario: str = Depends(exigir_permissao("acessar_gerador_notas")),
):
    return procurar_artigos(norma, q)


@router.get("/revisao")
def obter_revisao(_usuario: str = Depends(exigir_permissao("acessar_gerador_notas"))):
    return revisao()


@router.post("/previa", dependencies=[Depends(proteger_csrf)])
def gerar_previa(
    dados: dict,
    _usuario: str = Depends(exigir_permissao("acessar_gerador_notas")),
):
    try:
        return previa(_validar_carga(dados))
    except (KeyError, ValueError) as erro:
        raise HTTPException(status_code=422, detail=str(erro)) from erro


@router.post("/gerar", dependencies=[Depends(proteger_csrf)])
def gerar_nota(
    dados: dict,
    request: Request,
    usuario: str = Depends(exigir_permissao("acessar_gerador_notas")),
):
    carga = _validar_carga(dados, exigir_titulo=True)
    try:
        nome, conteudo, nao_revisadas, resumo = gerar_documento_com_resumo(carga)
    except (KeyError, ValueError, FileNotFoundError) as erro:
        raise HTTPException(status_code=422, detail=str(erro)) from erro
    registrar_auditoria(
        request,
        "gerar_nota_devolutiva",
        "sucesso",
        usuario,
        carga.get("protocolo") or None,
        {"especie": carga["especie"], "quantidade_exigencias": len(carga["itens"]),
         "resumo_incluido": True, "versao_resumo": resumo['versao']},
    )
    return {
        "ok": True,
        "arquivo": nome,
        "conteudo": base64.b64encode(conteudo).decode("ascii"),
        "nao_revisadas": nao_revisadas,
        "resumo": resumo,
        "resumo_incluido": True,
    }
