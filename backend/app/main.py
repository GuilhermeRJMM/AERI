import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from backend.app.rotas import analisador, autenticacao, incra, intimacoes


BASE_DIR = Path(__file__).resolve().parent.parent

app = FastAPI(title="AERI")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app.include_router(autenticacao.router)
app.include_router(analisador.router)
app.include_router(incra.router)
app.include_router(intimacoes.router)


@app.get("/")
def home(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")
