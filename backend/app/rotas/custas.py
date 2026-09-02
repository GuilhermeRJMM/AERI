from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from psycopg.types.json import Jsonb

from backend.app.autenticacao import exigir_permissao, proteger_csrf
from backend.app.database import conectar, preparar_banco
from backend.app.seguranca_web import registrar_auditoria, registrar_auditoria_cursor
from backend.app.servicos.custas import (
    STATUS_FINAIS,
    custas_json,
    extrair_pedidos_pdf,
    gerar_relatorio_custas_pdf,
    validar_item_custas,
)
from backend.app.servicos.buscas import hash_documento
from backend.app.servicos.registros_auxiliares import normalizar_busca, normalizar_safra


router = APIRouter(
    prefix="/api/custas",
    tags=["informar custas"],
    dependencies=[Depends(preparar_banco)],
)


def _analisar_versao_esperada(dados: dict) -> datetime:
    try:
        return datetime.fromisoformat(str(dados.get("atualizadoEm", "")))
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail="Recarregue a lista antes de editar este pedido."
        ) from exc


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


@router.post("/relatorio", dependencies=[Depends(proteger_csrf)])
def exportar_relatorio_custas(
    dados: dict,
    request: Request,
    usuario: str = Depends(exigir_permissao("gerenciar_custas")),
):
    try:
        identificadores = list(dict.fromkeys(UUID(str(item)) for item in dados.get("ids", [])))
    except (TypeError, ValueError, AttributeError) as erro:
        raise HTTPException(status_code=422, detail="Seleção inválida para o relatório.") from erro
    if not identificadores or len(identificadores) > 2_000:
        raise HTTPException(status_code=422, detail="O relatório deve conter entre 1 e 2.000 pedidos.")
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(
                "SELECT id, pedido, modalidade, resultado FROM custas_livro3_aeri WHERE id=ANY(%s)",
                (identificadores,),
            )
            encontrados = {item["id"]: item for item in cursor.fetchall()}
            if len(encontrados) != len(identificadores):
                raise HTTPException(status_code=404, detail="Um dos pedidos do relatório não foi encontrado.")
            ordenados = [encontrados[identificador] for identificador in identificadores]
            pdf = gerar_relatorio_custas_pdf(ordenados)
            cursor.execute(
                """UPDATE custas_livro3_aeri
                SET status='CUSTAS_INFORMADAS', atualizado_por=%s, atualizado_em=NOW()
                WHERE status='BUSCA_REALIZADA' AND finalizado=FALSE
                RETURNING id, pedido""",
                (usuario,),
            )
            custas_informadas = cursor.fetchall()
            for item in custas_informadas:
                _registrar_evento(
                    cursor,
                    item["id"],
                    item["pedido"],
                    "CUSTAS_INFORMADAS_POR_EXPORTACAO",
                    usuario,
                    {"origem": "RELATORIO_PDF"},
                )
            registrar_auditoria_cursor(
                cursor, request, "exportar_relatorio_custas", "sucesso", usuario,
                detalhes={
                    "quantidade": len(ordenados),
                    "formato": "PDF",
                    "custas_informadas": len(custas_informadas),
                },
            )
        conexao.commit()
    return Response(
        pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": 'attachment; filename="relatorio-informar-custas.pdf"',
            "Cache-Control": "no-store",
            "X-AERI-Custas-Informadas": str(len(custas_informadas)),
        },
    )


