import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from backend.app.rotas import analisador, autenticacao, incra, intimacoes, status_onr, usuarios


BASE_DIR = Path(__file__).resolve().parent.parent

app = FastAPI(title="AERI")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app.include_router(autenticacao.router)
app.include_router(analisador.router)
app.include_router(incra.router)
app.include_router(intimacoes.router)
app.include_router(status_onr.router)
app.include_router(usuarios.router)


@app.middleware("http")
async def seguranca_http(request: Request, call_next):
    tamanho = int(request.headers.get("content-length", "0") or 0)
    if tamanho > 16_000_000:
        return JSONResponse({"detail": "Requisição excede o limite permitido."}, status_code=413)
    resposta = await call_next(request)
    resposta.headers["X-Content-Type-Options"] = "nosniff"
    resposta.headers["X-Frame-Options"] = "DENY"
    resposta.headers["Referrer-Policy"] = "no-referrer"
    resposta.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=()"
    resposta.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    resposta.headers["Content-Security-Policy"] = (
        "default-src 'self'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'; "
        "object-src 'none'; script-src 'self'; connect-src 'self'; img-src 'self' data:; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com"
    )
    if request.url.path.startswith("/api/") or request.url.path in {"/analisar", "/analisar-incra"}:
        resposta.headers["Cache-Control"] = "no-store"
    return resposta


@app.get("/")
def home(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")
