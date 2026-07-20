from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request

from backend.app.autenticacao import exigir_perfis, exigir_permissao, proteger_csrf
from backend.app.database import conectar, preparar_banco
from backend.app.seguranca_web import registrar_auditoria, registrar_auditoria_cursor
from backend.app.servicos.analise_matricula import analisar_matricula
from backend.app.servicos.tri7 import (
    ConfiguracaoTri7Invalida,
    ErroTri7,
    MatriculaTri7NaoEncontrada,
    MatriculaTri7SemTexto,
    cliente_tri7,
    normalizar_numero_matricula,
)
from backend.app.servicos.aprendizado_regras import (
    validar_id_regra,
    validar_sugestao_aprendizado,
)


router = APIRouter(tags=["analisador"], dependencies=[Depends(preparar_banco)])


def _regras_aprovadas() -> list[dict]:
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(
                """SELECT expressao, expressao_normalizada, categoria, impacta_resultado, tipo_onus
                FROM regras_aprendizado_aeri
                WHERE status='APROVADA'
                ORDER BY atualizado_em DESC"""
            )
            return cursor.fetchall()


def _regra_json(item: dict) -> dict:
    return {
        "id": str(item["id"]),
        "expressao": item["expressao"],
        "categoria": item["categoria"],
        "impacta_resultado": item["impacta_resultado"],
        "tipo_onus": item["tipo_onus"] or None,
        "justificativa": item["justificativa"],
        "status": item["status"],
        "votos": item["votos"],
        "criado_por": item["criado_por"],
        "aprovado_por": item["aprovado_por"],
        "criado_em": item["criado_em"].isoformat(),
        "atualizado_em": item["atualizado_em"].isoformat(),
        "aprovado_em": item["aprovado_em"].isoformat() if item["aprovado_em"] else None,
    }


@router.post("/analisar", dependencies=[Depends(proteger_csrf)])
def analisar(dados: dict, request: Request, usuario: str = Depends(exigir_permissao("processar_matricula"))):
    texto = str(dados.get("texto", ""))
    if not texto.strip() or len(texto) > 5_000_000:
        raise HTTPException(status_code=413, detail="A matrícula excede o limite permitido.")
    resultado = analisar_matricula(texto, regras_aprendidas=_regras_aprovadas())
    registrar_auditoria(request, "analisar_matricula", "sucesso", usuario)
    return resultado


@router.post("/analisar/matricula", dependencies=[Depends(proteger_csrf)])
def analisar_por_numero(
    dados: dict,
    request: Request,
    usuario: str = Depends(exigir_permissao("processar_matricula")),
):
    try:
        numero = normalizar_numero_matricula(dados.get("numero_matricula"))
    except ValueError as erro:
        raise HTTPException(status_code=422, detail=str(erro)) from erro
    try:
        matricula = cliente_tri7().buscar_texto_matricula(numero)
    except (MatriculaTri7NaoEncontrada, MatriculaTri7SemTexto) as erro:
        raise HTTPException(status_code=404, detail=str(erro)) from erro
    except ConfiguracaoTri7Invalida as erro:
        raise HTTPException(status_code=503, detail=str(erro)) from erro
    except ErroTri7 as erro:
        raise HTTPException(status_code=502, detail=str(erro)) from erro
    resultado = analisar_matricula(matricula["texto"], regras_aprendidas=_regras_aprovadas())
    resultado["numero_matricula"] = matricula["numero_matricula"]
    resultado["origem"] = "TRI7"
    registrar_auditoria(request, "consultar_e_analisar_matricula_tri7", "sucesso", usuario, numero)
    return resultado


