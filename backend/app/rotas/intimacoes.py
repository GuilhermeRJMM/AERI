from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from psycopg.errors import UniqueViolation
from psycopg.types.json import Jsonb

from backend.app.autenticacao import exigir_perfis, exigir_permissao, proteger_csrf
from backend.app.database import conectar, preparar_banco
from backend.app.servicos.intimacoes import (
    andamento_indica_intimacao_positiva,
    fase_por_andamento,
    intimacao_json,
    somar_dias_uteis,
    validar_campos_fase_inicial,
    validar_intimacao,
    validar_novo_andamento,
)
from backend.app.seguranca_web import registrar_auditoria_cursor


router = APIRouter(
    prefix="/api/intimacoes",
    tags=["intimações"],
    dependencies=[Depends(preparar_banco)],
)


def _analisar_versao_esperada(dados: dict) -> datetime:
    try:
        return datetime.fromisoformat(str(dados.get("atualizadoEm", "")))
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail="Recarregue a lista antes de editar esta intimação."
        ) from exc


def _registrar_evento(cursor, identificador: UUID, protocolo: str, tipo: str, usuario: str, detalhes=None):
    cursor.execute(
        """INSERT INTO eventos_intimacao_aeri
        (intimacao_id, protocolo, tipo, usuario, detalhes)
        VALUES (%s, %s, %s, %s, %s)""",
        (identificador, protocolo, tipo, usuario, Jsonb(detalhes or {})),
    )


def _select_intimacoes() -> str:
    return """SELECT i.*,
        COALESCE((SELECT SUM(CASE WHEN l.tipo IN ('CREDITO','ESTORNO') THEN l.valor ELSE 0 END)
                  FROM lancamentos_intimacao_aeri l WHERE l.intimacao_id=i.id), i.valor_pago_onr) AS total_creditos,
        COALESCE((SELECT SUM(CASE WHEN l.tipo='REPASSE' THEN l.valor ELSE 0 END)
                  FROM lancamentos_intimacao_aeri l WHERE l.intimacao_id=i.id), i.valor_usado) AS total_repasses
        FROM intimacoes_aeri i"""


def _data_certificacao_cursor(cursor, data_intimacao: date | None, andamento: str) -> date | None:
    if not data_intimacao or not andamento_indica_intimacao_positiva(andamento):
        return None
    cursor.execute("SELECT data FROM feriados_aeri WHERE ativo=TRUE")
    return somar_dias_uteis(data_intimacao, 16, {item["data"] for item in cursor.fetchall()})


@router.get("")
def listar_intimacoes(
    lixeira: bool = Query(False),
    _usuario: str = Depends(exigir_permissao("ver_intimacoes")),
):
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(
                _select_intimacoes() + (" WHERE i.excluida_em IS NOT NULL" if lixeira else " WHERE i.excluida_em IS NULL")
                + " ORDER BY i.protocolo"
            )
            return [intimacao_json(item) for item in cursor.fetchall()]


@router.post("", status_code=201, dependencies=[Depends(proteger_csrf)])
def criar_intimacao(dados: dict, request: Request, usuario: str = Depends(exigir_permissao("criar_intimacoes"))):
    protocolo, credor, devedor, nome_andamento, andamento, fase = validar_intimacao(dados)
    campos = validar_campos_fase_inicial(dados)
    identificador = uuid4()
    try:
        with conectar() as conexao:
            with conexao.cursor() as cursor:
                campos["data_certificacao"] = _data_certificacao_cursor(
                    cursor, campos["data_intimacao"], nome_andamento,
                ) or campos["data_certificacao"]
                cursor.execute(
                    """INSERT INTO intimacoes_aeri
                    (id, protocolo, credor, devedor, nome_andamento, ultimo_andamento, fase,
                    protocolo_rtd, numero_os_tri7, protocolo_tri7, certidao_decurso_prazo,
                    data_intimacao, data_certificacao, valor_pago_onr, valor_usado)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING *""",
                    (
                        identificador, protocolo, credor, devedor, nome_andamento, andamento, fase,
                        campos["protocolo_rtd"], campos["numero_os_tri7"], campos["protocolo_tri7"],
                        campos["certidao_decurso_prazo"], campos["data_intimacao"],
                        campos["data_certificacao"], campos["valor_pago_onr"], campos["valor_usado"],
                    ),
                )
                item = cursor.fetchone()
                _registrar_evento(cursor, identificador, protocolo, "CRIACAO", usuario, {"fase": fase})
                registrar_auditoria_cursor(
                    cursor, request, "criar_intimacao", "sucesso", usuario, protocolo)
            conexao.commit()
    except UniqueViolation as exc:
        raise HTTPException(status_code=409, detail="Este protocolo já está cadastrado.") from exc
    return intimacao_json(item)


