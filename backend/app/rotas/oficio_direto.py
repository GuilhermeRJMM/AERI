"""Fila de consultas: somente HTTPS de saída do conector, sem proxy do navegador."""
import hashlib
import json
import os
import re
import secrets
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from psycopg.types.json import Jsonb
from starlette.concurrency import run_in_threadpool

from backend.app.autenticacao import exigir_permissao, permissoes_sessao, proteger_csrf
from backend.app.database import conectar, preparar_banco
from backend.app.permissoes import projecao_permissoes
from backend.app.rotas.oficio_consultas import cartorio_configurado
from backend.app.seguranca_web import registrar_auditoria_cursor
from backend.app.servicos.oficio_consultas import MAX_CORPO, validar_captura

router = APIRouter(prefix='/api/oficio-consultas', tags=['consulta direta'],
                   dependencies=[Depends(preparar_banco)])
ERROS = {
    'pagina_incorreta':'Abra a listagem de Intimações no Ofício antes de consultar.',
    'filtro_ativo_ou_desconhecido':'Retire os filtros da listagem do Ofício e tente novamente.',
    'cartorio_diferente':'O cartório aberto no Ofício não corresponde à instalação.',
    'total_ou_pagina_divergente':'Prepare a listagem histórica completa no Ofício e tente novamente.',
    'conexao_chrome':'Autorize o conector no Chrome e deixe uma única aba na listagem de Intimações.',
    'consulta_interrompida':'A consulta não foi concluída. Nenhum andamento foi alterado.',
    'expirado':'A consulta expirou. Verifique se o conector está aberto no computador.',
}


async def ler_json_limitado(request, limite=1024):
    if request.headers.get('content-type', '').split(';')[0].strip().lower() != 'application/json':
        raise HTTPException(415, 'Envie JSON.')
    corpo = bytearray()
    async for parte in request.stream():
        if len(corpo)+len(parte) > limite:
            raise HTTPException(413, 'Solicitação excede o limite.')
        corpo.extend(parte)
    try:
        dados = json.loads(corpo)
        if not isinstance(dados, dict):
            raise ValueError()
        return dados
    except (ValueError, RecursionError):
        raise HTTPException(422, 'Solicitação inválida.') from None


def _maquina(request):
    if request.headers.get('origin') or request.headers.get('cookie'):
        raise HTTPException(403, 'Rota exclusiva do conector.')


def _hash(valor):
    return hashlib.sha256(valor.encode('ascii')).hexdigest()


def autenticar_conector(request: Request):
    _maquina(request)
    token = request.headers.get('authorization','')
    if not re.fullmatch(r'Bearer oficio_[A-Za-z0-9_-]{43}',token):
        raise HTTPException(401, 'Conector não autorizado.')
    with conectar() as con:
        with con.cursor() as cur:
            cur.execute(f'''SELECT u.*, {projecao_permissoes('u')}, c.id AS conector_id,c.cartorio
                FROM conectores_oficio_aeri c JOIN usuarios_aeri u ON u.usuario=c.usuario
                WHERE c.token_hash=%s AND c.revogado_em IS NULL AND c.expira_em>NOW()
                AND u.ativo=TRUE''', (_hash(token[7:]),))
            item = cur.fetchone()
    if (not item or item['deve_trocar_senha'] or item['cartorio'] != cartorio_configurado()
            or not permissoes_sessao(item).get('alterar_intimacoes')):
        raise HTTPException(401, 'Conector não autorizado.')
    return {'id':item['conector_id'], 'usuario':item['usuario'], 'cartorio':item['cartorio']}


@router.post('/conectores', dependencies=[Depends(proteger_csrf)])
def criar_pareamento(request: Request, response: Response,
        usuario: str = Depends(exigir_permissao('alterar_intimacoes'))):
    cartorio = cartorio_configurado()
    codigo = 'oficio_pair_'+secrets.token_urlsafe(32)
    with conectar() as con:
        with con.cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ('oficio:'+usuario,))
            cur.execute('''UPDATE conectores_oficio_aeri SET codigo_hash=NULL
                WHERE usuario=%s AND cartorio=%s''', (usuario,cartorio))
            cur.execute('''INSERT INTO conectores_oficio_aeri
                (id,usuario,cartorio,codigo_hash,codigo_expira_em,expira_em)
                VALUES(%s,%s,%s,%s,NOW()+INTERVAL '5 minutes',NOW()+INTERVAL '30 days')''',
                (uuid4(),usuario,cartorio,_hash(codigo)))
            registrar_auditoria_cursor(cur,request,'parear_conector_oficio','sucesso',usuario,cartorio,{})
        con.commit()
    response.headers['Cache-Control'] = 'no-store'
    return {'codigo':codigo, 'expiraEmSegundos':300}