@router.post("/analisar/aprendizado/sugestoes", dependencies=[Depends(proteger_csrf)])
def sugerir_regra_aprendizado(
    dados: dict,
    request: Request,
    usuario: str = Depends(exigir_permissao("processar_matricula")),
):
    try:
        sugestao = validar_sugestao_aprendizado(dados)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(
                """INSERT INTO regras_aprendizado_aeri
                (id, expressao, expressao_normalizada, categoria, impacta_resultado,
                 tipo_onus, justificativa, criado_por)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (expressao_normalizada, categoria, tipo_onus)
                DO UPDATE SET votos=regras_aprendizado_aeri.votos + 1,
                    status=CASE
                        WHEN regras_aprendizado_aeri.status = 'REJEITADA' THEN 'PENDENTE'
                        ELSE regras_aprendizado_aeri.status
                    END,
                    aprovado_por=CASE
                        WHEN regras_aprendizado_aeri.status = 'REJEITADA' THEN NULL
                        ELSE regras_aprendizado_aeri.aprovado_por
                    END,
                    aprovado_em=CASE
                        WHEN regras_aprendizado_aeri.status = 'REJEITADA' THEN NULL
                        ELSE regras_aprendizado_aeri.aprovado_em
                    END,
                    justificativa=CASE
                        WHEN EXCLUDED.justificativa <> '' THEN EXCLUDED.justificativa
                        ELSE regras_aprendizado_aeri.justificativa
                    END,
                    atualizado_em=NOW()
                RETURNING *""",
                (
                    uuid4(),
                    sugestao["expressao"],
                    sugestao["expressao_normalizada"],
                    sugestao["categoria"],
                    sugestao["impacta_resultado"],
                    sugestao["tipo_onus"],
                    sugestao["justificativa"],
                    usuario,
                ),
            )
            item = cursor.fetchone()
            registrar_auditoria_cursor(
                cursor,
                request,
                "sugerir_regra_aprendizado",
                "sucesso",
                usuario,
                str(item["id"]),
                {"categoria": item["categoria"], "status": item["status"]},
            )
        conexao.commit()
    return _regra_json(item)


@router.get("/analisar/aprendizado/sugestoes")
def listar_regras_aprendizado(
    status: str = "PENDENTE",
    _admin: str = Depends(exigir_perfis("ADMIN", "SUBSTITUTO")),
):
    status = status.strip().upper()
    if status not in {"PENDENTE", "APROVADA", "REJEITADA"}:
        raise HTTPException(status_code=422, detail="Status inválido.")
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(
                """SELECT * FROM regras_aprendizado_aeri
                WHERE status=%s
                ORDER BY votos DESC, atualizado_em DESC
                LIMIT 200""",
                (status,),
            )
            return [_regra_json(item) for item in cursor.fetchall()]


@router.post("/analisar/aprendizado/sugestoes/{regra_id}/aprovar", dependencies=[Depends(proteger_csrf)])
def aprovar_regra_aprendizado(
    regra_id: str,
    request: Request,
    admin: str = Depends(exigir_perfis("ADMIN", "SUBSTITUTO")),
):
    try:
        identificador = validar_id_regra(regra_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(
                """UPDATE regras_aprendizado_aeri
                SET status='APROVADA', aprovado_por=%s, aprovado_em=NOW(), atualizado_em=NOW()
                WHERE id=%s RETURNING *""",
                (admin, identificador),
            )
            item = cursor.fetchone()
            if item:
                registrar_auditoria_cursor(cursor, request, "aprovar_regra_aprendizado", "sucesso", admin, str(identificador))
        conexao.commit()
    if not item:
        raise HTTPException(status_code=404, detail="Regra de aprendizado não encontrada.")
    return _regra_json(item)


@router.post("/analisar/aprendizado/sugestoes/{regra_id}/rejeitar", dependencies=[Depends(proteger_csrf)])
def rejeitar_regra_aprendizado(
    regra_id: str,
    request: Request,
    admin: str = Depends(exigir_perfis("ADMIN", "SUBSTITUTO")),
):
    try:
        identificador = validar_id_regra(regra_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(
                """UPDATE regras_aprendizado_aeri
                SET status='REJEITADA', aprovado_por=%s, atualizado_em=NOW()
                WHERE id=%s RETURNING *""",
                (admin, identificador),
            )
            item = cursor.fetchone()
            if item:
                registrar_auditoria_cursor(cursor, request, "rejeitar_regra_aprendizado", "sucesso", admin, str(identificador))
        conexao.commit()
    if not item:
        raise HTTPException(status_code=404, detail="Regra de aprendizado não encontrada.")
    return _regra_json(item)