@router.put("/{identificador}", dependencies=[Depends(proteger_csrf)])
def atualizar_intimacao(identificador: UUID, dados: dict, request: Request, usuario: str = Depends(exigir_permissao("alterar_intimacoes"))):
    protocolo, credor, devedor, nome_andamento, andamento, fase = validar_intimacao(dados)
    campos = validar_campos_fase_inicial(dados)
    versao_esperada = _analisar_versao_esperada(dados)
    try:
        with conectar() as conexao:
            with conexao.cursor() as cursor:
                cursor.execute("SELECT * FROM intimacoes_aeri WHERE id=%s", (identificador,))
                anterior = cursor.fetchone()
                if not anterior:
                    raise HTTPException(status_code=404, detail="Intimação não encontrada.")
                campos["data_certificacao"] = _data_certificacao_cursor(
                    cursor, campos["data_intimacao"], nome_andamento,
                ) or campos["data_certificacao"]
                cursor.execute(
                    """UPDATE intimacoes_aeri SET protocolo=%s, credor=%s, devedor=%s,
                    nome_andamento=%s, ultimo_andamento=%s, fase=%s, protocolo_rtd=%s,
                    numero_os_tri7=%s, protocolo_tri7=%s, certidao_decurso_prazo=%s,
                    data_intimacao=%s, data_certificacao=%s, valor_pago_onr=%s,
                    valor_usado=%s, atualizado_em=NOW()
                    WHERE id=%s AND atualizado_em=%s RETURNING *""",
                    (
                        protocolo, credor, devedor, nome_andamento, andamento, fase,
                        campos["protocolo_rtd"], campos["numero_os_tri7"], campos["protocolo_tri7"],
                        campos["certidao_decurso_prazo"], campos["data_intimacao"],
                        campos["data_certificacao"], campos["valor_pago_onr"],
                        campos["valor_usado"], identificador, versao_esperada,
                    ),
                )
                item = cursor.fetchone()
                if not item:
                    # A trava otimista falhou: outra pessoa salvou uma
                    # alteração nesta intimação enquanto a tela estava aberta.
                    raise HTTPException(
                        status_code=409,
                        detail="Esta intimação foi alterada por outra pessoa. Recarregue e tente novamente.",
                    )
                campos_alterados = [
                    campo for campo, novo in {
                        "protocolo": protocolo,
                        "credor": credor,
                        "devedor": devedor,
                        "nome_andamento": nome_andamento,
                        "ultimo_andamento": andamento,
                        "fase": fase,
                        **campos,
                    }.items() if anterior.get(campo) != novo
                ]
                _registrar_evento(
                    cursor, identificador, protocolo, "ALTERACAO", usuario,
                    {"campos_alterados": campos_alterados, "fase": fase},
                )
                registrar_auditoria_cursor(
                    cursor, request, "atualizar_intimacao", "sucesso", usuario,
                    str(identificador))
            conexao.commit()
    except UniqueViolation as exc:
        raise HTTPException(status_code=409, detail="Este protocolo já está cadastrado.") from exc
    return intimacao_json(item)


