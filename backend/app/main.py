from pathlib import Path

from fastapi import FastAPI
from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.parser import separar_atos
from app.regras import classificar
from app.cancelamentos import aplicar_cancelamentos
from app.modelos import Ato
from app.seguranca import destruir_variaveis
from app.proprietarios import calcular_cadeia_dominial

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

@app.get("/")
def home(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html"
    )

@app.post("/analisar-cadeia")
def analisar_cadeia(dados: dict):
    texto = dados["texto"]
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
    proprietarios = calcular_cadeia_dominial(atos)

    destruir_variaveis(texto, separados)
    return {"proprietarios": proprietarios}


@app.post("/analisar")
def analisar(dados: dict):
    texto = dados["texto"]
    separados = separar_atos(texto)
    atos = []

    # 1. Separação e Classificação
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

    # 2. Aplica a regra de cancelar os atos antigos
    atos = aplicar_cancelamentos(atos)

    # 3. Lógica de Ônus, Restrições e Publicidade
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

    # 4. Filtro de Exibição
    categorias_permitidas = ["ÔNUS", "RESTRIÇÃO", "PUBLICIDADE", "CANCELAMENTO"]
    atos_filtrados = [a.model_dump() for a in atos if a.categoria in categorias_permitidas]

    # --- 5. LÓGICA DE EXTRAÇÃO DE PROPRIETÁRIOS (Cadeia Dominial) ---
    lista_proprietarios = calcular_cadeia_dominial(atos)

    # 6. Prepara a Resposta
    resposta = {
        "resultado": resultado_final,
        "publicidade": "COM PUBLICIDADE" if tem_publicidade else "SEM PUBLICIDADE",
        "atos": atos_filtrados,
        "proprietarios_atuais": lista_proprietarios
    }

    destruir_variaveis(texto, separados)
    return resposta