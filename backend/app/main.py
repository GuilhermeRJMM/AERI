import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from backend.app.rotas import analisador, autenticacao, incra, intimacoes, status_onr, usuarios


BASE_DIR = Path(__file__).resolve().parent.parent
MANUTENCAO_ATIVA = True

HTML_MANUTENCAO = """<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AERI em manutenção</title>
  <style>
    *{box-sizing:border-box}
    body{margin:0;min-height:100vh;display:grid;place-items:center;padding:24px;font-family:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:#10254b;background:linear-gradient(135deg,#e0eafc 0%,#cfdef3 100%)}
    .card{width:min(560px,100%);padding:34px;border-radius:24px;background:rgba(255,255,255,.82);border:1px solid rgba(255,255,255,.78);box-shadow:0 28px 80px rgba(11,36,84,.16);text-align:center;backdrop-filter:blur(16px)}
    .marca{font-size:1.8rem;font-weight:900;color:#2563eb;letter-spacing:-.04em;margin-bottom:16px}
    h1{margin:0 0 10px;font-size:1.45rem}
    p{margin:0;color:#64748b;line-height:1.6}
    .pill{display:inline-flex;margin-top:22px;padding:9px 14px;border-radius:999px;background:#eff6ff;color:#1d4ed8;font-size:.82rem;font-weight:800}
  </style>
</head>
<body>
  <main class="card">
    <div class="marca">AERI</div>
    <h1>Sistema temporariamente indisponível</h1>
    <p>O AERI está em manutenção nesta manhã. Tente novamente mais tarde.</p>
    <span class="pill">Manutenção programada</span>
  </main>
</body>
</html>"""

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
    if MANUTENCAO_ATIVA:
        if request.url.path.startswith("/api/"):
            resposta = JSONResponse({"detail": "AERI temporariamente indisponível para manutenção."}, status_code=503)
        else:
            resposta = HTMLResponse(HTML_MANUTENCAO, status_code=503)
        resposta.headers["Cache-Control"] = "no-store"
        resposta.headers["X-Content-Type-Options"] = "nosniff"
        resposta.headers["X-Frame-Options"] = "DENY"
        resposta.headers["Referrer-Policy"] = "no-referrer"
        return resposta
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
