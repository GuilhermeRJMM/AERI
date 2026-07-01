from datetime import datetime
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Response
from psycopg.errors import UniqueViolation
from psycopg.types.json import Jsonb

from backend.app.autenticacao import usuario_atual
from backend.app.database import conectar
from backend.app.servicos.intimacoes import intimacao_json, validar_intimacao


router = APIRouter(prefix="/api/intimacoes", tags=["intimações"])


@router.get("")
def listar_intimacoes(_usuario: str = Depends(usuario_atual)):
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute("SELECT * FROM intimacoes_aeri ORDER BY protocolo")
            return [intimacao_json(item) for item in cursor.fetchall()]


@router.post("", status_code=201)
def criar_intimacao(dados: dict, _usuario: str = Depends(usuario_atual)):
    protocolo, credor, devedor, andamento = validar_intimacao(dados)
    identificador = uuid4()
    try:
        with conectar() as conexao:
            with conexao.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO intimacoes_aeri
                    (id, protocolo, credor, devedor, ultimo_andamento)
                    VALUES (%s, %s, %s, %s, %s) RETURNING *""",
                    (identificador, protocolo, credor, devedor, andamento),
                )
                item = cursor.fetchone()
            conexao.commit()
    except UniqueViolation as exc:
        raise HTTPException(status_code=409, detail="Este protocolo já está cadastrado.") from exc
    return intimacao_json(item)


@router.put("/{identificador}")
def atualizar_intimacao(identificador: UUID, dados: dict, _usuario: str = Depends(usuario_atual)):
    protocolo, credor, devedor, andamento = validar_intimacao(dados)
    try:
        with conectar() as conexao:
            with conexao.cursor() as cursor:
                cursor.execute(
                    """UPDATE intimacoes_aeri SET protocolo=%s, credor=%s, devedor=%s,
                    ultimo_andamento=%s, atualizado_em=NOW() WHERE id=%s RETURNING *""",
                    (protocolo, credor, devedor, andamento, identificador),
                )
                item = cursor.fetchone()
            conexao.commit()
    except UniqueViolation as exc:
        raise HTTPException(status_code=409, detail="Este protocolo já está cadastrado.") from exc
    if not item:
        raise HTTPException(status_code=404, detail="Intimação não encontrada.")
    return intimacao_json(item)


@router.post("/{identificador}/conferir")
def conferir_intimacao(identificador: UUID, _usuario: str = Depends(usuario_atual)):
    hoje = datetime.now(ZoneInfo("America/Sao_Paulo")).date().isoformat()
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute("SELECT historico FROM intimacoes_aeri WHERE id=%s", (identificador,))
            atual = cursor.fetchone()
            if not atual:
                raise HTTPException(status_code=404, detail="Intimação não encontrada.")
            historico = list(dict.fromkeys([*(atual["historico"] or []), hoje]))
            cursor.execute(
                """UPDATE intimacoes_aeri SET ultima_conferencia=%s, historico=%s,
                atualizado_em=NOW() WHERE id=%s RETURNING *""",
                (hoje, Jsonb(historico), identificador),
            )
            item = cursor.fetchone()
        conexao.commit()
    return intimacao_json(item)


@router.delete("/{identificador}", status_code=204)
def excluir_intimacao(identificador: UUID, _usuario: str = Depends(usuario_atual)):
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute("DELETE FROM intimacoes_aeri WHERE id=%s", (identificador,))
            removidos = cursor.rowcount
        conexao.commit()
    if not removidos:
        raise HTTPException(status_code=404, detail="Intimação não encontrada.")
    return Response(status_code=204)
