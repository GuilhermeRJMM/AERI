from datetime import datetime
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from psycopg.errors import UniqueViolation
from psycopg.types.json import Jsonb

from backend.app.autenticacao import exigir_perfis, exigir_permissao, proteger_csrf
from backend.app.database import conectar, preparar_banco
from backend.app.servicos.intimacoes import (
    fase_por_andamento,
    intimacao_json,
    validar_campos_fase_inicial,
    validar_intimacao,
    validar_novo_andamento,
)
from backend.app.seguranca_web import registrar_auditoria


router = APIRouter(
    prefix="/api/intimacoes",
    tags=["intimações"],
    dependencies=[Depends(preparar_banco)],
)


def _registrar_evento(cursor, identificador: UUID, protocolo: str, tipo: str, usuario: str, detalhes=None):
    cursor.execute(
        """INSERT INTO eventos_intimacao_aeri
        (intimacao_id, protocolo, tipo, usuario, detalhes)
        VALUES (%s, %s, %s, %s, %s)""",
        (identificador, protocolo, tipo, usuario, Jsonb(detalhes or {})),
    )


@router.get("")
def listar_intimacoes(_usuario: str = Depends(exigir_permissao("ver_intimacoes"))):
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute("SELECT * FROM intimacoes_aeri ORDER BY protocolo")
            return [intimacao_json(item) for item in cursor.fetchall()]


@router.post("", status_code=201, dependencies=[Depends(proteger_csrf)])
def criar_intimacao(dados: dict, request: Request, usuario: str = Depends(exigir_permissao("criar_intimacoes"))):
    protocolo, credor, devedor, nome_andamento, andamento, fase = validar_intimacao(dados)
    campos = validar_campos_fase_inicial(dados)
    identificador = uuid4()
    try:
        with conectar() as conexao:
            with conexao.cursor() as cursor:
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
            conexao.commit()
    except UniqueViolation as exc:
        raise HTTPException(status_code=409, detail="Este protocolo já está cadastrado.") from exc
    registrar_auditoria(request, "criar_intimacao", "sucesso", usuario, protocolo)
    return intimacao_json(item)


@router.put("/{identificador}", dependencies=[Depends(proteger_csrf)])
def atualizar_intimacao(identificador: UUID, dados: dict, request: Request, usuario: str = Depends(exigir_permissao("alterar_intimacoes"))):
    protocolo, credor, devedor, nome_andamento, andamento, fase = validar_intimacao(dados)
    campos = validar_campos_fase_inicial(dados)
    try:
        with conectar() as conexao:
            with conexao.cursor() as cursor:
                cursor.execute("SELECT * FROM intimacoes_aeri WHERE id=%s", (identificador,))
                anterior = cursor.fetchone()
                if not anterior:
                    raise HTTPException(status_code=404, detail="Intimação não encontrada.")
                cursor.execute(
                    """UPDATE intimacoes_aeri SET protocolo=%s, credor=%s, devedor=%s,
                    nome_andamento=%s, ultimo_andamento=%s, fase=%s, protocolo_rtd=%s,
                    numero_os_tri7=%s, protocolo_tri7=%s, certidao_decurso_prazo=%s,
                    data_intimacao=%s, data_certificacao=%s, valor_pago_onr=%s,
                    valor_usado=%s, atualizado_em=NOW()
                    WHERE id=%s RETURNING *""",
                    (
                        protocolo, credor, devedor, nome_andamento, andamento, fase,
                        campos["protocolo_rtd"], campos["numero_os_tri7"], campos["protocolo_tri7"],
                        campos["certidao_decurso_prazo"], campos["data_intimacao"],
                        campos["data_certificacao"], campos["valor_pago_onr"],
                        campos["valor_usado"], identificador,
                    ),
                )
                item = cursor.fetchone()
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
            conexao.commit()
    except UniqueViolation as exc:
        raise HTTPException(status_code=409, detail="Este protocolo já está cadastrado.") from exc
    if not item:
        raise HTTPException(status_code=404, detail="Intimação não encontrada.")
    registrar_auditoria(request, "atualizar_intimacao", "sucesso", usuario, str(identificador))
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
        conexao.commit()
    registrar_auditoria(request, "conferir_intimacao", "sucesso", usuario, str(identificador))
    return intimacao_json(item)


@router.delete("/{identificador}", status_code=204, dependencies=[Depends(proteger_csrf)])
def excluir_intimacao(identificador: UUID, request: Request, usuario: str = Depends(exigir_perfis("ADMIN", "SUBSTITUTO"))):
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute("SELECT protocolo, fase FROM intimacoes_aeri WHERE id=%s", (identificador,))
            anterior = cursor.fetchone()
            if anterior:
                _registrar_evento(
                    cursor, identificador, anterior["protocolo"], "EXCLUSAO", usuario,
                    {"fase": anterior["fase"]},
                )
            cursor.execute("DELETE FROM intimacoes_aeri WHERE id=%s", (identificador,))
            removidos = cursor.rowcount
        conexao.commit()
    if not removidos:
        raise HTTPException(status_code=404, detail="Intimação não encontrada.")
    registrar_auditoria(request, "excluir_intimacao", "sucesso", usuario, str(identificador))
    return Response(status_code=204)


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
