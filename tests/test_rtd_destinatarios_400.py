"""400 combinações sintéticas; não são 400 documentos reais de cartórios."""
from itertools import product
from unittest.mock import patch

import pytest

from backend.app.servicos.documentos_intimacao import extrair_dados_documento_rtd
from backend.app.servicos.enderecos_documentos_intimacao import completar_ceps_rtd

PREFIXOS = ['Ao Ilmo', 'Ao Ilmo.', 'Ao Ilmo(a)', 'Ao Ilmo(a).', 'À Ilma.',
            'Aos Ilmos.', 'Aos Ilmos(as).', 'Ao Ilustríssimo', 'À Ilustríssima', 'Aos Ilustríssimos(as).']
TRATAMENTOS = ['Sr.', 'Sr(a).', 'Sr.(a)', 'Sr(a)', 'Sra.', 'Srs.', 'Srs(as).', 'Senhor', 'Senhora', 'Senhores(as).']
FORMATOS = [
    '1)-{a}, CPF: {ca}; 2)-{b}, CPF: {cb}',
    '1) {a} (CPF: {ca});\n2) {b} (CPF: {cb})',
    '{a} - CPF {ca};\n{b} - CPF {cb}',
    '1. {a}, CPF: {ca}; 2. LAURA BORGES\nDIAS PINHEIRO, CPF: {cb}',
]
CASOS = list(product(PREFIXOS, TRATAMENTOS, FORMATOS))
assert len(CASOS) == 400


@pytest.mark.parametrize('prefixo,tratamento,formato', CASOS)
def test_400_escritas_do_destinatario(prefixo, tratamento, formato):
    pessoas = formato.format(a='TULIO ALBERTO MACEDO OLIVEIRA', b='LAURA BORGES DIAS PINHEIRO',
                             ca='021.060.541-30', cb='038.153.271-21')
    texto = f'''IN01708442C
{prefixo} {tratamento} {pessoas}
Prezado(a) Senhor(a),
Na qualidade de Escrevente.
Endereço para notificação:
1) Avenida das Flores, Lote 25, Quadra 04, n.º 116, Residencial Portal do Lago, Morrinhos-GO, CEP:
75.656-024.
OBSERVAÇÕES:
Assinado por FULANO ESCREVENTE CPF: 999.999.999-99
'''
    with patch('backend.app.servicos.documentos_intimacao._ler_pdf', return_value=texto):
        dados = extrair_dados_documento_rtd(b'%PDF teste', 'IN01708442C')
    assert dados['devedores'] == [
        {'nome': 'TULIO ALBERTO MACEDO OLIVEIRA', 'cpf': '02106054130'},
        {'nome': 'LAURA BORGES DIAS PINHEIRO', 'cpf': '03815327121'},
    ]
    assert len(dados['enderecos']) == 1
    e = dados['enderecos'][0]
    assert (e['logradouro'], e['numero'], e['cep'], e['cidade'], e['uf']) == (
        'Avenida das Flores', '116', '75656024', 'Morrinhos', 'GO')
    assert e['complemento'] == 'Lote 25, Quadra 04'
    assert e['bairro'] == 'Residencial Portal do Lago'


def endereco(cep=''):
    return {'logradouro': 'Avenida das Flores', 'bairro': 'Residencial Portal do Lago',
            'cidade': 'Morrinhos', 'uf': 'GO', 'cep': cep}


def resposta(cep='75656-024', **extras):
    return dict(cep=cep, logradouro='Avenida das Flores', bairro='Residencial Portal do Lago',
                localidade='Morrinhos', uf='GO', **extras)


def test_viacep_preenche_ausente_e_reutiliza_consulta():
    from unittest.mock import Mock
    buscar = Mock(return_value=[resposta()])
    dados = completar_ceps_rtd({'enderecos': [endereco(), endereco()]}, buscar=buscar)
    assert all(e['cep'] == '75656024' for e in dados['enderecos'])
    buscar.assert_called_once_with('Avenida das Flores')


@pytest.mark.parametrize('retornos', [[], [resposta(), resposta('75656-025')],
                                     [resposta(complemento='lado par')],
                                     [dict(resposta(), bairro='Outro bairro')],
                                     [dict(resposta(), localidade='Outra cidade')]])
def test_viacep_nao_escolhe_cep_incompativel_ou_ambiguo(retornos):
    dados = completar_ceps_rtd({'enderecos': [endereco()]}, buscar=lambda _: retornos)
    assert dados['enderecos'][0]['cep'] == ''


def test_viacep_preserva_cep_do_pdf_e_nao_consulta_fora_de_morrinhos():
    def proibido(_):
        pytest.fail('Não deveria consultar ViaCEP')
    fora = dict(endereco(), cidade='Goiânia')
    dados = completar_ceps_rtd({'enderecos': [endereco('75656024'), fora]}, buscar=proibido)
    assert dados['enderecos'][0]['cep'] == '75656024'
    assert dados['enderecos'][1]['cep'] == ''


@pytest.mark.parametrize('cep', ['75.656-024', '75656-024', '75656024'])
def test_cep_quebrado_nao_vira_endereco_numerado(cep):
    from backend.app.servicos.documentos_intimacao import _enderecos_numerados_multilinha
    lista = _enderecos_numerados_multilinha(f'1) Rua A, Centro, Morrinhos-GO, CEP:\n{cep}.\n2) Rua B, Centro, Morrinhos-GO, CEP: 75650-082.')
    assert len(lista) == 2
    assert cep in lista[0]


def test_nao_captura_assinante_apos_o_bloco_destinatario():
    from backend.app.servicos.documentos_intimacao import _devedores_destinatarios
    texto = '''Ao Ilmo(a) Sr(a). ANA PEREIRA, CPF: 111.111.111-11
Endereço para notificação:
Rua A
Assinado por BRUNO ESCREVENTE, CPF: 222.222.222-22'''
    assert _devedores_destinatarios(texto) == [{'nome': 'ANA PEREIRA', 'cpf': '11111111111'}]
