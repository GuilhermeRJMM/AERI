from unittest.mock import patch
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from backend.app.rotas.gerador_notas import consultar_protocolo_nota
from backend.app.main import app
from backend.app.servicos.tri7 import ProtocoloTri7NaoEncontrado, ErroTri7, ConfiguracaoTri7Invalida


@pytest.mark.parametrize('numero', ['186.804', '186804', '00186804', ' 186804 '])
def test_consulta_apenas_titulo_sem_dados_pessoais(numero):
    with patch('backend.app.servicos.tri7.cliente_tri7') as cliente:
        cliente.return_value.buscar_protocolo_completo.return_value = {'protocolo': {
            'protocolo_numero': 186804, 'descricao_titulo': ' ESCRITURA\nPÚBLICA ',
            'adquirente_nome': 'DADO NÃO RETORNADO', 'adquirente_cpf_cnpj': 'NÃO RETORNADO'}, 'ged': [{'sigiloso': True}]}
        resposta = consultar_protocolo_nota({'protocolo': numero}, 'TESTE')
        assert resposta == {'protocolo': '186804', 'titulo': 'ESCRITURA PÚBLICA', 'fonte': 'Tri7 · descrição do título'}
        cliente.return_value.buscar_protocolo_completo.assert_called_once_with('186804')


@pytest.mark.parametrize('numero', ['', '0', 'abc', '186804/2026', '1.2', '../186804', '1'*11, 186804, None])
def test_numero_invalido_nao_chama_tri7(numero):
    with patch('backend.app.servicos.tri7.cliente_tri7') as cliente:
        with pytest.raises(HTTPException) as erro:
            consultar_protocolo_nota({'protocolo': numero}, 'TESTE')
        assert erro.value.status_code == 422
        cliente.assert_not_called()


@pytest.mark.parametrize('numero', [None, 186805])
def test_numero_na_resposta_deve_conferir(numero):
    with patch('backend.app.servicos.tri7.cliente_tri7') as cliente:
        cliente.return_value.buscar_protocolo_completo.return_value = {'protocolo': {'protocolo_numero': numero, 'descricao_titulo': 'OUTRO'}}
        with pytest.raises(HTTPException) as erro:
            consultar_protocolo_nota({'protocolo': '186804'}, 'TESTE')
        assert erro.value.status_code == 502


@pytest.mark.parametrize('titulo', [None, '', 123])
def test_ausencia_de_titulo_nao_e_substituida_por_natureza(titulo):
    with patch('backend.app.servicos.tri7.cliente_tri7') as cliente:
        cliente.return_value.buscar_protocolo_completo.return_value = {'protocolo': {'protocolo_numero': 186804, 'descricao_titulo': titulo}, 'itens_do_pedido': [{'natureza_formal_descricao': 'INVENTÁRIO'}]}
        assert consultar_protocolo_nota({'protocolo': '186804'}, 'TESTE')['titulo'] == ''


@pytest.mark.parametrize('falha,status', [(ProtocoloTri7NaoEncontrado('dado interno'),404), (ErroTri7('dado interno'),502), (ConfiguracaoTri7Invalida('dado interno'),503)])
def test_falhas_controladas_nao_expoem_detalhes(falha,status):
    with patch('backend.app.servicos.tri7.cliente_tri7') as cliente:
        cliente.return_value.buscar_protocolo_completo.side_effect = falha
        with pytest.raises(HTTPException) as erro:
            consultar_protocolo_nota({'protocolo': '186804'}, 'TESTE')
        assert erro.value.status_code == status
        assert 'dado interno' not in erro.value.detail


def test_sem_sessao_nao_consulta():
    from backend.app.database import preparar_banco
    with patch.dict(app.dependency_overrides, {preparar_banco: lambda: None}), patch('backend.app.servicos.tri7.cliente_tri7') as cliente:
        resposta = TestClient(app).post('/api/gerador-notas/consultar-protocolo',json={'protocolo':'186804'})
    assert resposta.status_code in {401,403}
    cliente.assert_not_called()
