"""Entrada autenticada de consulta local. Não é receptor de cookies do Ofício."""
import json
import os
import re

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from psycopg.types.json import Jsonb
from starlette.concurrency import run_in_threadpool

from backend.app.autenticacao import exigir_permissao, proteger_csrf
from backend.app.database import conectar, preparar_banco
from backend.app.seguranca_web import registrar_auditoria_cursor
from backend.app.servicos.oficio_consultas import MAX_CORPO, validar_captura

router = APIRouter(prefix='/api/oficio-consultas', tags=['consulta assistida'],
                   dependencies=[Depends(preparar_banco)])


def cartorio_configurado():
    valor = os.getenv('OFICIO_CARTORIO_ID', '').strip()
    if not re.fullmatch(r'[1-9][0-9]{0,9}', valor):
        raise HTTPException(503, 'Configure o identificador do cartório para habilitar a consulta assistida.')
    return valor


def salvar_captura(dados, cartorio, usuario, request):
    with conectar() as con:
        with con.cursor() as cur:
            # A condição no UPSERT protege também duas importações concorrentes.
            cur.execute('''INSERT INTO consultas_oficio_aeri
                (cartorio, consultado_em, usuario, captura) VALUES (%s,%s,%s,%s)
                ON CONFLICT(cartorio) DO UPDATE SET consultado_em=EXCLUDED.consultado_em,
                    importado_em=NOW(),usuario=EXCLUDED.usuario,captura=EXCLUDED.captura
                WHERE consultas_oficio_aeri.consultado_em < EXCLUDED.consultado_em
                RETURNING cartorio''', (cartorio, dados['consultadoEm'], usuario, Jsonb(dados)))
            if not cur.fetchone():
                raise HTTPException(409, 'Já existe uma consulta igual ou mais recente. Nada foi substituído.')
            registrar_auditoria_cursor(cur, request, 'importar_consulta_oficio', 'sucesso',
                usuario, cartorio, {'quantidade': dados['total'], 'paginas': len(dados['paginas'])})
        con.commit()
    return {'totalConsultado': dados['total'], 'consultadoEm': dados['consultadoEm']}


@router.post('', dependencies=[Depends(proteger_csrf)])
async def importar_consulta(request: Request,
        usuario: str = Depends(exigir_permissao('alterar_intimacoes'))):
    cartorio = cartorio_configurado()
    if request.headers.get('content-type', '').split(';')[0].strip().lower() != 'application/json':
        raise HTTPException(415, 'Envie a captura em JSON.')
    corpo = bytearray()
    async for parte in request.stream():
        if len(corpo) + len(parte) > MAX_CORPO:
            raise HTTPException(413, 'A captura excede o limite permitido.')
        corpo.extend(parte)
    try:
        dados = validar_captura(json.loads(corpo), cartorio)
    except (ValueError, TypeError, RecursionError):
        raise HTTPException(422, 'Captura inválida, incompleta, antiga ou de outro cartório. Faça uma nova consulta.') from None
    return await run_in_threadpool(salvar_captura, dados, cartorio, usuario, request)


@router.get('')
def consultar_captura(response: Response,
        _usuario: str = Depends(exigir_permissao('ver_intimacoes'))):
    cartorio = cartorio_configurado()
    response.headers['Cache-Control'] = 'no-store'
    with conectar() as con:
        with con.cursor() as cur:
            cur.execute('''SELECT captura,importado_em FROM consultas_oficio_aeri
                WHERE cartorio=%s''', (cartorio,))
            captura = cur.fetchone()
            if not captura:
                return {'disponivel': False, 'itens': []}
            cur.execute('SELECT protocolo FROM intimacoes_aeri WHERE excluida_em IS NULL')
            ativos = {item['protocolo'] for item in cur.fetchall()}
    dados = captura['captura']
    itens = [item for item in dados['itens'] if item['protocolo'] in ativos]
    return {'disponivel': True, 'consultadoEm': dados['consultadoEm'],
            'importadoEm': captura['importado_em'].isoformat(),
            'totalConsultado': dados['total'], 'totalVinculado': len(itens), 'itens': itens}
