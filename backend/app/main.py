import sys
import logging
import time
from pathlib import Path
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from backend.app.rotas import (
    analisador, autenticacao, buscas, custas, gerador_notas, incra, intimacoes,
    livro_protocolos, registros_auxiliares, mapa_onr, poligonos, status_onr, usuarios,
)
from backend.app.seguranca_web import politica_frame_ancestors
from backend.app.database import conectar


BASE_DIR = Path(__file__).resolve().parent.parent

# Únicos hosts externos que o AERI carrega, e só como imagem: os tiles do
# módulo Polígonos. Ficam nomeados um a um em vez de um curinga https:
# porque img-src aberto transformaria qualquer XSS futuro num canal de
# exfiltração -- basta montar a URL de uma imagem com o dado dentro.
# Nenhum deles entra em script-src ou connect-src.
SERVIDORES_DE_TILE = " ".join((
    "https://server.arcgisonline.com",      # Esri World Imagery (satélite)
    "https://services.arcgisonline.com",    # espelho do mesmo serviço
    "https://mt0.google.com",               # Google (satélite HD)
    "https://mt1.google.com",
    "https://mt2.google.com",
    "https://mt3.google.com",
    "https://bdgex.eb.mil.br",              # Exército Brasileiro (topográfico)
    "https://tile.openstreetmap.org",       # OpenStreetMap (ruas)
))

app = FastAPI(title="AERI")
logger = logging.getLogger("aeri.http")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app.include_router(autenticacao.router)
app.include_router(analisador.router)
app.include_router(buscas.router)
app.include_router(incra.router)
app.include_router(custas.router)
app.include_router(registros_auxiliares.router)
app.include_router(livro_protocolos.router)
app.include_router(mapa_onr.router)
app.include_router(gerador_notas.router)
app.include_router(poligonos.router)
app.include_router(intimacoes.router)
app.include_router(status_onr.router)
app.include_router(usuarios.router)


@app.middleware("http")
async def seguranca_http(request: Request, call_next):
    request_id = str(uuid4())
    request.state.request_id = request_id
    inicio = time.perf_counter()
    try:
        tamanho = int(request.headers.get("content-length", "0") or 0)
    except ValueError:
        tamanho = -1
    if tamanho < 0:
        resposta = JSONResponse({"detail": "Cabeçalho de tamanho inválido."}, status_code=400)
    elif tamanho > 16_000_000:
        resposta = JSONResponse({"detail": "Requisição excede o limite permitido."}, status_code=413)
    else:
        try:
            resposta = await call_next(request)
        except Exception as erro:
            logger.exception(
                "requisicao_falhou id=%s metodo=%s rota=%s tipo=%s",
                request_id, request.method, request.url.path, type(erro).__name__,
            )
            resposta = JSONResponse(
                {
                    "detail": "O servidor não conseguiu concluir a operação.",
                    "identificador": request_id,
                },
                status_code=500,
            )
    duracao_ms = round((time.perf_counter() - inicio) * 1000, 1)
    resposta.headers["X-Request-ID"] = request_id
    resposta.headers["X-Content-Type-Options"] = "nosniff"
    resposta.headers["Referrer-Policy"] = "no-referrer"
    resposta.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=()"
    resposta.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    frame_ancestors = politica_frame_ancestors()
    if (
        request.url.path == "/api/mapa-onr/conversor"
        or request.url.path.startswith("/api/gerador-notas/interface")
    ) and frame_ancestors == "'none'":
        frame_ancestors = "'self'"
    resposta.headers["Content-Security-Policy"] = (
        "default-src 'self'; base-uri 'self'; form-action 'self'; "
        f"frame-ancestors {frame_ancestors}; "
        "object-src 'none'; script-src 'self'; connect-src 'self'; "
        f"img-src 'self' data: blob: {SERVIDORES_DE_TILE}; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com"
    )
    if (
        request.url.path.startswith("/api/")
        or request.url.path == "/api/mapa-onr/conversor"
        or request.url.path.startswith("/api/gerador-notas/interface")
        or request.url.path in {"/analisar", "/analisar-incra"}
    ):
        resposta.headers["Cache-Control"] = "no-store"
    if request.url.path.startswith("/api/"):
        logger.info(
            "requisicao_concluida id=%s metodo=%s rota=%s status=%s duracao_ms=%s",
            request_id, request.method, request.url.path, resposta.status_code, duracao_ms,
        )
    return resposta


@app.get("/")
def home(request: Request):
    resposta = templates.TemplateResponse(request=request, name="index.html")
    resposta.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return resposta


@app.get("/api/saude")
def saude():
    """Sonda mínima para monitoramento, sem expor configuração do servidor."""
    try:
        with conectar() as conexao:
            with conexao.cursor() as cursor:
                cursor.execute("SELECT 1 AS ok")
                cursor.fetchone()
        return {"status": "OK", "banco": "OK"}
    except Exception:
        logger.exception("sonda_saude_falhou")
        return JSONResponse({"status": "INDISPONIVEL", "banco": "FALHA"}, status_code=503)
