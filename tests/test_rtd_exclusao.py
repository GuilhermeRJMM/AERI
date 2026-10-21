import inspect
import unittest
from uuid import uuid4
from unittest.mock import patch

from fastapi import HTTPException
from starlette.requests import Request

from backend.app.rotas import rtd_intimacoes


PROTOCOLO_IN = 'IN00000469C'
PROTOCOLO_RTD = '20261021123456789'


def requisicao_teste():
    return Request({
        'type': 'http', 'http_version': '1.1', 'method': 'POST', 'scheme': 'https',
        'path': '/', 'raw_path': b'/', 'query_string': b'', 'headers': [],
        'client': ('192.0.2.10', 443), 'server': ('aeri.test', 443),
    })


class CursorExclusaoFake:
    def __init__(self, intimacao_id, protocolo_envio=None, senha_hash='hash'):
        self.intimacao_id = intimacao_id
        self.protocolo_envio = protocolo_envio
        self.senha_hash = senha_hash
        self.resultado = None
        self.resultados_lista = []
        self.rowcount = 0
        self.sql_executado = []
        self.trava_disponivel = True

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, parametros=None):
        normalizado = ' '.join(sql.split())
        self.sql_executado.append(normalizado)
        self.resultado = None
        self.resultados_lista = []
        self.rowcount = 0
        if 'pg_try_advisory_xact_lock' in normalizado:
            self.resultado = {'obteve': self.trava_disponivel}
        elif 'FROM auditoria_aeri' in normalizado:
            self.resultado = {'total': 0}
        elif 'SELECT senha_hash FROM usuarios_aeri' in normalizado:
            self.resultado = {'senha_hash': self.senha_hash}
        elif 'SELECT id,protocolo,protocolo_rtd' in normalizado:
            self.resultado = {
                'id': self.intimacao_id,
                'protocolo': PROTOCOLO_IN,
                'protocolo_rtd': PROTOCOLO_RTD,
            }
        elif 'AND intimacao_id<>%s' in normalizado:
            self.resultados_lista = []
        elif 'SELECT protocolo FROM rtd_pedidos_aeri' in normalizado and 'protocolo=ANY' in normalizado:
            self.resultados_lista = []
        elif 'SELECT protocolo FROM rtd_pedidos_aeri' in normalizado:
            self.resultados_lista = [{'protocolo': PROTOCOLO_RTD}]
        elif 'SELECT id,protocolo FROM rtd_notificacao_envios_aeri' in normalizado:
            self.resultados_lista = ([{'id': uuid4(), 'protocolo': self.protocolo_envio}]
                                     if self.protocolo_envio else [])
        elif 'SELECT COUNT(*) AS total FROM rtd_notificacao_envios_aeri' in normalizado:
            self.resultado = {'total': 1}
        elif normalizado.startswith('DELETE FROM rtd_eventos_aeri'):
            self.rowcount = 2
        elif normalizado.startswith('DELETE FROM rtd_leituras_aeri'):
            self.rowcount = 1
        elif normalizado.startswith('DELETE FROM rtd_pedidos_aeri'):
            self.rowcount = 1
        elif normalizado.startswith('DELETE FROM rtd_notificacao_envios_aeri'):
            self.rowcount = 1
        elif normalizado.startswith('UPDATE intimacoes_aeri SET protocolo_rtd=NULL'):
            self.rowcount = 1

    def fetchone(self):
        return self.resultado

    def fetchall(self):
        return self.resultados_lista


class ConexaoExclusaoFake:
    def __init__(self, cursor):
        self.cursor_fake = cursor
        self.commits = 0

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def cursor(self):
        return self.cursor_fake

    def commit(self):
        self.commits += 1


