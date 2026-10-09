import json
import unittest
from datetime import datetime, timezone
from io import BytesIO
from uuid import uuid4
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from starlette.requests import Request
from fastapi import UploadFile

from pydantic import ValidationError

import backend.app.rotas.rtd_intimacoes as rotas_rtd
from backend.app.rotas.rtd_intimacoes import PedidoNotificacao, _ambiente_envio_rtd
from backend.app.servicos.rtd_cliente import MAX_ARQUIVO_ENVIO, ClienteRTD, ErroRTD


def endereco(cep='74000000'):
    return {
        'CEP': cep, 'Logradouro': 'Rua de Teste', 'Numero': '10', 'Complemento': '',
        'Bairro': 'Centro', 'Cidade': 'Morrinhos', 'UF': 'GO',
    }


def pedido_valido():
    return {
        'Remetente': {'Nome': 'Cartório de Teste', 'CPFCNPJ': '12.345.678/0001-90',
                      'Endereco': endereco()},
        'CartorioId': 123, 'CidadeDestino': 'Morrinhos', 'UFDestino': 'go',
        'InformacoesAdicionais': 'Recebido em nome de: Credor de Teste, inscrita no CNPJ: 12.345.678/0001-90. Atenção ao prazo.',
        'EntregueSomenteAoDestinatario': True,
        'Notificados': [{'Nome': 'Pessoa Destinatária', 'CpfCnpj': '123.456.789-00',
                         'Endereco': endereco('07400000')}],
    }


class RespostaFake:
    def __init__(self, conteudo):
        self.conteudo = BytesIO(conteudo)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, tamanho=-1):
        return self.conteudo.read(tamanho)


class CursorEnvioFake:
    def __init__(self):
        self.comandos = []
        self.resultado = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, parametros=None):
        self.comandos.append(sql)
        if 'SELECT protocolo,fase FROM intimacoes_aeri' in sql:
            self.resultado = {'protocolo':'IN0123456789C', 'fase':'INTIMACAO'}
        elif 'RETURNING id,chave_operacao,intimacao_id,usuario' in sql:
            agora = datetime.now(timezone.utc)
            self.resultado = {
                'id':str(parametros[3]), 'estado':parametros[0], 'protocolo':parametros[1],
                'cartorio_id':123, 'ambiente':'homologacao', 'erro':parametros[2],
                'criado_em':agora, 'alterado_em':agora,
            }
        else:
            self.resultado = None

    def fetchone(self):
        return self.resultado


class ConexaoEnvioFake:
    def __init__(self, cursor):
        self.cursor_fake = cursor

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def cursor(self):
        return self.cursor_fake

    def commit(self):
        pass