@router.delete('/conectores', dependencies=[Depends(proteger_csrf)], status_code=204)
def revogar_conectores(request: Request,
        usuario: str = Depends(exigir_permissao('alterar_intimacoes'))):
    with conectar() as con:
        with con.cursor() as cur:
            cur.execute('''UPDATE conectores_oficio_aeri SET revogado_em=NOW(),codigo_hash=NULL
                WHERE usuario=%s''',(usuario,))
            cur.execute("UPDATE trabalhos_oficio_aeri SET estado='ERRO',erro='consulta_interrompida' WHERE usuario=%s AND estado IN ('PENDENTE','LENDO')",(usuario,))
            registrar_auditoria_cursor(cur,request,'revogar_conector_oficio','sucesso',usuario,None,{})
        con.commit()


@router.post('/conector/vincular')
async def vincular_conector(request: Request, response: Response):
    _maquina(request)
    dados = await ler_json_limitado(request)
    codigo = dados.get('codigo')
    if set(dados) != {'codigo'} or not isinstance(codigo,str) or not re.fullmatch(r'oficio_pair_[A-Za-z0-9_-]{43}',codigo):
        raise HTTPException(401,'Código inválido ou expirado.')
    resposta=await run_in_threadpool(vincular_codigo,codigo,request)
    response.headers['Cache-Control']='no-store'
    return resposta


def vincular_codigo(codigo,request):
    token = 'oficio_'+secrets.token_urlsafe(32)
    with conectar() as con:
        with con.cursor() as cur:
            cur.execute('''UPDATE conectores_oficio_aeri SET codigo_hash=NULL,token_hash=%s
                WHERE codigo_hash=%s AND codigo_expira_em>NOW() AND revogado_em IS NULL
                AND cartorio=%s RETURNING id,usuario,cartorio''',(_hash(token),_hash(codigo),cartorio_configurado()))
            item = cur.fetchone()
            if not item:
                raise HTTPException(401,'Código inválido ou expirado.')
            cur.execute('''UPDATE conectores_oficio_aeri SET revogado_em=NOW()
                WHERE usuario=%s AND cartorio=%s AND id<>%s AND token_hash IS NOT NULL
                AND revogado_em IS NULL''',(item['usuario'],item['cartorio'],item['id']))
            registrar_auditoria_cursor(cur,request,'conectar_oficio','sucesso',item['usuario'],str(item['id']),{})
        con.commit()
    return {'token':token, 'cartorio':item['cartorio']}


@router.post('/trabalhos', dependencies=[Depends(proteger_csrf)],status_code=202)
def solicitar_consulta(request: Request,
        usuario: str = Depends(exigir_permissao('alterar_intimacoes'))):
    cartorio = cartorio_configurado()
    with conectar() as con:
        with con.cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))",('oficio:'+usuario,))
            # Limpeza limitada aos trabalhos deste usuário; não acumular dados indefinidamente.
            cur.execute("DELETE FROM trabalhos_oficio_aeri WHERE usuario=%s AND expira_em<NOW()-INTERVAL '1 day'",(usuario,))
            cur.execute("UPDATE trabalhos_oficio_aeri SET estado='ERRO',erro='expirado' WHERE usuario=%s AND estado IN ('PENDENTE','LENDO') AND expira_em<=NOW()",(usuario,))
            cur.execute('''SELECT id,estado FROM trabalhos_oficio_aeri WHERE usuario=%s AND cartorio=%s
                AND estado IN ('PENDENTE','LENDO') AND expira_em>NOW()''',(usuario,cartorio))
            existente=cur.fetchone()
            if existente:
                con.commit()
                return {'id':str(existente['id']),'estado':existente['estado']}
            cur.execute('''SELECT id FROM conectores_oficio_aeri WHERE usuario=%s AND cartorio=%s
                AND revogado_em IS NULL AND token_hash IS NOT NULL AND expira_em>NOW()
                AND visto_em>NOW()-INTERVAL '30 seconds' ''',(usuario,cartorio))
            if not cur.fetchone():
                raise HTTPException(409,'Abra o conector neste computador e conecte sua conta antes de consultar.')
            cur.execute('SELECT captura FROM consultas_oficio_aeri WHERE cartorio=%s',(cartorio,))
            anterior = cur.fetchone()
            try:
                minimo = max(int(os.getenv('OFICIO_TOTAL_HISTORICO_MINIMO','0')),
                    anterior['captura']['total'] if anterior else 0)
                if not 1 <= minimo <= 2000:
                    raise ValueError()
            except (ValueError,TypeError):
                raise HTTPException(503,'Configure o total histórico mínimo da primeira consulta.') from None
            cur.execute('''INSERT INTO trabalhos_oficio_aeri(id,usuario,cartorio,minimo,estado)
                VALUES(%s,%s,%s,%s,'PENDENTE') ON CONFLICT(usuario,cartorio)
                WHERE estado IN ('PENDENTE','LENDO') DO UPDATE SET minimo=trabalhos_oficio_aeri.minimo
                RETURNING id,estado''',(uuid4(),usuario,cartorio,minimo))
            item=cur.fetchone()
            registrar_auditoria_cursor(cur,request,'solicitar_consulta_oficio','sucesso',usuario,str(item['id']),{})
        con.commit()
    return {'id':str(item['id']),'estado':item['estado']}


