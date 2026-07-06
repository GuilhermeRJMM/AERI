import hashlib
import json
import os
from urllib.request import Request as UrlRequest, urlopen

from fastapi import APIRouter, Depends, HTTPException, Request

from backend.app.autenticacao import usuario_atual
from backend.app.database import conectar, preparar_banco
from backend.app.status_onr import componentes_oficio_api, interpretar_webhook, pior_status, assinatura_valida, status_seguro


router = APIRouter(tags=["status-onr"])
COMPONENTES_URL = "https://status.onr.org.br/v3/components.json"


def _sincronizar_api_publica() -> None:
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(
                "SELECT COALESCE(MAX(recebido_em) < NOW() - INTERVAL '5 minutes', TRUE) AS atualizar FROM status_onr_aeri"
            )
            if not cursor.fetchone()["atualizar"]:
                return

    requisicao = UrlRequest(COMPONENTES_URL, headers={"User-Agent": "AERI/1.0"})
    with urlopen(requisicao, timeout=4) as resposta:
        componentes = componentes_oficio_api(json.load(resposta))
    if not componentes:
        return

    with conectar() as conexao:
        with conexao.cursor() as cursor:
            for componente in componentes:
                cursor.execute(
                    """INSERT INTO status_onr_aeri
                    (chave, nome, status, origem, detalhes, recebido_em)
                    VALUES (%s, %s, %s, 'API', '{}'::jsonb, NOW())
                    ON CONFLICT (chave) DO UPDATE SET
                        nome=EXCLUDED.nome, status=EXCLUDED.status, origem='API', recebido_em=NOW()""",
                    (
                        f"componente:{str(componente.get('id') or componente.get('name'))[:100]}",
                        str(componente.get("name") or "Ofício Eletrônico")[:180],
                        status_seguro(componente.get("status")),
                    ),
                )
            if all(status_seguro(item.get("status")) == "OPERATIONAL" for item in componentes):
                cursor.execute(
                    """UPDATE status_onr_aeri SET status='OPERATIONAL', recebido_em=NOW()
                    WHERE (chave LIKE 'incidente:%' OR chave LIKE 'manutencao:%')
                    AND status <> 'OPERATIONAL'"""
                )
        conexao.commit()


def _salvar_evento(payload: dict, corpo: bytes) -> bool:
    evento = interpretar_webhook(payload)
    hash_evento = hashlib.sha256(corpo).hexdigest()
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(
                """INSERT INTO eventos_onr_aeri
                (hash_evento, tipo, referencia, status, resumo)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (hash_evento) DO NOTHING RETURNING id""",
                (hash_evento, evento["tipo"], evento["referencia"], evento["status"], evento["resumo"]),
            )
            if not cursor.fetchone():
                return False
            cursor.execute(
                """INSERT INTO status_onr_aeri
                (chave, nome, status, origem, detalhes, atualizado_origem_em, recebido_em)
                VALUES (%s, %s, %s, 'WEBHOOK', %s::jsonb, %s, NOW())
                ON CONFLICT (chave) DO UPDATE SET
                    nome=EXCLUDED.nome, status=EXCLUDED.status, origem='WEBHOOK',
                    detalhes=EXCLUDED.detalhes,
                    atualizado_origem_em=EXCLUDED.atualizado_origem_em, recebido_em=NOW()""",
                (
                    evento["chave"], evento["nome"], evento["status"],
                    json.dumps(evento["detalhes"], ensure_ascii=False), evento["atualizado_em"],
                ),
            )
        conexao.commit()
    return True


@router.post("/api/webhooks/onr", dependencies=[Depends(preparar_banco)])
async def webhook_onr(request: Request):
    segredo = os.getenv("ONR_WEBHOOK_SECRET", "")
    if not segredo:
        raise HTTPException(status_code=503, detail="Webhook do ONR ainda não configurado.")
    corpo = await request.body()
    try:
        payload = json.loads(corpo)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Payload inválido.") from exc
    assinatura = request.headers.get("x-instatus-webhook-signature", "")
    if not assinatura_valida(payload, corpo, assinatura, segredo):
        raise HTTPException(status_code=401, detail="Assinatura do webhook inválida.")
    return {"recebido": True, "novo": _salvar_evento(payload, corpo)}


@router.get("/api/status/onr", dependencies=[Depends(preparar_banco)])
def consultar_status_onr(usuario: str = Depends(usuario_atual)):
    try:
        _sincronizar_api_publica()
    except Exception:
        pass
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(
                """SELECT chave, nome, status, origem, detalhes,
                atualizado_origem_em, recebido_em
                FROM status_onr_aeri ORDER BY recebido_em DESC"""
            )
            componentes = cursor.fetchall()
            cursor.execute(
                """SELECT tipo, referencia, status, resumo, recebido_em
                FROM eventos_onr_aeri ORDER BY recebido_em DESC LIMIT 10"""
            )
            eventos = cursor.fetchall()

    status = pior_status(item["status"] for item in componentes)
    atualizado_em = componentes[0]["recebido_em"] if componentes else None
    return {
        "status": status,
        "atualizadoEm": atualizado_em,
        "componentes": componentes,
        "eventos": eventos,
        "configurado": bool(os.getenv("ONR_WEBHOOK_SECRET")),
        "usuario": usuario,
    }
