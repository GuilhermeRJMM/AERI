import re
import sys
from datetime import date, datetime
from zoneinfo import ZoneInfo
from pathlib import Path
from uuid import UUID, uuid4

# --- GPS PARA O VERCEL ---
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from psycopg.errors import UniqueViolation
from psycopg.types.json import Jsonb

# --- IMPORTAÇÕES COM O CAMINHO CORRETO ---
from backend.app.parser import separar_atos
from backend.app.regras import classificar
from backend.app.cancelamentos import aplicar_cancelamentos
from backend.app.modelos import Ato
from backend.app.proprietarios import calcular_cadeia_dominial
from backend.app.incra import extrair_protocolos
from backend.app.autenticacao import (
    COOKIE_SESSAO,
    SESSAO_SEGUNDOS,
    autenticar,
    criar_token,
    usuario_atual,
)
from backend.app.database import conectar, preparar_banco

app = FastAPI()

BASE_DIR = Path(__file__).resolve().parent.parent

app.mount(
    "/static",
    StaticFiles(directory=str(BASE_DIR / "static")),
    name="static"
)

templates = Jinja2Templates(
    directory=str(BASE_DIR / "templates")
)

@app.post("/analisar-incra")
async def analisar_incra(request: Request, _usuario: str = Depends(usuario_atual)):
    try:
        pdf_bytes = await request.body()
        if not pdf_bytes.startswith(b"%PDF"):
            return {"erro": "Envie um arquivo PDF válido."}
        return extrair_protocolos(pdf_bytes)
    except Exception as exc:
        return {"erro": str(exc)}

@app.get("/")
def home(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html"
    )

@app.post("/analisar")
def analisar(dados: dict, _usuario: str = Depends(usuario_atual)):
    texto = dados.get("texto", "")
    separados = separar_atos(texto)
    atos = []

    for item in separados:
        categoria, impacta = classificar(item["texto"])
        atos.append(
            Ato(
                codigo=item["codigo"],
                descricao=item["texto"],
                categoria=categoria,
                impacta_resultado=impacta
            )
        )

    atos = aplicar_cancelamentos(atos)

    tem_onus = any(
        a.categoria in ["ÔNUS", "RESTRIÇÃO"] and a.status == "ATIVO" 
        for a in atos
    )
    
    tem_publicidade = any(
        a.categoria == "PUBLICIDADE" and a.status == "ATIVO" 
        for a in atos
    )

    if tem_onus:
        resultado_final = "POSITIVA PARA ÔNUS"
    elif tem_publicidade:
        resultado_final = "NEGATIVA, PORÉM COM PUBLICIDADE"
    else:
        resultado_final = "NEGATIVA PARA ÔNUS"

    categorias_permitidas = ["ÔNUS", "RESTRIÇÃO", "PUBLICIDADE", "CANCELAMENTO"]
    
    atos_filtrados = [
        a.model_dump() if hasattr(a, 'model_dump') else a.dict()
        for a in atos if a.categoria in categorias_permitidas
    ]

    # Processamento simultâneo da Cadeia Dominial
    lista_proprietarios = calcular_cadeia_dominial(atos, texto)

    resposta = {
        "resultado": resultado_final,
        "publicidade": "COM PUBLICIDADE" if tem_publicidade else "SEM PUBLICIDADE",
        "atos": atos_filtrados,
        "proprietarios_atuais": lista_proprietarios
    }

    return resposta


@app.post("/api/login")
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


@app.get("/api/sessao")
def sessao(usuario: str = Depends(usuario_atual)):
    return {"usuario": usuario}


@app.post("/api/logout")
def logout():
    resposta = Response(status_code=204)
    resposta.delete_cookie(COOKIE_SESSAO)
    return resposta


def intimacao_json(registro: dict) -> dict:
    return {
        "id": str(registro["id"]),
        "protocolo": registro["protocolo"],
        "credor": registro["credor"],
        "devedor": registro["devedor"],
        "ultimoAndamento": registro["ultimo_andamento"].isoformat(),
        "ultimaConferencia": registro["ultima_conferencia"].isoformat() if registro["ultima_conferencia"] else None,
        "historico": registro["historico"] or [],
    }