class TesteEnvioNotificacaoRTD(unittest.TestCase):
    def test_envio_fica_em_homologacao_se_ambiente_nao_for_configurado(self):
        with patch.dict('os.environ', {}, clear=True):
            self.assertEqual(_ambiente_envio_rtd(), 'homologacao')
        with patch.dict('os.environ', {'AERI_RTD_NOTIFICACAO_AMBIENTE':'producao'}, clear=True):
            self.assertEqual(_ambiente_envio_rtd(), 'producao')

    def test_payload_validado_e_convertido_para_schema_da_central(self):
        dados = PedidoNotificacao.model_validate(pedido_valido())
        api = dados.para_api(987)
        self.assertEqual(api['Remetente']['CPFCNPJ'], '12345678000190')
        self.assertEqual(api['Notificados'][0]['CpfCnpj'], '12345678900')
        # O OpenAPI da Central declara CEP como inteiro de 32 bits.
        self.assertEqual(api['Notificados'][0]['Endereco']['CEP'], 7400000)
        self.assertEqual(api['ArquivoId'], 987)
        self.assertEqual(api['UFDestino'] if 'UFDestino' in api else dados.uf_destino, 'GO')

    def test_rejeita_documento_e_cep_com_tamanho_invalido(self):
        ruim = pedido_valido()
        ruim['Notificados'][0]['CpfCnpj'] = '123'
        with self.assertRaises(ValidationError):
            PedidoNotificacao.model_validate(ruim)
        ruim = pedido_valido()
        ruim['Remetente']['Endereco']['CEP'] = '12345'
        with self.assertRaises(ValidationError):
            PedidoNotificacao.model_validate(ruim)

    def test_duas_localizacoes_da_mesma_pessoa_sao_enviadas_como_destinatarios_separados(self):
        pedido = pedido_valido()
        primeiro = pedido['Notificados'][0]
        segundo = {
            **primeiro,
            'Endereco': endereco('07400001') | {
                'Logradouro':'Avenida de Teste', 'Numero':'20', 'Bairro':'Setor Sul',
            },
        }
        pedido['Notificados'].append(segundo)

        api = PedidoNotificacao.model_validate(pedido).para_api(987)

        self.assertEqual(len(api['Notificados']), 2)
        self.assertEqual(api['Notificados'][0]['CpfCnpj'], api['Notificados'][1]['CpfCnpj'])
        self.assertNotEqual(api['Notificados'][0]['Endereco'], api['Notificados'][1]['Endereco'])
        self.assertTrue(api['EntregueSomenteAoDestinatario'])

    def test_nao_permite_entrega_a_terceiros(self):
        pedido = pedido_valido()
        pedido['EntregueSomenteAoDestinatario'] = False
        with self.assertRaises(ValidationError):
            PedidoNotificacao.model_validate(pedido)

    def test_exige_identificacao_do_credor_nas_informacoes_adicionais(self):
        pedido = pedido_valido()
        pedido['InformacoesAdicionais'] = 'Atenção ao prazo.'
        with self.assertRaises(ValidationError):
            PedidoNotificacao.model_validate(pedido)

    def test_cartorios_normaliza_resposta_sem_expor_outros_campos(self):
        cliente = ClienteRTD('teste')
        cliente.json = Mock(return_value=[{'Id': 123, 'Nome': 'Cartório Morrinhos', 'secreto': 'ignorar'}])
        self.assertEqual(cliente.cartorios('GO', 'Morrinhos'), [{'id': 123, 'nome': 'Cartório Morrinhos'}])
        cliente.json.assert_called_once_with('/api/cartorio?uf=GO&cidade=Morrinhos')

    def test_upload_usa_campo_file_e_nao_segue_para_outro_host(self):
        cliente = ClienteRTD('segredo')
        cliente.opener.open = Mock(return_value=RespostaFake(b'{"id":42}'))
        self.assertEqual(cliente.enviar_arquivo('aviso.pdf', b'%PDF-teste'), 42)
        req = cliente.opener.open.call_args.args[0]
        self.assertEqual(req.full_url, 'https://apicentral.rtdbrasil.org.br/api/arquivo')
        self.assertIn('name="file"; filename="aviso.pdf"', req.data.decode('latin-1'))
        self.assertTrue(req.get_header('Content-type').startswith('multipart/form-data; boundary='))

    def test_upload_aceita_pdf_real_do_procedimento_acima_de_4mb(self):
        cliente = ClienteRTD('segredo')
        cliente.opener.open = Mock(return_value=RespostaFake(b'{"id":42}'))
        pdf = b'%PDF-' + b'x' * (4_214_400 - 5)

        self.assertEqual(len(pdf), 4_214_400)
        self.assertLessEqual(len(pdf), MAX_ARQUIVO_ENVIO)
        self.assertEqual(cliente.enviar_arquivo('Documentos RTD.pdf', pdf), 42)

    def test_criacao_envia_json_com_arquivo_id_e_retorna_protocolo(self):
        cliente = ClienteRTD('segredo')
        cliente.opener.open = Mock(return_value=RespostaFake(b'{"Protocolo":"20260924145692380","CartorioId":123}'))
        resposta = cliente.criar_notificacao(PedidoNotificacao.model_validate(pedido_valido()).para_api(42))
        self.assertEqual(resposta, {'protocolo': '20260924145692380', 'cartorio_id': 123})
        req = cliente.opener.open.call_args.args[0]
        self.assertEqual(req.get_method(), 'POST')
        self.assertEqual(json.loads(req.data)['ArquivoId'], 42)

    def test_erro_de_rede_na_criacao_e_marcado_como_incerto(self):
        cliente = ClienteRTD('segredo')
        cliente.opener.open = Mock(side_effect=HTTPError('https://privado', 500, 'segredo', {}, None))
        with self.assertRaises(ErroRTD) as erro:
            cliente.criar_notificacao({'CartorioId': 123})
        self.assertTrue(erro.exception.resultado_incerto)
        self.assertNotIn('segredo', str(erro.exception))
        self.assertNotIn('privado', str(erro.exception))

    def test_http_de_permissao_negada_nao_marca_como_incerto(self):
        cliente = ClienteRTD('segredo')
        cliente.opener.open = Mock(side_effect=HTTPError('https://privado', 403, 'segredo', {}, None))
        with self.assertRaises(ErroRTD) as erro:
            cliente.criar_notificacao({'CartorioId': 123})
        self.assertFalse(erro.exception.resultado_incerto)

    def test_homologacao_usa_host_e_token_separados(self):
        with patch.dict('os.environ', {'AERI_RTD_TOKEN_HOMOLOGACAO':'token-hml'}, clear=True):
            cliente = ClienteRTD(ambiente='homologacao')
        cliente.opener.open = Mock(return_value=RespostaFake(b'[]'))
        self.assertEqual(cliente.cartorios('GO', 'Morrinhos'), [])
        self.assertEqual(cliente.opener.open.call_args.args[0].full_url,
                         'https://apicentral.fpsti.com.br/api/cartorio?uf=GO&cidade=Morrinhos')
        self.assertEqual(cliente.opener.open.call_args.args[0].get_header('Authorization'),
                         'Bearer token-hml')

    def test_post_de_notificacao_usa_apenas_a_url_de_homologacao(self):
        cliente = ClienteRTD('token-hml', ambiente='homologacao')
        cliente.opener.open = Mock(return_value=RespostaFake(
            b'{"Protocolo":"HML-TESTE-001","CartorioId":123}'))
        resposta = cliente.criar_notificacao({'CartorioId':123, 'ArquivoId':42})
        self.assertEqual(resposta['protocolo'], 'HML-TESTE-001')
        requisicao = cliente.opener.open.call_args.args[0]
        self.assertEqual(requisicao.full_url, 'https://apicentral.fpsti.com.br/api/notificacao')
        self.assertEqual(requisicao.get_header('Authorization'), 'Bearer token-hml')

    def test_envio_homologacao_nao_vincula_pedido_na_fila_de_producao(self):
        cursor = CursorEnvioFake()
        conexao = ConexaoEnvioFake(cursor)
        cliente = Mock()
        cliente.cartorios.return_value = [{'id':123, 'nome':'Cartório de Teste'}]
        cliente.enviar_arquivo.return_value = 42
        cliente.criar_notificacao.return_value = {
            'protocolo':'20261007000000001', 'cartorio_id':123,
        }
        request = Request({
            'type':'http', 'http_version':'1.1', 'method':'POST',
            'scheme':'http', 'path':'/api/rtd-intimacoes/notificacoes',
            'raw_path':b'/api/rtd-intimacoes/notificacoes', 'query_string':b'',
            'headers':[], 'client':('127.0.0.1',1234), 'server':('127.0.0.1',80),
        })
        dados = json.dumps(pedido_valido())
        with patch.dict('os.environ', {'AERI_RTD_NOTIFICACAO_AMBIENTE':'homologacao'}, clear=True), \
                patch.object(rotas_rtd, 'conectar', return_value=conexao), \
                patch.object(rotas_rtd, 'registrar_auditoria_cursor'), \
                patch.object(rotas_rtd, 'ClienteRTD', return_value=cliente):
            resultado = __import__('asyncio').run(rotas_rtd.enviar_notificacao_rtd(
                request, str(uuid4()), str(uuid4()), dados,
                UploadFile(filename='Documentos RTD.pdf', file=BytesIO(b'%PDF-teste')),
                'usuario-teste',
            ))
        self.assertTrue(resultado['ok'])
        self.assertEqual(resultado['estado'], 'HOMOLOGACAO_OK')
        self.assertEqual(resultado['ambiente'], 'homologacao')
        cliente.enviar_arquivo.assert_called_once_with('Documentos RTD.pdf', b'%PDF-teste')
        cliente.criar_notificacao.assert_called_once()
        self.assertFalse(any('INSERT INTO rtd_pedidos_aeri' in sql for sql in cursor.comandos))

    def test_envio_producao_vincula_protocolo_a_fila_de_acompanhamento(self):
        cursor = CursorEnvioFake()
        conexao = ConexaoEnvioFake(cursor)
        cliente = Mock()
        cliente.cartorios.return_value = [{'id':123, 'nome':'Cartório de Teste'}]
        cliente.enviar_arquivo.return_value = 42
        cliente.criar_notificacao.return_value = {
            'protocolo':'20261007000000001', 'cartorio_id':123,
        }
        request = Request({
            'type':'http', 'http_version':'1.1', 'method':'POST',
            'scheme':'http', 'path':'/api/rtd-intimacoes/notificacoes',
            'raw_path':b'/api/rtd-intimacoes/notificacoes', 'query_string':b'',
            'headers':[], 'client':('127.0.0.1',1234), 'server':('127.0.0.1',80),
        })
        with patch.dict('os.environ', {'AERI_RTD_NOTIFICACAO_AMBIENTE':'producao'}, clear=True), \
                patch.object(rotas_rtd, 'conectar', return_value=conexao), \
                patch.object(rotas_rtd, 'registrar_auditoria_cursor'), \
                patch.object(rotas_rtd, 'ClienteRTD', return_value=cliente):
            resultado = __import__('asyncio').run(rotas_rtd.enviar_notificacao_rtd(
                request, str(uuid4()), str(uuid4()), json.dumps(pedido_valido()),
                UploadFile(filename='Documentos RTD.pdf', file=BytesIO(b'%PDF-teste')),
                'usuario-teste',
            ))

        self.assertEqual(resultado['estado'], 'CRIADO')
        self.assertEqual(resultado['protocolo'], '20261007000000001')
        self.assertTrue(any('INSERT INTO rtd_pedidos_aeri' in sql for sql in cursor.comandos))

    def test_cliente_homologacao_nao_envia_credencial_a_host_de_producao(self):
        cliente = ClienteRTD('token-hml', ambiente='homologacao')
        cliente.opener.open = Mock()
        with self.assertRaises(ErroRTD):
            cliente.baixar('https://apicentral.rtdbrasil.org.br/api/pedido/teste')
        cliente.opener.open.assert_not_called()

    def test_ambiente_desconhecido_e_rejeitado(self):
        with self.assertRaises(ErroRTD):
            ClienteRTD('teste', ambiente='https://evil.example')


if __name__ == '__main__':
    unittest.main()
