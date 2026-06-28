import sys
from pathlib import Path

# --- GPS PARA O VERCEL ---
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# --- IMPORTAÇÕES COM O CAMINHO CORRETO ---
from backend.app.parser import separar_atos
from backend.app.regras import classificar
from backend.app.cancelamentos import aplicar_cancelamentos
from backend.app.modelos import Ato
from backend.app.proprietarios import calcular_cadeia_dominial
from backend.app.incra import extrair_protocolos

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
async def analisar_incra(request: Request):
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
def analisar(dados: dict):
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
