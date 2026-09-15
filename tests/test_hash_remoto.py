import hashlib
import hmac
import io
import json
import os
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from backend.app.rotas.executor_hash import autenticar_executor, calcular_lote
from backend.app.servicos import hash_remoto
from backend.app.servicos.buscas import hash_documento


def req(headers=None):
    return Request({'type':'http','method':'POST','path':'/api/integracoes/executor/documentos-hash',
                    'headers':[(k.lower().encode(),v.encode()) for k,v in (headers or {}).items()]})


def test_cliente_exige_https_host_fixado_e_credencial_exclusiva(monkeypatch):
    monkeypatch.setenv('AERI_HASH_REMOTO_URL','http://aeri-two.vercel.app/api/integracoes/executor/documentos-hash')
    monkeypatch.setenv('AERI_HASH_REMOTO_TOKEN','aeri_hash_'+'a'*43)
    with pytest.raises(RuntimeError): hash_remoto.configuracao()
    monkeypatch.setenv('AERI_HASH_REMOTO_URL','https://evil.example/api/integracoes/executor/documentos-hash')
    with pytest.raises(RuntimeError): hash_remoto.configuracao()


def test_endpoint_rejeita_cookie_e_token_invalido():
    token = 'aeri_hash_'+'a'*43
    with pytest.raises(HTTPException) as erro:
        autenticar_executor(req({'Authorization':'Bearer '+token,'Cookie':'sessao=x'}))
    assert erro.value.status_code == 403
    with pytest.raises(HTTPException) as erro:
        autenticar_executor(req({'Authorization':'Bearer errado'}))
    assert erro.value.status_code == 401


def test_hash_remoto_usa_resposta_validada_e_nao_documento_no_log(monkeypatch):
    token='aeri_hash_'+'b'*43
    monkeypatch.setenv('AERI_HASH_REMOTO_URL','https://aeri-two.vercel.app/api/integracoes/executor/documentos-hash')
    monkeypatch.setenv('AERI_HASH_REMOTO_TOKEN',token)
    documento='12345678901'
    esperado=hmac.new(b'chave-teste',documento.encode(),hashlib.sha256).hexdigest()
    resposta=MagicMock(status=200)
    resposta.headers.get_content_type.return_value='application/json'
    resposta.read.return_value=json.dumps({'versao':1,'hashes':[esperado]}).encode()
    with patch('backend.app.servicos.hash_remoto.build_opener') as build:
        build.return_value.open.return_value.__enter__.return_value=resposta
        hash_remoto._falha_ate=0
        assert hash_remoto._solicitar([documento], *hash_remoto.configuracao()) == [esperado]


def test_calculo_local_nao_devolve_documento(monkeypatch):
    token='aeri_hash_'+'c'*43
    resumo=hashlib.sha256(token[7:].encode()).hexdigest()
    cur=MagicMock(); cur.fetchone.side_effect=[{'id':'executor'}]
    con=MagicMock(); con.__enter__.return_value=con; con.cursor.return_value.__enter__.return_value=cur
    monkeypatch.setenv('AERI_BUSCAS_HMAC_KEY','chave-teste')
    with patch('backend.app.rotas.executor_hash.conectar',return_value=con):
        out=calcular_lote(['12345678901'],resumo,req())
    assert set(out)=={'versao','hashes'}
    assert '12345678901' not in json.dumps(out)
    assert out['hashes'][0]==hmac.new(b'chave-teste',b'12345678901',hashlib.sha256).hexdigest()


def test_buscas_delega_para_o_servico_remoto_sem_fallback_local(monkeypatch):
    monkeypatch.setenv('AERI_BUSCAS_HMAC_KEY','')
    with patch('backend.app.servicos.hash_remoto.calcular_hashes', return_value=['f'*64]) as remoto:
        assert hash_documento('123.456.789-01') == 'f'*64
    remoto.assert_called_once_with(['12345678901'])
