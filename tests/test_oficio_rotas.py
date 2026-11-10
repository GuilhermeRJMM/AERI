from contextlib import contextmanager
from datetime import datetime, timezone
import json
from unittest.mock import patch

from fastapi import FastAPI, HTTPException, Response
from fastapi.testclient import TestClient
import pytest

from backend.app.database import preparar_banco
from backend.app.autenticacao import proteger_csrf
from backend.app.rotas import oficio_consultas as rotas
from test_oficio_consultas import captura


class Cursor:
    def __init__(self, registro=None, ativos=()):
        self.registro = registro
        self.ativos = ativos
        self.sql = []

    def execute(self, sql, params=()):
        self.sql.append((sql, params))

    def fetchone(self):
        return self.registro

    def fetchall(self):
        return [{'protocolo': p} for p in self.ativos]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class Banco:
    def __init__(self, cur):
        self.cur = cur
        self.commitado = False

    def cursor(self):
        return self.cur

    def commit(self):
        self.commitado = True


@contextmanager
def conexao(banco):
    yield banco


def cliente(autorizado=True, csrf=True):
    app = FastAPI()
    app.include_router(rotas.router)
    app.dependency_overrides[preparar_banco] = lambda: None
    if csrf:
        app.dependency_overrides[proteger_csrf] = lambda: None
    if autorizado:
        for rota in rotas.router.routes:
            for dep in rota.dependant.dependencies:
                if getattr(dep.call, '__name__', '') == 'verificar':
                    app.dependency_overrides[dep.call] = lambda: 'USUARIO_TESTE'
    return TestClient(app)


def test_sem_autenticacao_nao_toca_banco():
    with patch.object(rotas, 'conectar') as conectar:
        assert cliente(autorizado=False).get('/api/oficio-consultas').status_code == 401
        assert cliente(autorizado=False).post('/api/oficio-consultas', json={}).status_code == 401
        conectar.assert_not_called()


def test_csrf_exigido():
    with patch.object(rotas, 'conectar') as conectar:
        assert cliente(csrf=False).post('/api/oficio-consultas', json={}).status_code == 403
        conectar.assert_not_called()


def test_nao_tem_configuracao_outra_serventia_nao_tem_fallback(monkeypatch):
    monkeypatch.delenv('OFICIO_CARTORIO_ID', raising=False)
    with patch.object(rotas, 'conectar') as conectar:
        assert cliente().get('/api/oficio-consultas').status_code == 503
        conectar.assert_not_called()


@pytest.mark.parametrize('tipo,corpo,status', [
    ('text/plain', '{}', 415), ('application/json', 'x' * 1000001, 413),
    ('application/json', '[]', 422), ('application/json', '{', 422),
])
def test_formato_e_limites_antes_do_banco(monkeypatch, tipo, corpo, status):
    monkeypatch.setenv('OFICIO_CARTORIO_ID', '8422')
    with patch.object(rotas, 'conectar') as conectar:
        r = cliente().post('/api/oficio-consultas', content=corpo, headers={'Content-Type':tipo})
        assert r.status_code == status
        conectar.assert_not_called()


def test_importa_sem_tocar_tabelas_operacionais(monkeypatch):
    monkeypatch.setenv('OFICIO_CARTORIO_ID', '8422')
    dados = captura()
    dados['consultadoEm'] = datetime.now(timezone.utc).isoformat()
    cur = Cursor({'cartorio':'8422'})
    banco = Banco(cur)
    with patch.object(rotas, 'conectar', lambda: conexao(banco)), patch.object(rotas, 'registrar_auditoria_cursor') as audit:
        r = cliente().post('/api/oficio-consultas', json=dados)
        assert r.status_code == 200
        assert r.json()['totalConsultado'] == 1
        audit.assert_called_once()
        assert audit.call_args.args[-1] == {'quantidade':1, 'paginas':1}
    assert banco.commitado
    assert len(cur.sql) == 1
    sql, params = cur.sql[0]
    assert 'consultas_oficio_aeri.consultado_em < EXCLUDED.consultado_em' in sql
    assert 'intimacoes_aeri' not in sql
    assert params[0] == '8422'


def test_importacao_antiga_nao_comita():
    banco = Banco(Cursor(None))
    with patch.object(rotas, 'conectar', lambda: conexao(banco)), patch.object(rotas, 'registrar_auditoria_cursor') as audit:
        with pytest.raises(HTTPException) as erro:
            rotas.salvar_captura(captura(), '8422', 'TESTE', None)
        assert erro.value.status_code == 409
        audit.assert_not_called()
    assert not banco.commitado


def test_consulta_retorna_somente_vinculados_ativos(monkeypatch):
    monkeypatch.setenv('OFICIO_CARTORIO_ID', '8422')
    dados = captura()
    dados['itens'].append(dados['itens'][0] | {'protocolo':'IN00000001X'})
    dados['total'] = 2
    cur = Cursor({'captura':dados, 'importado_em':datetime.now(timezone.utc)}, ['IN01708442C'])
    with patch.object(rotas, 'conectar', lambda: conexao(Banco(cur))):
        resposta = Response()
        retorno = rotas.consultar_captura(resposta, 'TESTE')
    assert resposta.headers['cache-control'] == 'no-store'
    assert retorno['totalVinculado'] == 1
    assert retorno['itens'] == [dados['itens'][0]]
    assert cur.sql[0][1] == ('8422',)
    assert 'excluida_em IS NULL' in cur.sql[1][0]


def test_so_get_post():
    assert cliente().put('/api/oficio-consultas', json={}).status_code == 405
    assert cliente().delete('/api/oficio-consultas').status_code == 405
