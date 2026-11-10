from unittest.mock import patch
import asyncio
import json
from datetime import datetime,timezone,timedelta
import pytest
from fastapi import HTTPException
from backend.app.rotas.oficio_direto import autenticar_conector, ler_json_limitado
from starlette.requests import Request
from fastapi import Response
from backend.app.rotas import oficio_direto as rotas
from test_oficio_consultas import captura
from test_oficio_rotas import Banco, Cursor, conexao


def requisicao(headers=(), corpo=b'{}'):
    async def receive():
        return {'type':'http.request', 'body':corpo, 'more_body':False}
    return Request({'type':'http', 'method':'POST', 'path':'/', 'headers':headers}, receive)


@pytest.mark.parametrize('headers', [[], [(b'authorization',b'Bearer errado')],
    [(b'origin',b'https://evil.test')], [(b'cookie',b'sessao=x')]])
def test_maquina_nao_aceita_cookie_origin_ou_token_invalido(headers):
    with patch('backend.app.rotas.oficio_direto.conectar') as banco:
        with pytest.raises(HTTPException):
            autenticar_conector(requisicao(headers))
        banco.assert_not_called()


@pytest.mark.parametrize('tipo,corpo,status', [
    (b'text/plain', b'{}',415), (b'application/json',b'[]',422),
    (b'application/json',b'{'*1025,413)])
def test_entrada_limitada(tipo, corpo, status):
    with pytest.raises(HTTPException) as erro:
        asyncio.run(ler_json_limitado(requisicao([(b'content-type',tipo)],corpo),1024))
    assert erro.value.status_code == status


CRED={'id':'11111111-1111-4111-8111-111111111111','usuario':'TESTE','cartorio':'8422'}


@pytest.mark.parametrize('trabalho,status', [(None,409),({'minimo':500},422)])
def test_resultado_recusa_outro_dono_expirado_ou_piso_insuficiente(trabalho,status):
    dados=captura();dados['consultadoEm']=datetime.now(timezone.utc).isoformat()
    banco=Banco(Cursor(trabalho))
    req=requisicao([(b'content-type',b'application/json')],json.dumps({'captura':dados}).encode())
    with patch.object(rotas,'conectar',lambda:conexao(banco)), patch.object(rotas,'registrar_auditoria_cursor') as audit:
        with pytest.raises(HTTPException) as erro:
            asyncio.run(rotas.receber_resultado(CRED['id'],req,CRED))
        assert erro.value.status_code==status
        audit.assert_not_called()
    assert not banco.commitado
    assert not any('INSERT INTO consultas' in sql for sql,_ in banco.cur.sql)
    sql,parametros=banco.cur.sql[0]
    assert 't.conector_id=%s' in sql and "t.estado='LENDO'" in sql and 't.expira_em>NOW()' in sql
    assert parametros==(CRED['id'],'TESTE','8422',CRED['id'])


def test_resultado_atomico_grava_apenas_snapshot_e_trabalho():
    dados=captura();dados['consultadoEm']=datetime.now(timezone.utc).isoformat()
    banco=Banco(Cursor({'minimo':1,'criado_em':datetime.now(timezone.utc)}))
    req=requisicao([(b'content-type',b'application/json')],json.dumps({'captura':dados}).encode())
    with patch.object(rotas,'conectar',lambda:conexao(banco)), patch.object(rotas,'registrar_auditoria_cursor') as audit:
        assert asyncio.run(rotas.receber_resultado(CRED['id'],req,CRED))=={'recebido':True}
        assert audit.call_args.args[-1]=={'quantidade':1}
    assert banco.commitado
    sql=' '.join(s for s,_ in banco.cur.sql)
    assert 'INSERT INTO consultas_oficio_aeri' in sql
    assert 'UPDATE trabalhos_oficio_aeri' in sql
    assert 'intimacoes_aeri' not in sql
    assert 'FOR UPDATE OF t FOR SHARE OF c' in sql


@pytest.mark.parametrize('erro',[[],{},'mensagem com dados pessoais'])
def test_erro_remoto_arbitrario_nao_e_persistido(erro):
    req=requisicao([(b'content-type',b'application/json')],json.dumps({'erro':erro}).encode())
    with patch.object(rotas,'conectar') as db:
        with pytest.raises(HTTPException) as falha:
            asyncio.run(rotas.receber_resultado(CRED['id'],req,CRED))
        assert falha.value.status_code==422
        db.assert_not_called()


