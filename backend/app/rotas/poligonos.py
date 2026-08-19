"""Rotas do módulo Polígonos."""
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from psycopg.types.json import Jsonb

from backend.app.autenticacao import exigir_permissao, proteger_csrf
from backend.app.database import conectar, preparar_banco
from backend.app.seguranca_web import registrar_auditoria_cursor
from backend.app.servicos.poligonos import (
    fuso_de,
    geografica_para_utm,
    interpretar_coordenadas,
    medidas,
    poligono_json,
    se_sobrepoem,
    validar_anel,
)


router = APIRouter(
    prefix="/api/poligonos",
    tags=["polígonos"],
    dependencies=[Depends(preparar_banco)],
)

CORES_PERMITIDAS = {
    "#f97316", "#2563eb", "#16a34a", "#dc2626",
    "#9333ea", "#0891b2", "#ca8a04", "#475569",
}


def _validar_entrada(dados: dict) -> dict:
    nome = str(dados.get("nome") or "").strip()
    if not nome or len(nome) > 160:
        raise HTTPException(status_code=422, detail="Informe um nome de até 160 caracteres.")

    tipo = str(dados.get("tipo") or "POLIGONO").upper()
    try:
        anel = validar_anel(dados.get("anel"), tipo)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    matricula = dados.get("matricula")
    if matricula not in (None, ""):
        try:
            matricula = int(str(matricula).replace(".", "").strip())
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Matrícula inválida.") from exc
        if not 0 < matricula < 10_000_000:
            raise HTTPException(status_code=422, detail="Matrícula fora da faixa esperada.")
    else:
        matricula = None

    cor = str(dados.get("cor") or "#f97316").lower()
    if cor not in CORES_PERMITIDAS:
        # Lista fechada em vez de validar formato: a cor vai para o atributo
        # de estilo no desenho, e aceitar texto livre ali abriria injeção.
        cor = "#f97316"

    observacao = str(dados.get("observacao") or "").strip()[:2000] or None

    return {
        "nome": nome, "tipo": tipo, "anel": anel, "matricula": matricula,
        "cor": cor, "observacao": observacao, **medidas(anel, tipo),
    }


@router.get("")
def listar_poligonos(_usuario: str = Depends(exigir_permissao("acessar_poligonos"))):
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM poligonos_aeri ORDER BY criado_em DESC LIMIT 500")
            return [poligono_json(item) for item in cursor.fetchall()]


@router.post("", status_code=201, dependencies=[Depends(proteger_csrf)])
def criar_poligono(
    dados: dict,
    request: Request,
    usuario: str = Depends(exigir_permissao("acessar_poligonos")),
):
    campos = _validar_entrada(dados)
    identificador = uuid4()
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(
                """INSERT INTO poligonos_aeri
                (id, nome, matricula, tipo, anel, area_m2, perimetro_m, cor,
                observacao, criado_por)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING *""",
                (
                    identificador, campos["nome"], campos["matricula"], campos["tipo"],
                    Jsonb(campos["anel"]), campos["area_m2"], campos["perimetro_m"],
                    campos["cor"], campos["observacao"], usuario,
                ),
            )
            item = cursor.fetchone()
            registrar_auditoria_cursor(
                cursor, request, "criar_poligono", "sucesso", usuario, campos["nome"],
                {"tipo": campos["tipo"], "vertices": len(campos["anel"])},
            )
        conexao.commit()
    return poligono_json(item)


@router.put("/{identificador}", dependencies=[Depends(proteger_csrf)])
def atualizar_poligono(
    identificador: UUID,
    dados: dict,
    request: Request,
    usuario: str = Depends(exigir_permissao("acessar_poligonos")),
):
    campos = _validar_entrada(dados)
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(
                """UPDATE poligonos_aeri SET nome=%s, matricula=%s, tipo=%s,
                anel=%s, area_m2=%s, perimetro_m=%s, cor=%s, observacao=%s,
                atualizado_em=NOW() WHERE id=%s RETURNING *""",
                (
                    campos["nome"], campos["matricula"], campos["tipo"],
                    Jsonb(campos["anel"]), campos["area_m2"], campos["perimetro_m"],
                    campos["cor"], campos["observacao"], identificador,
                ),
            )
            item = cursor.fetchone()
            if not item:
                raise HTTPException(status_code=404, detail="Polígono não encontrado.")
            registrar_auditoria_cursor(
                cursor, request, "atualizar_poligono", "sucesso", usuario,
                str(identificador),
            )
        conexao.commit()
    return poligono_json(item)


