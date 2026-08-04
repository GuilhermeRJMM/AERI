from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from psycopg.types.json import Jsonb

from backend.app.autenticacao import exigir_permissao, proteger_csrf
from backend.app.database import conectar, preparar_banco
from backend.app.seguranca_web import registrar_auditoria, registrar_auditoria_cursor
from backend.app.servicos.custas import (
    STATUS_FINAIS,
    custas_json,
    extrair_pedidos_pdf,
    validar_item_custas,
)


router = APIRouter(
    prefix="/api/custas",
    tags=["informar custas"],
    dependencies=[Depends(preparar_banco)],
)


def _registrar_evento(cursor, item_id: UUID, pedido: str, tipo: str, usuario: str, detalhes=None):
    cursor.execute(
        """INSERT INTO eventos_custas_livro3_aeri
        (item_id, pedido, tipo, usuario, detalhes)
        VALUES (%s, %s, %s, %s, %s)""",
        (item_id, pedido, tipo, usuario, Jsonb(detalhes or {})),
    )


@router.get("")
def listar_custas(_usuario: str = Depends(exigir_permissao("gerenciar_custas"))):
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(
                """SELECT * FROM custas_livro3_aeri
                ORDER BY finalizado ASC, atualizado_em DESC, pedido"""
            )
            return [custas_json(item) for item in cursor.fetchall()]


@router.post("/importar", dependencies=[Depends(proteger_csrf)])
async def importar_relatorio(
    request: Request,
    confirmar: bool = Query(False),
    usuario: str = Depends(exigir_permissao("gerenciar_custas")),
):
    tamanho = int(request.headers.get("content-length", "0") or 0)
    if tamanho > 15_000_000:
        raise HTTPException(status_code=413, detail="O PDF excede o limite de 15 MB.")
    pdf_bytes = await request.body()
    if len(pdf_bytes) > 15_000_000:
        raise HTTPException(status_code=413, detail="O PDF excede o limite de 15 MB.")
    if not pdf_bytes.startswith(b"%PDF") or b"%%EOF" not in pdf_bytes[-2048:]:
        raise HTTPException(status_code=422, detail="Envie um arquivo PDF válido.")

    try:
        resultado = extrair_pedidos_pdf(pdf_bytes)
        if not confirmar:
            return {**resultado, "importados": 0, "duplicados": 0}

        importados = 0
        duplicados = 0
        with conectar() as conexao:
            with conexao.cursor() as cursor:
                for item in resultado["itens"]:
                    identificador = uuid4()
                    cursor.execute(
                        """INSERT INTO custas_livro3_aeri
                        (id, pedido, nome, documento, modalidade, produto, safra, criado_por, atualizado_por)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (pedido) DO NOTHING RETURNING id""",
                        (
                            identificador, item["pedido"], item["nome"], item["documento"],
                            item["modalidade"], item["produto"], item["safra"], usuario, usuario,
                        ),
                    )
                    if cursor.fetchone():
                        importados += 1
                        _registrar_evento(
                            cursor, identificador, item["pedido"], "IMPORTACAO", usuario,
                            {"campos_ausentes": [a["campos"] for a in resultado["alertas"] if a["pedido"] == item["pedido"]]},
                        )
                    else:
                        duplicados += 1
                registrar_auditoria_cursor(
                    cursor, request, "importar_custas", "sucesso", usuario,
                    detalhes={"importados": importados, "duplicados": duplicados, "ignorados": resultado["ignorados"]},
                )
            conexao.commit()
        return {**resultado, "importados": importados, "duplicados": duplicados}
    except HTTPException:
        raise
    except Exception as exc:
        registrar_auditoria(request, "importar_custas", "falha", usuario)
        raise HTTPException(status_code=422, detail="Não foi possível processar o relatório.") from exc


@router.put("/{identificador}", dependencies=[Depends(proteger_csrf)])
def atualizar_custas(
    identificador: UUID,
    dados: dict,
    request: Request,
    usuario: str = Depends(exigir_permissao("gerenciar_custas")),
):
    campos = validar_item_custas(dados)
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute("SELECT * FROM custas_livro3_aeri WHERE id=%s", (identificador,))
            anterior = cursor.fetchone()
            if not anterior:
                raise HTTPException(status_code=404, detail="Pedido não encontrado.")
            cursor.execute(
                """UPDATE custas_livro3_aeri SET
                nome=%s, documento=%s, modalidade=%s, produto=%s, safra=%s,
                resultado=%s, numero_registro=%s, status=%s, atualizado_por=%s, atualizado_em=NOW()
                WHERE id=%s RETURNING *""",
                (
                    campos["nome"], campos["documento"], campos["modalidade"], campos["produto"],
                    campos["safra"], campos["resultado"], campos["numero_registro"], campos["status"],
                    usuario, identificador,
                ),
            )
            item = cursor.fetchone()
            alterados = [campo for campo, valor in campos.items() if anterior.get(campo) != valor]
            _registrar_evento(cursor, identificador, item["pedido"], "ALTERACAO", usuario, {"campos": alterados})
            registrar_auditoria_cursor(cursor, request, "atualizar_custas", "sucesso", usuario, item["pedido"], {"campos": alterados})
        conexao.commit()
    return custas_json(item)


@router.post("/{identificador}/finalizar", dependencies=[Depends(proteger_csrf)])
def finalizar_custas(
    identificador: UUID,
    request: Request,
    usuario: str = Depends(exigir_permissao("gerenciar_custas")),
):
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute("SELECT * FROM custas_livro3_aeri WHERE id=%s", (identificador,))
            anterior = cursor.fetchone()
            if not anterior:
                raise HTTPException(status_code=404, detail="Pedido não encontrado.")
            if anterior["resultado"] == "PENDENTE" and anterior["status"] not in STATUS_FINAIS:
                raise HTTPException(status_code=422, detail="Informe o resultado antes de finalizar.")
            novo_status = anterior["status"] if anterior["status"] in STATUS_FINAIS else "RESPONDIDO"
            cursor.execute(
                """UPDATE custas_livro3_aeri SET finalizado=TRUE, status=%s,
                finalizado_em=NOW(), atualizado_em=NOW(), atualizado_por=%s
                WHERE id=%s RETURNING *""",
                (novo_status, usuario, identificador),
            )
            item = cursor.fetchone()
            _registrar_evento(cursor, identificador, item["pedido"], "FINALIZACAO", usuario, {"status": novo_status})
            registrar_auditoria_cursor(cursor, request, "finalizar_custas", "sucesso", usuario, item["pedido"])
        conexao.commit()
    return custas_json(item)


@router.post("/{identificador}/reabrir", dependencies=[Depends(proteger_csrf)])
def reabrir_custas(
    identificador: UUID,
    request: Request,
    usuario: str = Depends(exigir_permissao("gerenciar_custas")),
):
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(
                """UPDATE custas_livro3_aeri SET finalizado=FALSE, finalizado_em=NULL,
                atualizado_em=NOW(), atualizado_por=%s WHERE id=%s RETURNING *""",
                (usuario, identificador),
            )
            item = cursor.fetchone()
            if not item:
                raise HTTPException(status_code=404, detail="Pedido não encontrado.")
            _registrar_evento(cursor, identificador, item["pedido"], "REABERTURA", usuario)
            registrar_auditoria_cursor(cursor, request, "reabrir_custas", "sucesso", usuario, item["pedido"])
        conexao.commit()
    return custas_json(item)