@router.post("/lote", dependencies=[Depends(proteger_csrf)])
def atualizar_custas_em_lote(
    dados: dict,
    request: Request,
    usuario: str = Depends(exigir_permissao("gerenciar_custas")),
):
    """Finaliza ou reabre pedidos selecionados em uma única transação."""
    acao = str(dados.get("acao", "")).strip().upper()
    if acao not in {"FINALIZAR", "REABRIR"}:
        raise HTTPException(status_code=422, detail="Ação em lote inválida.")
    try:
        identificadores = list(dict.fromkeys(UUID(str(item)) for item in dados.get("ids", [])))
    except (TypeError, ValueError, AttributeError) as erro:
        raise HTTPException(status_code=422, detail="Seleção em lote inválida.") from erro
    if not identificadores or len(identificadores) > 200:
        raise HTTPException(status_code=422, detail="Selecione entre 1 e 200 pedidos.")

    atualizados = []
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM custas_livro3_aeri WHERE id=ANY(%s) FOR UPDATE",
                (identificadores,),
            )
            encontrados = cursor.fetchall()
            if len(encontrados) != len(identificadores):
                raise HTTPException(status_code=404, detail="Um dos pedidos selecionados não foi encontrado.")
            if acao == "FINALIZAR":
                impedidos = [item["pedido"] for item in encontrados if item["resultado"] == "PENDENTE" and item["status"] not in STATUS_FINAIS]
                if impedidos:
                    raise HTTPException(
                        status_code=422,
                        detail=f"Informe o resultado antes de finalizar: {', '.join(impedidos[:8])}.",
                    )
                for item in encontrados:
                    novo_status = item["status"] if item["status"] in STATUS_FINAIS else "RESPONDIDO"
                    cursor.execute(
                        """UPDATE custas_livro3_aeri SET finalizado=TRUE, status=%s,
                        finalizado_em=NOW(), atualizado_em=NOW(), atualizado_por=%s
                        WHERE id=%s RETURNING *""",
                        (novo_status, usuario, item["id"]),
                    )
                    atualizado = cursor.fetchone()
                    atualizados.append(custas_json(atualizado))
                    _registrar_evento(cursor, item["id"], item["pedido"], "FINALIZACAO", usuario, {"origem": "LOTE"})
            else:
                for item in encontrados:
                    cursor.execute(
                        """UPDATE custas_livro3_aeri SET finalizado=FALSE, finalizado_em=NULL,
                        atualizado_em=NOW(), atualizado_por=%s WHERE id=%s RETURNING *""",
                        (usuario, item["id"]),
                    )
                    atualizado = cursor.fetchone()
                    atualizados.append(custas_json(atualizado))
                    _registrar_evento(cursor, item["id"], item["pedido"], "REABERTURA", usuario, {"origem": "LOTE"})
            registrar_auditoria_cursor(
                cursor, request, f"{acao.lower()}_custas_lote", "sucesso", usuario,
                detalhes={"quantidade": len(atualizados)},
            )
        conexao.commit()
    return {"itens": atualizados, "quantidade": len(atualizados)}