def test_job_outro_usuario_nao_pode_consultar(monkeypatch):
    monkeypatch.setenv('OFICIO_CARTORIO_ID','8422')
    banco=Banco(Cursor(None))
    with patch.object(rotas,'conectar',lambda:conexao(banco)):
        with pytest.raises(HTTPException) as erro:
            rotas.consultar_trabalho(CRED['id'],Response(),'OUTRO')
        assert erro.value.status_code==404
    assert banco.cur.sql[0][1]==(CRED['id'],'OUTRO','8422')


def test_pareamento_expirado_ou_repetido_recusado(monkeypatch):
    monkeypatch.setenv('OFICIO_CARTORIO_ID','8422')
    banco=Banco(Cursor(None))
    req=requisicao([(b'content-type',b'application/json')],json.dumps({'codigo':'oficio_pair_'+'a'*43}).encode())
    with patch.object(rotas,'conectar',lambda:conexao(banco)):
        with pytest.raises(HTTPException) as erro:
            asyncio.run(rotas.vincular_conector(req,Response()))
        assert erro.value.status_code==401
    assert not banco.commitado
    assert 'SET codigo_hash=NULL' in banco.cur.sql[0][0]
    assert 'codigo_expira_em>NOW()' in banco.cur.sql[0][0]
    assert 'oficio_pair_' not in str(banco.cur.sql[0][1])


def test_token_revogado_expirado_nao_revela_conta():
    banco=Banco(Cursor(None))
    with patch.object(rotas,'conectar',lambda:conexao(banco)):
        with pytest.raises(HTTPException) as erro:
            rotas.autenticar_conector(requisicao([(b'authorization',('Bearer oficio_'+'a'*43).encode())]))
        assert erro.value.status_code==401
    assert 'c.revogado_em IS NULL' in banco.cur.sql[0][0]
    assert 'u.ativo=TRUE' in banco.cur.sql[0][0]


def test_nao_reutiliza_captura_anterior_ao_clique():
    dados=captura();dados['consultadoEm']=(datetime.now(timezone.utc)-timedelta(hours=1)).isoformat()
    banco=Banco(Cursor({'minimo':1,'criado_em':datetime.now(timezone.utc)}))
    req=requisicao([(b'content-type',b'application/json')],json.dumps({'captura':dados}).encode())
    with patch.object(rotas,'conectar',lambda:conexao(banco)):
        with pytest.raises(HTTPException) as erro:
            asyncio.run(rotas.receber_resultado(CRED['id'],req,CRED))
        assert erro.value.status_code==422
    assert not banco.commitado


class CursorSequencial(Cursor):
    def __init__(self,respostas):
        super().__init__()
        self.respostas=iter(respostas)
    def fetchone(self):
        return next(self.respostas)


def test_recarregar_pagina_retoma_trabalho_existente(monkeypatch):
    monkeypatch.setenv('OFICIO_CARTORIO_ID','8422')
    banco=Banco(CursorSequencial([{'id':CRED['id'],'estado':'LENDO'}]))
    with patch.object(rotas,'conectar',lambda:conexao(banco)):
        assert rotas.solicitar_consulta(None,'TESTE')=={'id':CRED['id'],'estado':'LENDO'}
    assert banco.commitado
    assert not any('INSERT' in sql for sql,_ in banco.cur.sql)


def test_piso_automatico_usa_maior_total_anterior(monkeypatch):
    monkeypatch.setenv('OFICIO_CARTORIO_ID','8422')
    monkeypatch.setenv('OFICIO_TOTAL_HISTORICO_MINIMO','257')
    banco=Banco(CursorSequencial([None,{'id':CRED['id']},{'captura':{'total':258}},{'id':CRED['id'],'estado':'PENDENTE'}]))
    with patch.object(rotas,'conectar',lambda:conexao(banco)),patch.object(rotas,'registrar_auditoria_cursor'):
        assert rotas.solicitar_consulta(None,'TESTE')['estado']=='PENDENTE'
    insert=next((sql,param) for sql,param in banco.cur.sql if 'INSERT INTO trabalhos' in sql)
    assert insert[1][-1]==258
    assert banco.commitado


def test_conector_offline_nao_cria_trabalho(monkeypatch):
    monkeypatch.setenv('OFICIO_CARTORIO_ID','8422')
    banco=Banco(CursorSequencial([None,None]))
    with patch.object(rotas,'conectar',lambda:conexao(banco)):
        with pytest.raises(HTTPException) as erro:
            rotas.solicitar_consulta(None,'TESTE')
        assert erro.value.status_code==409
    assert not any('INSERT' in sql for sql,_ in banco.cur.sql)