class TesteExclusaoProtocolosRtd(unittest.TestCase):
    def test_rota_de_exclusao_e_restrita_ao_cargo_adm(self):
        rota = next(
            item for item in rtd_intimacoes.router.routes
            if getattr(item, 'path', '') == '/api/rtd-intimacoes/intimacao/{identificador}/excluir-protocolos'
        )
        validar_perfil = inspect.signature(rota.endpoint).parameters['usuario'].default.dependency
        requisicao = requisicao_teste()
        requisicao.state.sessao = {'perfil': 'SUBSTITUTO', 'deve_trocar_senha': False}
        with self.assertRaises(HTTPException) as erro:
            validar_perfil(requisicao, usuario='SUBSTITUTO')
        self.assertEqual(erro.exception.status_code, 403)
        requisicao.state.sessao = {'perfil': 'ADMIN', 'deve_trocar_senha': False}
        self.assertEqual(validar_perfil(requisicao, usuario='ADM'), 'ADM')

    def test_exclusao_nao_compete_com_sincronizacao_em_andamento(self):
        identificador = uuid4()
        cursor = CursorExclusaoFake(identificador)
        cursor.trava_disponivel = False
        conexao = ConexaoExclusaoFake(cursor)
        with patch.object(rtd_intimacoes, 'conectar', return_value=conexao), \
             patch.object(rtd_intimacoes, 'registrar_auditoria_cursor') as auditoria:
            with self.assertRaises(HTTPException) as erro:
                rtd_intimacoes.excluir_protocolos_rtd_intimacao(
                    identificador,
                    rtd_intimacoes.ExclusaoProtocolosRtd(senha='correta', confirmacao=PROTOCOLO_IN),
                    requisicao_teste(), usuario='ADM',
                )
        self.assertEqual(erro.exception.status_code, 409)
        self.assertEqual(conexao.commits, 1)
        self.assertFalse(any(sql.startswith('DELETE FROM') for sql in cursor.sql_executado))
        self.assertEqual(auditoria.call_args.args[2:4], ('rtd_exclusao_protocolos', 'sincronizacao_em_andamento'))

    def test_senha_incorreta_nao_remove_e_fica_auditada(self):
        identificador = uuid4()
        cursor = CursorExclusaoFake(identificador)
        conexao = ConexaoExclusaoFake(cursor)
        with patch.object(rtd_intimacoes, 'conectar', return_value=conexao), \
             patch.object(rtd_intimacoes, 'verificar_senha', return_value=False), \
             patch.object(rtd_intimacoes, 'registrar_auditoria_cursor') as auditoria:
            with self.assertRaises(HTTPException) as erro:
                rtd_intimacoes.excluir_protocolos_rtd_intimacao(
                    identificador,
                    rtd_intimacoes.ExclusaoProtocolosRtd(senha='errada', confirmacao=PROTOCOLO_IN),
                    requisicao_teste(), usuario='ADM',
                )
        self.assertEqual(erro.exception.status_code, 401)
        self.assertEqual(conexao.commits, 1)
        self.assertFalse(any(sql.startswith('DELETE FROM') for sql in cursor.sql_executado))
        self.assertEqual(auditoria.call_args.args[2:4], ('rtd_exclusao_senha', 'senha_invalida'))

    def test_exclusao_e_atomica_auditada_e_impede_reimportacao(self):
        identificador = uuid4()
        cursor = CursorExclusaoFake(identificador, protocolo_envio='20261021987654321')
        conexao = ConexaoExclusaoFake(cursor)
        with patch.object(rtd_intimacoes, 'conectar', return_value=conexao), \
             patch.object(rtd_intimacoes, 'verificar_senha', return_value=True), \
             patch.object(rtd_intimacoes, 'registrar_auditoria_cursor') as auditoria:
            resultado = rtd_intimacoes.excluir_protocolos_rtd_intimacao(
                identificador,
                rtd_intimacoes.ExclusaoProtocolosRtd(senha='correta', confirmacao=PROTOCOLO_IN),
                requisicao_teste(), usuario='ADM',
            )
        self.assertEqual(conexao.commits, 1)
        self.assertEqual(resultado['pedidos_rtd'], 1)
        self.assertEqual(resultado['envios_com_protocolo'], 1)
        self.assertEqual(resultado['tentativas_sem_protocolo_preservadas'], 1)
        self.assertEqual(resultado['protocolos_suprimidos'], 2)
        self.assertTrue(any('INSERT INTO rtd_protocolos_excluidos_aeri' in sql for sql in cursor.sql_executado))
        self.assertFalse(any(sql.startswith('DELETE FROM intimacoes_aeri') for sql in cursor.sql_executado))
        self.assertEqual(auditoria.call_args.args[2:4], ('rtd_exclusao_protocolos', 'sucesso'))
        self.assertNotIn('correta', str(auditoria.call_args))


if __name__ == '__main__':
    unittest.main()