@router.post("/registro-auxiliar", dependencies=[Depends(proteger_csrf)])
def incluir_busca_registro_auxiliar(
    dados: dict,
    request: Request,
    usuario: str = Depends(exigir_permissao("gerenciar_custas")),
):
    """Cria um pedido a partir de uma busca e repete a consulta no servidor."""
    pedido = str(dados.get("pedido", "")).strip().upper()[:20]
    nome = str(dados.get("nome", "")).strip()[:180]
    documento = "".join(c for c in str(dados.get("documento", "")) if c.isdigit())[:14]
    produto = normalizar_busca(str(dados.get("produto", "")))[:80]
    safra = normalizar_safra(str(dados.get("safra", "")))[:20]
    modalidade_busca = str(dados.get("modalidade", "")).strip().upper()
    if not pedido or not nome or not produto or not safra or modalidade_busca not in {"PENHOR", "ALIENACAO"}:
        raise HTTPException(status_code=422, detail="Informe pedido, pessoa, produto, safra e modalidade.")
    modalidade_banco = "ALIENAÇÃO" if modalidade_busca == "ALIENACAO" else modalidade_busca
    modalidade_custas = "ALIENACAO_FIDUCIARIA" if modalidade_busca == "ALIENACAO" else modalidade_busca
    termo = normalizar_busca(nome)
    filtros = ["situacao='ATIVO'", "produtos ? %s", "safras ? %s", "modalidade=%s"]
    parametros = [produto, safra, modalidade_banco]
    if len(documento) in {11, 14}:
        filtros.append("(nomes_busca LIKE %s OR documentos_hash ? %s)")
        parametros.extend((f"%{termo}%", hash_documento(documento)))
    else:
        filtros.append("nomes_busca LIKE %s")
        parametros.append(f"%{termo}%")

    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(
                f"SELECT numero FROM registros_auxiliares_aeri WHERE {' AND '.join(filtros)} ORDER BY numero",
                tuple(parametros),
            )
            numeros = [item["numero"] for item in cursor.fetchall()]
            resultado = "POSITIVA" if numeros else "NEGATIVA"
            identificador = uuid4()
            cursor.execute(
                """INSERT INTO custas_livro3_aeri
                (id, pedido, nome, documento, modalidade, produto, safra, resultado,
                 numero_registro, status, criado_por, atualizado_por)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'BUSCA_REALIZADA',%s,%s)
                ON CONFLICT (pedido) DO NOTHING RETURNING *""",
                (identificador, pedido, nome, documento or "NÃO CONSTA", modalidade_custas,
                 produto, safra, resultado, ", ".join(map(str, numeros)), usuario, usuario),
            )
            item = cursor.fetchone()
            if not item:
                raise HTTPException(status_code=409, detail="Este pedido já existe no Informar Custas.")
            _registrar_evento(
                cursor, identificador, pedido, "PESQUISA_REGISTRO_AUXILIAR", usuario,
                {"origem": "REGISTRO_AUXILIAR", "registros": numeros, "resultado": resultado},
            )
            registrar_auditoria_cursor(
                cursor, request, "enviar_registro_auxiliar_custas", "sucesso", usuario,
                pedido, {"quantidade": len(numeros)},
            )
        conexao.commit()
    return custas_json(item)


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
        with conectar() as conexao:
            with conexao.cursor() as cursor:
                pedidos = [item["pedido"] for item in resultado["itens"]]
                cursor.execute("SELECT pedido, nome, modalidade, produto, safra FROM custas_livro3_aeri WHERE pedido=ANY(%s)", (pedidos,))
                existentes = {item["pedido"] for item in cursor.fetchall()}
                cursor.execute("SELECT pedido, nome, modalidade, produto, safra FROM custas_livro3_aeri")
                todos = cursor.fetchall()
        incompletos = {alerta["pedido"] for alerta in resultado["alertas"]}
        resultado["categorias"] = {
            "novos": [item["pedido"] for item in resultado["itens"] if item["pedido"] not in existentes and item["pedido"] not in incompletos],
            "existentes": sorted(existentes),
            "ignorados": resultado["ignorados"],
            "incompletos": sorted(incompletos),
            "possiveisDuplicados": [item["pedido"] for item in resultado["itens"] if any(
                normalizar_busca(item["nome"]) == normalizar_busca(atual["nome"])
                and item["modalidade"] == atual["modalidade"]
                and normalizar_busca(item["produto"]) == normalizar_busca(atual["produto"])
                and normalizar_safra(item["safra"]) == normalizar_safra(atual["safra"])
                and item["pedido"] != atual["pedido"] for atual in todos
            )],
        }
        if not confirmar:
            return {**resultado, "importados": 0, "duplicados": 0, "itensImportados": []}

        importados = 0
        duplicados = 0
        itens_importados = []
        with conectar() as conexao:
            with conexao.cursor() as cursor:
                for item in resultado["itens"]:
                    identificador = uuid4()
                    cursor.execute(
                        """INSERT INTO custas_livro3_aeri
                        (id, pedido, nome, documento, modalidade, produto, safra, criado_por, atualizado_por)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (pedido) DO NOTHING RETURNING *""",
                        (
                            identificador, item["pedido"], item["nome"], item["documento"],
                            item["modalidade"], item["produto"], item["safra"], usuario, usuario,
                        ),
                    )
                    novo_item = cursor.fetchone()
                    if novo_item:
                        importados += 1
                        itens_importados.append(custas_json(novo_item))
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
        return {
            **resultado,
            "importados": importados,
            "duplicados": duplicados,
            "itensImportados": itens_importados,
        }
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
    versao_esperada = _analisar_versao_esperada(dados)
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute("SELECT * FROM custas_livro3_aeri WHERE id=%s", (identificador,))
            anterior = cursor.fetchone()
            if not anterior:
                raise HTTPException(status_code=404, detail="Pedido não encontrado.")
            if anterior["finalizado"]:
                raise HTTPException(
                    status_code=409,
                    detail="Este pedido já foi finalizado. Reabra antes de editar.",
                )
            cursor.execute(
                """UPDATE custas_livro3_aeri SET
                nome=%s, documento=%s, modalidade=%s, produto=%s, safra=%s,
                resultado=%s, numero_registro=%s, status=%s, atualizado_por=%s, atualizado_em=NOW()
                WHERE id=%s AND atualizado_em=%s RETURNING *""",
                (
                    campos["nome"], campos["documento"], campos["modalidade"], campos["produto"],
                    campos["safra"], campos["resultado"], campos["numero_registro"], campos["status"],
                    usuario, identificador, versao_esperada,
                ),
            )
            item = cursor.fetchone()
            if not item:
                # A trava otimista falhou: alguém salvou uma alteração neste
                # pedido entre a abertura da tela de edição e este envio.
                raise HTTPException(
                    status_code=409,
                    detail="Este pedido foi alterado por outra pessoa. Recarregue e tente novamente.",
                )
            alterados = [campo for campo, valor in campos.items() if anterior.get(campo) != valor]
            _registrar_evento(cursor, identificador, item["pedido"], "ALTERACAO", usuario, {"campos": alterados})
            registrar_auditoria_cursor(cursor, request, "atualizar_custas", "sucesso", usuario, item["pedido"], {"campos": alterados})
        conexao.commit()
    return custas_json(item)


