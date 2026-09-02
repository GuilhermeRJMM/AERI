import os
import re
import secrets

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from psycopg.types.json import Jsonb

from backend.app.database import conectar, preparar_banco
from backend.app.seguranca_web import registrar_auditoria_cursor
from backend.app.servicos.custas import rotulo_certidao_custas


USUARIO_INTEGRACAO = "INTEGRACAO_CUSTAS"
_bearer = HTTPBearer(auto_error=False)


def exigir_token_integracao_custas(
    credencial: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> str:
    esperado = os.getenv("AERI_CUSTAS_API_TOKEN", "")
    if len(esperado) < 32:
        raise HTTPException(status_code=503, detail="A integração do Informar Custas não está configurada.")
    recebido = credencial.credentials if credencial and credencial.scheme.lower() == "bearer" else ""
    if len(recebido) > 512 or not secrets.compare_digest(recebido, esperado):
        raise HTTPException(
            status_code=401,
            detail="Credencial da integração inválida.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return USUARIO_INTEGRACAO


router = APIRouter(
    prefix="/api/integracoes/informar-custas",
    tags=["integração Informar Custas"],
    dependencies=[Depends(preparar_banco)],
)


@router.get("/pendentes")
def listar_custas_pendentes_integracao(
    request: Request,
    limite: int = Query(500, ge=1, le=500),
    usuario: str = Depends(exigir_token_integracao_custas),
):
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(
                """SELECT pedido, modalidade, resultado
                FROM custas_livro3_aeri
                WHERE status='BUSCA_REALIZADA' AND finalizado=FALSE
                AND resultado IN ('POSITIVA', 'NEGATIVA')
                ORDER BY atualizado_em, pedido
                LIMIT %s""",
                (limite,),
            )
            encontrados = cursor.fetchall()
            itens = [
                {
                    "pedido": item["pedido"],
                    "tipoCertidao": rotulo_certidao_custas(item),
                }
                for item in encontrados
            ]
            registrar_auditoria_cursor(
                cursor,
                request,
                "consultar_custas_pendentes_integracao",
                "sucesso",
                usuario,
                detalhes={"quantidade": len(itens)},
            )
        conexao.commit()
    return JSONResponse(
        {"itens": itens, "quantidade": len(itens)},
        headers={"Cache-Control": "no-store"},
    )


@router.post("/confirmar")
def confirmar_custas_informadas_integracao(
    dados: dict,
    request: Request,
    usuario: str = Depends(exigir_token_integracao_custas),
):
    recebidos = dados.get("pedidos")
    if not isinstance(recebidos, list) or not 1 <= len(recebidos) <= 500:
        raise HTTPException(status_code=422, detail="Informe de 1 a 500 pedidos para confirmação.")

    pedidos = []
    invalidos = []
    for valor in recebidos:
        pedido = str(valor).strip().upper()
        if not re.fullmatch(r"S\d{11}D", pedido):
            invalidos.append(pedido[:30])
        elif pedido not in pedidos:
            pedidos.append(pedido)
    if invalidos:
        raise HTTPException(status_code=422, detail="Há números de pedido inválidos na confirmação.")

    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(
                """SELECT pedido, status, finalizado FROM custas_livro3_aeri
                WHERE pedido=ANY(%s) FOR UPDATE""",
                (pedidos,),
            )
            encontrados = {item["pedido"]: item for item in cursor.fetchall()}
            confirmaveis = [
                pedido for pedido in pedidos
                if pedido in encontrados
                and encontrados[pedido]["status"] == "BUSCA_REALIZADA"
                and not encontrados[pedido]["finalizado"]
            ]
            ja_confirmados = [
                pedido for pedido in pedidos
                if pedido in encontrados and encontrados[pedido]["status"] == "CUSTAS_INFORMADAS"
            ]
            nao_encontrados = [pedido for pedido in pedidos if pedido not in encontrados]
            nao_confirmados = [
                pedido for pedido in pedidos
                if pedido in encontrados and pedido not in confirmaveis and pedido not in ja_confirmados
            ]

            atualizados = []
            if confirmaveis:
                cursor.execute(
                    """UPDATE custas_livro3_aeri
                    SET status='CUSTAS_INFORMADAS', atualizado_por=%s, atualizado_em=NOW()
                    WHERE pedido=ANY(%s) AND status='BUSCA_REALIZADA' AND finalizado=FALSE
                    RETURNING id, pedido""",
                    (usuario, confirmaveis),
                )
                atualizados = cursor.fetchall()
                for item in atualizados:
                    cursor.execute(
                        """INSERT INTO eventos_custas_livro3_aeri
                        (item_id, pedido, tipo, usuario, detalhes)
                        VALUES (%s, %s, 'CUSTAS_INFORMADAS_PELA_API', %s, %s)""",
                        (
                            item["id"],
                            item["pedido"],
                            usuario,
                            Jsonb({"origem": "API_KEVIN"}),
                        ),
                    )

            confirmados = [item["pedido"] for item in atualizados]
            registrar_auditoria_cursor(
                cursor,
                request,
                "confirmar_custas_informadas_integracao",
                "sucesso",
                usuario,
                detalhes={
                    "confirmados": len(confirmados),
                    "ja_confirmados": len(ja_confirmados),
                    "nao_encontrados": len(nao_encontrados),
                    "nao_confirmados": len(nao_confirmados),
                },
            )
        conexao.commit()

    return JSONResponse(
        {
            "confirmados": confirmados,
            "jaConfirmados": ja_confirmados,
            "naoEncontrados": nao_encontrados,
            "naoConfirmados": nao_confirmados,
        },
        headers={"Cache-Control": "no-store"},
    )
