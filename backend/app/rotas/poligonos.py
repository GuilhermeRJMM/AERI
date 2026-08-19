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


def _tem_recorte(cursor) -> bool:
    """Diz se este banco sabe recortar um polígono contra o outro.

    A pergunta é pela função da migração 033, e não pela extensão em si:
    é ela que as consultas usam, e checar exatamente a pré-condição evita
    o caso em que o PostGIS existe mas a migração ainda não rodou.
    """
    cursor.execute(
        "SELECT EXISTS (SELECT 1 FROM pg_proc WHERE proname = %s) AS tem",
        ("aeri_anel_para_geometria",),
    )
    return bool(cursor.fetchone()["tem"])


def _sobreposicoes_com_recorte(cursor, identificador: UUID) -> list:
    """Sobreposições com a área invadida, calculada pelo PostGIS.

    A interseção é recortada no plano e medida como geography, que é o
    elipsoide -- a mesma referência do resto do módulo. Área zero
    significa que os desenhos apenas encostam na divisa, o que é situação
    normal entre vizinhos e não é invasão.
    """
    cursor.execute(
        """
        WITH alvo AS (
            SELECT aeri_anel_para_geometria(anel) AS forma
            FROM poligonos_aeri
            WHERE id = %(id)s AND tipo = 'POLIGONO'
        )
        SELECT p.id, p.nome, p.matricula, p.cor,
               -- CollectionExtract(..., 3) fica só com as partes que têm
               -- área. Dois vizinhos que dividem cerca se cruzam numa
               -- linha, e linha não é invasão: aqui isso vira zero, em
               -- vez de virar um erro de tipo na medição.
               ST_Area(
                   ST_CollectionExtract(
                       ST_Intersection(
                           alvo.forma, aeri_anel_para_geometria(p.anel)
                       ),
                       3
                   )::geography
               ) AS area_invadida
        FROM poligonos_aeri p CROSS JOIN alvo
        WHERE p.id <> %(id)s
          AND p.tipo = 'POLIGONO'
          AND ST_Intersects(alvo.forma, aeri_anel_para_geometria(p.anel))
        ORDER BY area_invadida DESC NULLS LAST
        LIMIT 500
        """,
        {"id": identificador},
    )
    return [
        {
            "id": str(item["id"]), "nome": item["nome"],
            "matricula": item["matricula"], "cor": item["cor"],
            "areaInvadidaM2": item["area_invadida"],
            "apenasEncosta": not (item["area_invadida"] or 0) > 0.005,
        }
        for item in cursor.fetchall()
    ]


def _sobreposicoes_sem_recorte(cursor, identificador: UUID) -> list:
    """Só quem se sobrepõe, sem quanto -- usado quando não há PostGIS."""
    cursor.execute("SELECT * FROM poligonos_aeri WHERE tipo='POLIGONO' LIMIT 500")
    todos = cursor.fetchall()

    alvo = next((p for p in todos if str(p["id"]) == str(identificador)), None)
    if not alvo:
        raise HTTPException(status_code=404, detail="Polígono não encontrado.")

    return [
        {
            "id": str(outro["id"]), "nome": outro["nome"],
            "matricula": outro["matricula"], "cor": outro["cor"],
            "areaInvadidaM2": None, "apenasEncosta": None,
        }
        for outro in todos
        if str(outro["id"]) != str(identificador)
        and se_sobrepoem(alvo["anel"], outro["anel"])
    ]


@router.get("/{identificador}/sobreposicoes")
def listar_sobreposicoes(
    identificador: UUID,
    _usuario: str = Depends(exigir_permissao("acessar_poligonos")),
):
    """Quais outros desenhos invadem ou encostam neste.

    Com PostGIS no banco, vem também a área invadida em metros quadrados.
    Sem ele, vem só a lista -- porque calcular recorte à mão devolveria um
    número com cara de exato que ninguém teria como conferir.
    """
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            if _tem_recorte(cursor):
                achados = _sobreposicoes_com_recorte(cursor, identificador)
                if achados:
                    return achados
                # Lista vazia pode ser "não há invasão" ou "o id não
                # existe"; a consulta com CROSS JOIN não distingue os dois.
                cursor.execute(
                    "SELECT 1 FROM poligonos_aeri WHERE id=%s", (identificador,))
                if not cursor.fetchone():
                    raise HTTPException(status_code=404, detail="Polígono não encontrado.")
                return []
            return _sobreposicoes_sem_recorte(cursor, identificador)


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