@router.post("/{identificador}/pesquisar-registros", dependencies=[Depends(proteger_csrf)])
def pesquisar_registros_do_pedido(
    identificador: UUID, request: Request,
    usuario: str = Depends(exigir_permissao("gerenciar_custas")),
):
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute("SELECT * FROM custas_livro3_aeri WHERE id=%s", (identificador,))
            pedido = cursor.fetchone()
            if not pedido:
                raise HTTPException(status_code=404, detail="Pedido não encontrado.")
            termo = normalizar_busca(pedido["nome"])
            documento = "".join(c for c in pedido["documento"] if c.isdigit())
            filtros = ["situacao='ATIVO'", "produtos ? %s", "safras ? %s", "modalidade=%s"]
            parametros = [normalizar_busca(pedido["produto"]), normalizar_safra(pedido["safra"]),
                          "ALIENAÇÃO" if pedido["modalidade"] == "ALIENACAO_FIDUCIARIA" else pedido["modalidade"]]
            if len(documento) in {11, 14}:
                filtros.append("(nomes_busca LIKE %s OR documentos_hash ? %s)")
                parametros.extend((f"%{termo}%", hash_documento(documento)))
            else:
                filtros.append("nomes_busca LIKE %s")
                parametros.append(f"%{termo}%")
            cursor.execute(
                f"SELECT numero FROM registros_auxiliares_aeri WHERE {' AND '.join(filtros)} ORDER BY numero",
                tuple(parametros),
            )
            numeros = [item["numero"] for item in cursor.fetchall()]
            cursor.execute(
                """SELECT valor FROM custas_precos_aeri WHERE servico='CERTIDAO_REGISTRO_AUXILIAR'
                AND vigencia_inicio<=CURRENT_DATE AND (vigencia_fim IS NULL OR vigencia_fim>=CURRENT_DATE)
                ORDER BY vigencia_inicio DESC LIMIT 1"""
            )
            preco_item = cursor.fetchone()
            preco = preco_item["valor"] if preco_item else Decimal("139.93")
            resultado = "POSITIVA" if numeros else "NEGATIVA"
            numero_registro = ", ".join(str(numero) for numero in numeros)
            cursor.execute(
                """UPDATE custas_livro3_aeri SET resultado=%s, numero_registro=%s,
                status='BUSCA_REALIZADA', atualizado_por=%s, atualizado_em=NOW()
                WHERE id=%s RETURNING *""",
                (resultado, numero_registro, usuario, identificador),
            )
            atualizado = cursor.fetchone()
            valor = preco * max(1, len(numeros))
            _registrar_evento(cursor, identificador, pedido["pedido"], "PESQUISA_REGISTRO_AUXILIAR", usuario,
                              {"registros": numeros, "valor": str(valor), "resultado": resultado})
            registrar_auditoria_cursor(cursor, request, "pesquisar_registros_custas", "sucesso", usuario,
                                       pedido["pedido"], {"quantidade": len(numeros)})
        conexao.commit()
    return {"item": custas_json(atualizado), "registros": numeros, "valor": float(valor), "resultado": resultado}


@router.get("/{identificador}/historico")
def historico_custas(
    identificador: UUID,
    _usuario: str = Depends(exigir_permissao("gerenciar_custas")),
):
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(
                "SELECT tipo, usuario, detalhes, criado_em FROM eventos_custas_livro3_aeri WHERE item_id=%s ORDER BY criado_em DESC",
                (identificador,),
            )
            return [{**item, "criado_em": item["criado_em"].isoformat()} for item in cursor.fetchall()]


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
