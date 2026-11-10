"""Homologação real opt-in; recusa DSN externo e cria somente esquema sintético."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime,timezone
import json
import os
from pathlib import Path
from threading import Barrier
from uuid import uuid4

from fastapi import HTTPException,Response
import psycopg
from psycopg import sql
from psycopg.rows import dict_row
import pytest

from backend.app.rotas import oficio_consultas as consultas, oficio_direto as direto
from test_oficio_direto import requisicao
from test_oficio_consultas import captura


@pytest.fixture
def pg(monkeypatch):
    dsn=os.getenv('AERI_TEST_POSTGRES_URL','')
    if not dsn:
        pytest.skip('Configure um PostgreSQL local isolado de testes.')
    parametros=psycopg.conninfo.conninfo_to_dict(dsn)
    if parametros.get('host') not in {'127.0.0.1','localhost','::1'}:
        pytest.fail('Este teste é exclusivo de PostgreSQL local, nunca do Neon de produção.')
    esquema='teste_oficio_'+uuid4().hex
    def abrir():
        c=psycopg.connect(dsn,row_factory=dict_row,connect_timeout=5)
        c.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(esquema)))
        c.commit()
        return c
    with psycopg.connect(dsn,autocommit=True) as c:
        c.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(esquema)))
    try:
        with abrir() as c:
            c.execute('''CREATE TABLE usuarios_aeri(usuario VARCHAR(80) PRIMARY KEY,
                perfil TEXT NOT NULL DEFAULT 'ADMIN',ativo BOOLEAN NOT NULL DEFAULT TRUE,
                deve_trocar_senha BOOLEAN NOT NULL DEFAULT FALSE)''')
            c.execute('CREATE TABLE perfis_permissoes_aeri(perfil TEXT,permissao TEXT)')
            c.execute('CREATE TABLE usuarios_permissoes_aeri(usuario TEXT,permissao TEXT,concedida BOOLEAN)')
            # Somente chaves de cadastros fictícios para a leitura de correspondências.
            c.execute('CREATE TABLE intimacoes_aeri(protocolo TEXT,excluida_em TIMESTAMPTZ)')
            c.execute("INSERT INTO usuarios_aeri(usuario) VALUES('TESTE'),('OUTRO')")
            for nome in ('067_consultas_oficio.sql','068_oficio_consulta_direta.sql'):
                c.execute((Path(__file__).parents[1]/'backend/app/migrations'/nome).read_text(encoding='utf-8'))
            c.commit()
        @contextmanager
        def conectar():
            with abrir() as c:
                yield c
        monkeypatch.setattr(direto,'conectar',conectar)
        monkeypatch.setattr(consultas,'conectar',conectar)
        monkeypatch.setattr(direto,'registrar_auditoria_cursor',lambda *args:None)
        monkeypatch.setenv('OFICIO_CARTORIO_ID','8422')
        monkeypatch.setenv('OFICIO_TOTAL_HISTORICO_MINIMO','1')
        yield abrir
    finally:
        # Nome aleatório, prefixo fixo e objetos conhecidos, todos criados por este teste.
        assert esquema.startswith('teste_oficio_') and len(esquema)==45
        with abrir() as c:
            for tabela in ('trabalhos_oficio_aeri','conectores_oficio_aeri','consultas_oficio_aeri',
                'intimacoes_aeri','usuarios_permissoes_aeri','perfis_permissoes_aeri','usuarios_aeri'):
                c.execute(sql.SQL('DROP TABLE {}').format(sql.Identifier(tabela)))
            c.commit()
        with psycopg.connect(dsn,autocommit=True) as c:
            c.execute(sql.SQL('DROP SCHEMA {}').format(sql.Identifier(esquema)))


def parear():
    req=requisicao()
    codigo=direto.criar_pareamento(req,Response(),'TESTE')['codigo']
    corpo=json.dumps({'codigo':codigo}).encode()
    req2=requisicao([(b'content-type',b'application/json')],corpo)
    token=asyncio.run(direto.vincular_conector(req2,Response()))['token']
    req3=requisicao([(b'authorization',('Bearer '+token).encode())])
    return codigo,req3,direto.autenticar_conector(req3)


def test_ciclo_real_parear_consultar_resultado_e_revogar(pg):
    codigo,req,cred=parear()
    assert direto.proximo_trabalho(req,Response(),cred)=={'trabalho':None}
    trabalho=direto.solicitar_consulta(requisicao(),'TESTE')
    recebido=direto.proximo_trabalho(req,Response(),cred)['trabalho']
    assert recebido['id']==trabalho['id']
    assert direto.proximo_trabalho(req,Response(),cred)['trabalho'] is None
    dados=captura();dados['consultadoEm']=datetime.now(timezone.utc).isoformat()
    corpo=json.dumps({'captura':dados}).encode()
    reqresultado=requisicao([(b'content-type',b'application/json')],corpo)
    assert asyncio.run(direto.receber_resultado(trabalho['id'],reqresultado,cred))=={'recebido':True}
    assert direto.consultar_trabalho(trabalho['id'],Response(),'TESTE')['estado']=='PRONTO'
    with pg() as c:
        c.execute("INSERT INTO intimacoes_aeri VALUES('IN01708442C',NULL)")
        c.commit()
    assert consultas.consultar_captura(Response(),'TESTE')['itens']==dados['itens']
    with pytest.raises(HTTPException) as erro:
        direto.salvar_resultado(trabalho['id'],{'captura':dados},dados,cred,requisicao())
    assert erro.value.status_code==409
    direto.revogar_conectores(requisicao(),'TESTE')
    with pytest.raises(HTTPException) as erro:
        direto.autenticar_conector(req)
    assert erro.value.status_code==401


def test_duas_retiradas_concorrentes_so_uma_recebe(pg):
    _,req,cred=parear()
    direto.proximo_trabalho(req,Response(),cred)
    trabalho=direto.solicitar_consulta(requisicao(),'TESTE')
    barreira=Barrier(2)
    def retirar(_):
        barreira.wait(timeout=5)
        return direto.proximo_trabalho(req,Response(),cred)['trabalho']
    with ThreadPoolExecutor(max_workers=2) as pool:
        resultados=list(pool.map(retirar,range(2)))
    assert sum(r is not None for r in resultados)==1
    assert next(r['id'] for r in resultados if r)==trabalho['id']


def test_codigo_de_uso_unico_e_propriedade_do_trabalho(pg):
    codigo,req,cred=parear()
    with pytest.raises(HTTPException) as erro:
        direto.vincular_codigo(codigo,requisicao())
    assert erro.value.status_code==401
    direto.proximo_trabalho(req,Response(),cred)
    trabalho=direto.solicitar_consulta(requisicao(),'TESTE')
    with pytest.raises(HTTPException) as erro:
        direto.consultar_trabalho(trabalho['id'],Response(),'OUTRO')
    assert erro.value.status_code==404