@router.delete("/{identificador}", status_code=204, dependencies=[Depends(proteger_csrf)])
def excluir_poligono(
    identificador: UUID,
    request: Request,
    usuario: str = Depends(exigir_permissao("acessar_poligonos")),
):
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute("DELETE FROM poligonos_aeri WHERE id=%s", (identificador,))
            removidos = cursor.rowcount
            if removidos:
                registrar_auditoria_cursor(
                    cursor, request, "excluir_poligono", "sucesso", usuario,
                    str(identificador),
                )
        conexao.commit()
    if not removidos:
        raise HTTPException(status_code=404, detail="Polígono não encontrado.")
    return Response(status_code=204)


@router.post("/medir")
def medir_desenho(dados: dict, _usuario: str = Depends(exigir_permissao("acessar_poligonos"))):
    """Área e perímetro de um desenho ainda não salvo.

    O mapa calcula sozinho enquanto o usuário arrasta, para a leitura
    acompanhar o mouse. Esta rota é a fonte autoritativa: é ela que decide
    o número que vai para o banco e para o documento.
    """
    tipo = str(dados.get("tipo") or "POLIGONO").upper()
    try:
        anel = validar_anel(dados.get("anel"), tipo)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    resultado = medidas(anel, tipo)
    return {
        "areaM2": resultado["area_m2"],
        "perimetroM": resultado["perimetro_m"],
        "vertices": len(anel),
        "fuso": fuso_de(anel[0][0]) if anel else None,
    }


@router.post("/importar")
def importar_coordenadas(dados: dict, _usuario: str = Depends(exigir_permissao("acessar_poligonos"))):
    """Lê coordenadas coladas em decimal, GMS ou UTM."""
    texto = str(dados.get("texto") or "")
    if len(texto) > 200_000:
        raise HTTPException(status_code=422, detail="Texto grande demais para importar.")
    pontos = interpretar_coordenadas(texto)
    if not pontos:
        raise HTTPException(
            status_code=422,
            detail="Nenhuma coordenada reconhecida. Use graus decimais, GMS ou UTM.",
        )
    return {"anel": pontos, "vertices": len(pontos)}


@router.get("/{identificador}/sobreposicoes")
def listar_sobreposicoes(
    identificador: UUID,
    _usuario: str = Depends(exigir_permissao("acessar_poligonos")),
):
    """Quais outros desenhos invadem ou tocam este.

    Responde quem, não quanto: a área de invasão exigiria recortar um
    polígono contra o outro, e um número errado com cara de exato numa
    qualificação é pior do que apontar o par e deixar o conferente medir.
    """
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM poligonos_aeri WHERE tipo='POLIGONO' LIMIT 500")
            todos = cursor.fetchall()

    alvo = next((p for p in todos if str(p["id"]) == str(identificador)), None)
    if not alvo:
        raise HTTPException(status_code=404, detail="Polígono não encontrado.")

    return [
        {
            "id": str(outro["id"]), "nome": outro["nome"],
            "matricula": outro["matricula"], "cor": outro["cor"],
        }
        for outro in todos
        if str(outro["id"]) != str(identificador)
        and se_sobrepoem(alvo["anel"], outro["anel"])
    ]


@router.post("/utm")
def converter_para_utm(dados: dict, _usuario: str = Depends(exigir_permissao("acessar_poligonos"))):
    """Devolve o anel em UTM, que é a forma do memorial descritivo."""
    try:
        anel = validar_anel(dados.get("anel"), "POLIGONO")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    fuso = fuso_de(anel[0][0])
    return {
        "fuso": fuso,
        "vertices": [
            {"ordem": i + 1, **geografica_para_utm(lon, lat, fuso)}
            for i, (lon, lat) in enumerate(anel)
        ],
    }