@router.post("/{identificador}/conferir", dependencies=[Depends(proteger_csrf)])
def conferir_intimacao(
    identificador: UUID,
    request: Request,
    dados: dict | None = None,
    usuario: str = Depends(exigir_permissao("conferir_intimacoes")),
):
    hoje = datetime.now(ZoneInfo("America/Sao_Paulo")).date().isoformat()
    novo_andamento = validar_novo_andamento(dados)
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute("SELECT historico, fase FROM intimacoes_aeri WHERE id=%s", (identificador,))
            atual = cursor.fetchone()
            if not atual:
                raise HTTPException(status_code=404, detail="Intimação não encontrada.")
            historico = list(dict.fromkeys([*(atual["historico"] or []), hoje]))
            if novo_andamento:
                fase = fase_por_andamento(novo_andamento, atual["fase"])
                cursor.execute(
                    """UPDATE intimacoes_aeri SET ultima_conferencia=%s, historico=%s,
                    nome_andamento=%s, ultimo_andamento=%s, fase=%s, atualizado_em=NOW()
                    WHERE id=%s RETURNING *""",
                    (hoje, Jsonb(historico), novo_andamento, hoje, fase, identificador),
                )
            else:
                cursor.execute(
                    """UPDATE intimacoes_aeri SET ultima_conferencia=%s, historico=%s,
                    atualizado_em=NOW() WHERE id=%s RETURNING *""",
                    (hoje, Jsonb(historico), identificador),
                )
            item = cursor.fetchone()
            _registrar_evento(
                cursor,
                identificador,
                item["protocolo"],
                "ANDAMENTO" if novo_andamento else "CONFERENCIA",
                usuario,
                {"houve_novo_andamento": bool(novo_andamento), "fase": item["fase"]},
            )
            registrar_auditoria_cursor(
                cursor, request, "conferir_intimacao", "sucesso", usuario,
                str(identificador))
        conexao.commit()
    return intimacao_json(item)


@router.delete("/{identificador}", status_code=204, dependencies=[Depends(proteger_csrf)])
def excluir_intimacao(identificador: UUID, request: Request, usuario: str = Depends(exigir_perfis("ADMIN", "SUBSTITUTO"))):
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute("SELECT protocolo, fase, excluida_em FROM intimacoes_aeri WHERE id=%s", (identificador,))
            anterior = cursor.fetchone()
            if anterior and not anterior["excluida_em"]:
                _registrar_evento(
                    cursor, identificador, anterior["protocolo"], "EXCLUSAO", usuario,
                    {"fase": anterior["fase"]},
                )
            cursor.execute(
                "UPDATE intimacoes_aeri SET excluida_em=NOW(), excluida_por=%s, atualizado_em=NOW() "
                "WHERE id=%s AND excluida_em IS NULL", (usuario, identificador),
            )
            removidos = cursor.rowcount
            if removidos:
                registrar_auditoria_cursor(
                    cursor, request, "excluir_intimacao", "sucesso", usuario,
                    str(identificador))
        conexao.commit()
    if not removidos:
        raise HTTPException(status_code=404, detail="Intimação não encontrada.")
    return Response(status_code=204)


@router.post("/{identificador}/restaurar", dependencies=[Depends(proteger_csrf)])
def restaurar_intimacao(
    identificador: UUID, request: Request,
    usuario: str = Depends(exigir_perfis("ADMIN", "SUBSTITUTO")),
):
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(
                "UPDATE intimacoes_aeri SET excluida_em=NULL, excluida_por=NULL, atualizado_em=NOW() "
                "WHERE id=%s AND excluida_em IS NOT NULL RETURNING *", (identificador,),
            )
            item = cursor.fetchone()
            if not item:
                raise HTTPException(status_code=404, detail="Intimação não encontrada na lixeira.")
            _registrar_evento(cursor, identificador, item["protocolo"], "RESTAURACAO", usuario)
            registrar_auditoria_cursor(cursor, request, "restaurar_intimacao", "sucesso", usuario, str(identificador))
        conexao.commit()
    return intimacao_json(item)