def validar_intimacao(dados: dict) -> tuple[str, str, str, date]:
    protocolo = str(dados.get("protocolo", "")).strip().upper()
    credor = str(dados.get("credor", "")).strip()
    devedor = str(dados.get("devedor", "")).strip()
    try:
        andamento = date.fromisoformat(str(dados.get("ultimoAndamento", "")))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Data do último andamento inválida.") from exc
    if not re.fullmatch(r"IN\d{8}C", protocolo):
        raise HTTPException(status_code=422, detail="Use o protocolo no padrão IN01625306C.")
    if not credor or not devedor or len(credor) > 160 or len(devedor) > 160:
        raise HTTPException(status_code=422, detail="Informe credor e devedor válidos.")
    return protocolo, credor, devedor, andamento


@app.get("/api/intimacoes")
def listar_intimacoes(_usuario: str = Depends(usuario_atual)):
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute("SELECT * FROM intimacoes_aeri ORDER BY protocolo")
            return [intimacao_json(item) for item in cursor.fetchall()]


@app.post("/api/intimacoes", status_code=201)
def criar_intimacao(dados: dict, _usuario: str = Depends(usuario_atual)):
    protocolo, credor, devedor, andamento = validar_intimacao(dados)
    identificador = uuid4()
    try:
        with conectar() as conexao:
            with conexao.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO intimacoes_aeri
                    (id, protocolo, credor, devedor, ultimo_andamento)
                    VALUES (%s, %s, %s, %s, %s) RETURNING *""",
                    (identificador, protocolo, credor, devedor, andamento),
                )
                item = cursor.fetchone()
            conexao.commit()
    except UniqueViolation as exc:
        raise HTTPException(status_code=409, detail="Este protocolo já está cadastrado.") from exc
    return intimacao_json(item)


@app.put("/api/intimacoes/{identificador}")
def atualizar_intimacao(identificador: UUID, dados: dict, _usuario: str = Depends(usuario_atual)):
    protocolo, credor, devedor, andamento = validar_intimacao(dados)
    try:
        with conectar() as conexao:
            with conexao.cursor() as cursor:
                cursor.execute(
                    """UPDATE intimacoes_aeri SET protocolo=%s, credor=%s, devedor=%s,
                    ultimo_andamento=%s, atualizado_em=NOW() WHERE id=%s RETURNING *""",
                    (protocolo, credor, devedor, andamento, identificador),
                )
                item = cursor.fetchone()
            conexao.commit()
    except UniqueViolation as exc:
        raise HTTPException(status_code=409, detail="Este protocolo já está cadastrado.") from exc
    if not item:
        raise HTTPException(status_code=404, detail="Intimação não encontrada.")
    return intimacao_json(item)


@app.post("/api/intimacoes/{identificador}/conferir")
def conferir_intimacao(identificador: UUID, _usuario: str = Depends(usuario_atual)):
    hoje = datetime.now(ZoneInfo("America/Sao_Paulo")).date().isoformat()
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute("SELECT historico FROM intimacoes_aeri WHERE id=%s", (identificador,))
            atual = cursor.fetchone()
            if not atual:
                raise HTTPException(status_code=404, detail="Intimação não encontrada.")
            historico = list(dict.fromkeys([*(atual["historico"] or []), hoje]))
            cursor.execute(
                """UPDATE intimacoes_aeri SET ultima_conferencia=%s, historico=%s,
                atualizado_em=NOW() WHERE id=%s RETURNING *""",
                (hoje, Jsonb(historico), identificador),
            )
            item = cursor.fetchone()
        conexao.commit()
    return intimacao_json(item)


@app.delete("/api/intimacoes/{identificador}", status_code=204)
def excluir_intimacao(identificador: UUID, _usuario: str = Depends(usuario_atual)):
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute("DELETE FROM intimacoes_aeri WHERE id=%s", (identificador,))
            removidos = cursor.rowcount
        conexao.commit()
    if not removidos:
        raise HTTPException(status_code=404, detail="Intimação não encontrada.")
    return Response(status_code=204)
