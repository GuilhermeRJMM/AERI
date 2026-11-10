from copy import deepcopy
from datetime import datetime, timezone, timedelta

import pytest

from backend.app.servicos.oficio_consultas import validar_captura


AGORA = datetime(2026, 11, 10, 15, tzinfo=timezone.utc)


def captura():
    return {'versao': 1, 'fonte': 'oficioeletronico.com.br', 'cartorio': '8422',
            'consultadoEm': AGORA.isoformat(), 'completo': True,
            'total': 1, 'paginas': [{'pagina': 1, 'itens': 1}],
            'itens': [{'protocolo': 'IN01708442C', 'prenotacao': '186804',
                       'status': 'Expedição de Intimação - RI',
                       'dataStatus': '2026-11-04', 'dataPedido': '2026-10-19',
                       'prazoPurga': '-'}]}


def test_contrato_valido_nao_altera_entrada():
    dados = captura()
    original = deepcopy(dados)
    assert validar_captura(dados, '8422', agora=AGORA) == original
    assert dados == original


@pytest.mark.parametrize('alteracao', [
    {'cartorio': '9999'}, {'fonte': 'evil.test'}, {'completo': False},
    {'total': 2}, {'total': True}, {'versao': True}, {'versao': 2},
    {'consultadoEm': '2026-11-10'}, {'consultadoEm': 'ontem'},
    {'consultadoEm': (AGORA - timedelta(days=2)).isoformat()},
    {'consultadoEm': (AGORA + timedelta(minutes=11)).isoformat()},
    {'cookies': 'nao aceitar'}, {'paginas': [{'pagina': 2, 'itens': 1}]},
    {'paginas': [{'pagina': 1, 'itens': 0}]}, {'itens': []},
])
def test_rejeita_captura_incompleta_ou_indevida(alteracao):
    dados = captura() | alteracao
    with pytest.raises(ValueError):
        validar_captura(dados, '8422', agora=AGORA)


@pytest.mark.parametrize('campo,valor', [
    ('protocolo', 'IN01708442C<script>'), ('prenotacao', 'abc'),
    ('status', '<img src=x>'), ('status', 'x' * 181), ('status', ''),
    ('dataStatus', '2026-02-30'), ('dataPedido', '19/10/2026'),
    ('cpf', '00000000000'), ('prazoPurga', '\x00'),
])
def test_rejeita_linha_invalida_ou_dado_extra(campo, valor):
    dados = captura()
    dados['itens'][0][campo] = valor
    with pytest.raises(ValueError):
        validar_captura(dados, '8422', agora=AGORA)


def test_rejeita_duplicidade_mesmo_com_total_correto():
    dados = captura()
    dados['itens'] *= 2
    dados['total'] = 2
    dados['paginas'][0]['itens'] = 2
    with pytest.raises(ValueError):
        validar_captura(dados, '8422', agora=AGORA)


def test_configuracao_obrigatoria():
    with pytest.raises(ValueError):
        validar_captura(captura(), '', agora=AGORA)