@router.get("/{identificador}/financeiro")
def listar_financeiro(
    identificador: UUID,
    _usuario: str = Depends(exigir_permissao("ver_intimacoes")),
):
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM lancamentos_intimacao_aeri WHERE intimacao_id=%s ORDER BY criado_em, id",
                (identificador,),
            )
            itens = cursor.fetchall()
    saldo = Decimal("0")
    retorno = []
    for item in itens:
        impacto = item["valor"] if item["tipo"] in {"CREDITO", "ESTORNO"} else -item["valor"]
        saldo += impacto
        retorno.append({
            "id": str(item["id"]), "tipo": item["tipo"], "valor": float(item["valor"]),
            "descricao": item["descricao"], "usuario": item["usuario"],
            "criadoEm": item["criado_em"].isoformat(), "saldoApos": float(saldo),
        })
    return {"itens": retorno, "saldo": float(saldo)}


@router.post("/{identificador}/financeiro", status_code=201, dependencies=[Depends(proteger_csrf)])
def criar_lancamento_financeiro(
    identificador: UUID, dados: dict, request: Request,
    usuario: str = Depends(exigir_permissao("alterar_intimacoes")),
):
    tipo = str(dados.get("tipo") or "").upper()
    try:
        valor = Decimal(str(dados.get("valor"))).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError) as exc:
        raise HTTPException(status_code=422, detail="Informe um valor válido.") from exc
    if tipo not in {"CREDITO", "REPASSE", "ESTORNO"} or valor <= 0:
        raise HTTPException(status_code=422, detail="Tipo ou valor do lançamento inválido.")
    descricao = str(dados.get("descricao") or "").strip()[:240] or None
    lancamento_id = uuid4()
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute("SELECT protocolo FROM intimacoes_aeri WHERE id=%s AND excluida_em IS NULL", (identificador,))
            item = cursor.fetchone()
            if not item:
                raise HTTPException(status_code=404, detail="Intimação não encontrada.")
            cursor.execute(
                "INSERT INTO lancamentos_intimacao_aeri (id, intimacao_id, tipo, valor, descricao, usuario) "
                "VALUES (%s,%s,%s,%s,%s,%s)",
                (lancamento_id, identificador, tipo, valor, descricao, usuario),
            )
            _registrar_evento(cursor, identificador, item["protocolo"], "LANCAMENTO_FINANCEIRO", usuario,
                              {"tipo": tipo, "valor": str(valor)})
            registrar_auditoria_cursor(cursor, request, "lancamento_financeiro_intimacao", "sucesso", usuario, str(identificador))
        conexao.commit()
    return {"id": str(lancamento_id), "ok": True}


@router.put("/{identificador}/checklist-desistencia", dependencies=[Depends(proteger_csrf)])
def atualizar_checklist_desistencia(
    identificador: UUID, dados: dict, request: Request,
    usuario: str = Depends(exigir_permissao("alterar_intimacoes")),
):
    permitidos = {"pedidoLocalizado", "documentosConferidos", "signatario", "notaGerada", "observacao"}
    checklist = {chave: dados[chave] for chave in permitidos if chave in dados}
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(
                "UPDATE intimacoes_aeri SET checklist_desistencia=%s, atualizado_em=NOW() WHERE id=%s RETURNING protocolo",
                (Jsonb(checklist), identificador),
            )
            item = cursor.fetchone()
            if not item:
                raise HTTPException(status_code=404, detail="Intimação não encontrada.")
            _registrar_evento(cursor, identificador, item["protocolo"], "CHECKLIST", usuario, {"campos": sorted(checklist)})
            registrar_auditoria_cursor(cursor, request, "checklist_desistencia", "sucesso", usuario, str(identificador))
        conexao.commit()
    return {"ok": True, "checklist": checklist}


@router.get("/{identificador}/historico")
def historico_intimacao(
    identificador: UUID,
    _usuario: str = Depends(exigir_permissao("ver_intimacoes")),
):
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(
                """SELECT id, protocolo, tipo, usuario, detalhes, criado_em
                FROM eventos_intimacao_aeri WHERE intimacao_id=%s
                ORDER BY criado_em DESC, id DESC LIMIT 500""",
                (identificador,),
            )
            return [
                {
                    "id": item["id"],
                    "protocolo": item["protocolo"],
                    "tipo": item["tipo"],
                    "usuario": item["usuario"],
                    "detalhes": item["detalhes"],
                    "criado_em": item["criado_em"].isoformat(),
                }
                for item in cursor.fetchall()
            ]