@router.get('/trabalhos/{identificador}')
def consultar_trabalho(identificador: UUID, response: Response,
        usuario: str = Depends(exigir_permissao('alterar_intimacoes'))):
    with conectar() as con:
        with con.cursor() as cur:
            cur.execute('''SELECT estado,erro,expira_em<=NOW() AS expirado FROM trabalhos_oficio_aeri
                WHERE id=%s AND usuario=%s AND cartorio=%s''',(identificador,usuario,cartorio_configurado()))
            item=cur.fetchone()
    if not item:
        raise HTTPException(404,'Consulta não encontrada.')
    if item['expirado'] and item['estado'] in {'PENDENTE','LENDO'}:
        item={'estado':'ERRO','erro':'expirado'}
    response.headers['Cache-Control']='no-store'
    return {'estado':item['estado'],'mensagem':ERROS.get(item['erro'],'')}


@router.post('/conector/proximo')
def proximo_trabalho(request: Request, response: Response, credencial=Depends(autenticar_conector)):
    with conectar() as con:
        with con.cursor() as cur:
            cur.execute('''UPDATE conectores_oficio_aeri SET visto_em=NOW() WHERE id=%s
                AND revogado_em IS NULL AND expira_em>NOW() RETURNING id''',(credencial['id'],))
            if not cur.fetchone():
                raise HTTPException(401,'Conector não autorizado.')
            cur.execute('''UPDATE trabalhos_oficio_aeri SET estado='LENDO',conector_id=%s
                WHERE id=(SELECT id FROM trabalhos_oficio_aeri WHERE usuario=%s AND cartorio=%s
                    AND estado='PENDENTE' AND expira_em>NOW() ORDER BY criado_em
                    FOR UPDATE SKIP LOCKED LIMIT 1) RETURNING id,minimo''',
                (credencial['id'],credencial['usuario'],credencial['cartorio']))
            item=cur.fetchone()
        con.commit()
    response.headers['Cache-Control']='no-store'
    return {'trabalho':{'id':str(item['id']),'cartorio':credencial['cartorio'],'minimo':item['minimo']} if item else None}


@router.post('/conector/trabalhos/{identificador}/resultado')
async def receber_resultado(identificador: UUID, request: Request, credencial=Depends(autenticar_conector)):
    dados = await ler_json_limitado(request,MAX_CORPO)
    captura=None
    if set(dados)=={'captura'}:
        try:
            captura=validar_captura(dados['captura'],credencial['cartorio'])
        except (ValueError,TypeError):
            raise HTTPException(422,'Resultado incompleto ou inválido.') from None
    elif set(dados)!={'erro'} or not isinstance(dados['erro'],str) or dados['erro'] not in ERROS:
        raise HTTPException(422,'Resultado inválido.')
    return await run_in_threadpool(salvar_resultado,identificador,dados,captura,credencial,request)


def salvar_resultado(identificador,dados,captura,credencial,request):
    with conectar() as con:
        with con.cursor() as cur:
            cur.execute('''SELECT t.minimo,t.criado_em FROM trabalhos_oficio_aeri t JOIN conectores_oficio_aeri c ON c.id=t.conector_id
                WHERE t.id=%s AND t.usuario=%s AND t.cartorio=%s AND t.conector_id=%s
                AND t.estado='LENDO' AND t.expira_em>NOW() AND c.revogado_em IS NULL
                AND c.expira_em>NOW() FOR UPDATE OF t FOR SHARE OF c''',
                (identificador,credencial['usuario'],credencial['cartorio'],credencial['id']))
            trabalho=cur.fetchone()
            if not trabalho:
                raise HTTPException(409,'Trabalho expirado, já concluído ou não pertence ao conector.')
            if captura:
                if captura['total']<trabalho['minimo']:
                    raise HTTPException(422,'A consulta não alcançou o histórico esperado.')
                if datetime.fromisoformat(captura['consultadoEm'])<trabalho['criado_em']-timedelta(minutes=2):
                    raise HTTPException(422,'O resultado é anterior à consulta solicitada.')
                cur.execute('''INSERT INTO consultas_oficio_aeri(cartorio,consultado_em,usuario,captura)
                    VALUES(%s,%s,%s,%s) ON CONFLICT(cartorio) DO UPDATE SET
                    consultado_em=EXCLUDED.consultado_em,importado_em=NOW(),usuario=EXCLUDED.usuario,captura=EXCLUDED.captura
                    WHERE consultas_oficio_aeri.consultado_em<EXCLUDED.consultado_em''',
                    (credencial['cartorio'],captura['consultadoEm'],credencial['usuario'],Jsonb(captura)))
            cur.execute('''UPDATE trabalhos_oficio_aeri SET estado=%s,erro=%s WHERE id=%s''',
                ('PRONTO' if captura else 'ERRO',None if captura else dados['erro'],identificador))
            registrar_auditoria_cursor(cur,request,'resultado_consulta_oficio','sucesso' if captura else 'erro',
                credencial['usuario'],str(identificador),{'quantidade':captura['total'] if captura else 0})
        con.commit()
    return {'recebido':True}
