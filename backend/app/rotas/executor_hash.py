"""Serviço restrito de HMAC: a chave nunca sai do servidor.

Autenticação de máquina por Bearer exclusivo; não aceita sessão/cookie de
usuário. Não usa CSRF pois não há autenticação implícita do navegador.
"""
import hashlib
import hmac
import json
import re

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from backend.app.database import conectar, preparar_banco
from backend.app.seguranca_web import registrar_auditoria_cursor
from backend.app.servicos.buscas import HASH_DOCUMENTOS_VERSAO, _segredo_documentos

router = APIRouter(prefix='/api/integracoes/executor', tags=['executor'],
                   dependencies=[Depends(preparar_banco)])
MAX_DOCUMENTOS = 100
MAX_CORPO = 8192


def autenticar_executor(request: Request) -> str:
    # Esta rota não participa de login nem de chamadas feitas por sites.
    if request.headers.get('origin') or request.headers.get('cookie'):
        raise HTTPException(403, 'Endpoint exclusivo do executor.')
    recebido = request.headers.get('authorization', '')
    if not re.fullmatch(r'Bearer aeri_hash_[A-Za-z0-9_-]{43}', recebido):
        raise HTTPException(401, 'Credencial do executor inválida.')
    resumo = hashlib.sha256(recebido[7:].encode('ascii')).hexdigest()
    with conectar() as con:
        with con.cursor() as cur:
            cur.execute('''SELECT id FROM executores_hash_documentos_aeri
                WHERE token_hash=%s AND revogado_em IS NULL AND expira_em>NOW()''', (resumo,))
            if not cur.fetchone():
                raise HTTPException(401, 'Credencial do executor inválida ou expirada.')
    return resumo


def calcular_lote(documentos: list[str], credencial_hash: str, request: Request) -> dict:
    try:
        segredo = _segredo_documentos()  # Direto: nunca delega para si mesmo.
    except RuntimeError:
        raise HTTPException(503, 'Serviço de documentos indisponível.') from None
    with conectar() as con:
        with con.cursor() as cur:
            # Atualização atômica por máquina. Reconfere revogação e validade.
            cur.execute('''UPDATE executores_hash_documentos_aeri SET
                janela_em=date_trunc('minute',NOW()), ultima_chamada_em=NOW(),
                chamadas_janela=CASE WHEN janela_em=date_trunc('minute',NOW())
                    THEN chamadas_janela+1 ELSE 1 END,
                documentos_janela=CASE WHEN janela_em=date_trunc('minute',NOW())
                    THEN documentos_janela+%s ELSE %s END
                WHERE token_hash=%s AND revogado_em IS NULL AND expira_em>NOW()
                  AND (janela_em IS DISTINCT FROM date_trunc('minute',NOW())
                       OR (chamadas_janela<120 AND documentos_janela+%s<=3000))
                RETURNING id''', (len(documentos), len(documentos), credencial_hash, len(documentos)))
            executor = cur.fetchone()
            if not executor:
                raise HTTPException(429, 'Executor indisponível ou limite de uso atingido.',
                                    headers={'Retry-After': '60'})
            hashes = [hmac.new(segredo, d.encode('ascii'), hashlib.sha256).hexdigest() for d in documentos]
            registrar_auditoria_cursor(cur, request, 'calcular_hash_executor', 'sucesso',
                recurso=str(executor['id']), detalhes={'quantidade': len(documentos)})
        con.commit()
    return {'versao': HASH_DOCUMENTOS_VERSAO, 'hashes': hashes}


@router.post('/documentos-hash')
async def documentos_hash(request: Request, credencial: str = Depends(autenticar_executor)):
    if request.headers.get('content-type', '').split(';')[0].strip().lower() != 'application/json':
        raise HTTPException(415, 'Envie JSON.')
    corpo = bytearray()
    async for parte in request.stream():
        corpo.extend(parte)
        if len(corpo) > MAX_CORPO:
            raise HTTPException(413, 'Lote excede o limite permitido.')
    try:
        dados = json.loads(corpo)
    except (ValueError, UnicodeError):
        raise HTTPException(422, 'Lote de documentos inválido.') from None
    documentos = dados.get('documentos') if isinstance(dados, dict) else None
    if (not isinstance(documentos, list) or len(documentos) > MAX_DOCUMENTOS
            or any(not isinstance(d, str) or not re.fullmatch(r'(?:[0-9]{11}|[0-9]{14})', d) for d in documentos)):
        raise HTTPException(422, 'Informe até 100 CPF/CNPJ completos, somente com números.')
    # Lote vazio permite ao executor comprovar configuração antes de ler a Tri7.
    resultado = await run_in_threadpool(calcular_lote, documentos, credencial, request)
    return JSONResponse(resultado, headers={'Cache-Control': 'no-store'})
