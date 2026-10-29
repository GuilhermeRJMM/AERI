"""100 apresentações distintas e controles contra atribuição a terceiros."""
import unicodedata
from itertools import product

import pytest

from backend.app.servicos.custas import _registro_atende_custas
from backend.app.servicos.registros_auxiliares import extrair_indice_registro_auxiliar, _extrair_pessoas
from backend.app.servicos.buscas import hash_documento


CABECALHOS = (
    'EMITENTE/DEVEDORA/FIEL DEPOSITÁRIA',
    'EMITENTE/DEVEDORA/FIEL DEPOSITARIA',
    'EMITENTES/DEVEDORAS/FIÉIS DEPOSITÁRIAS',
    'EMITENTES/DEVEDORAS/FIEIS DEPOSITARIAS',
    'EMITENTE(S)/DEVEDOR(A)(S)/FIEL(IS) DEPOSITÁRIO(A)(S)',
    'EMITENTE/DEVEDOR/FIEL DEPOSITÁRIO',
    'EMITENTES/DEVEDORES/FIÉIS DEPOSITÁRIOS',
    'EMITENTE(S)/DEVEDOR(ES)/FIEL(IS) DEPOSITÁRIO(S)',
    'EMITENTE/DEVEDOR(A)/FIEL DEPOSITÁRIO(A)',
    'EMITENTE/DEVEDORA/DEPOSITÁRIA',
    'EMITENTES/DEVEDORAS/DEPOSITÁRIAS',
    'EMITENTE/DEVEDOR/FIEL',
    'EMITENTE/DEVEDORA',
    'EMITENTE E DEVEDORA E FIEL DEPOSITÁRIA',
    'EMITENTE - DEVEDORA - FIEL DEPOSITÁRIA',
    'EMITENTE — DEVEDORA — FIEL DEPOSITÁRIA',
    'EMITENTE – DEVEDORA – FIEL DEPOSITÁRIA',
    'EMITENTE, DEVEDORA E FIEL DEPOSITÁRIA',
    'EMITENTE & DEVEDORA & FIEL DEPOSITÁRIA',
    'DEVEDORA/FIEL DEPOSITÁRIA',
    'DEVEDORAS/FIÉIS DEPOSITÁRIAS',
    'DEVEDOR(A)(S)/FIEL(IS) DEPOSITÁRIO(A)(S)',
    'DEVEDORA(S)/DEPOSITÁRIA(S)',
    'EMITENTE/FIEL DEPOSITÁRIA',
    'EMITENTE/DEPOSITÁRIA',
)
SEPARADORES = (': ', ' :\n', ' — ', '\n')
CASOS = list(product(CABECALHOS, SEPARADORES))


@pytest.mark.parametrize('cabecalho,separador', CASOS)
def test_cem_formatos_preservam_pessoa_garantia_e_filtros(cabecalho, separador, monkeypatch):
    monkeypatch.setenv('AERI_BUSCAS_HMAC_KEY', 'chave-sintetica-cabecalhos')
    texto = (
        f'{cabecalho}{separador}Ana Exemplo, produtora rural, inscrita no CPF/MF sob o n.º 111.222.333-44, '
        'casada com Carlos Exemplo, inscrito no CPF sob o n.º 555.666.777-88. '
        'CREDORA: Empresa Exemplo, inscrita no CNPJ sob o n.º 12.345.678/0001-90. '
        'PRODUTO: SOJA; SAFRA: 2026/2027. OBJETO DA GARANTIA: Em ALIENAÇÃO FIDUCIÁRIA, soja. '
        'AVALISTA: Pedro Exemplo, inscrito no CPF sob o n.º 999.888.777-66.'
    )
    # Acentos decompostos aparecem em conversões de texto e PDFs.
    if separador == '\n':
        texto = unicodedata.normalize('NFD', texto)
    indice = extrair_indice_registro_auxiliar(100, texto)
    assert [p['nome'] for p in indice['pessoas']] == ['Ana Exemplo']
    assert indice['produtos'] == ['SOJA']
    assert indice['safras'] == ['2026/2027']
    assert indice['modalidade'] == 'ALIENAÇÃO'
    protegido = hash_documento('11122233344')
    assert indice['documentos_hash'] == [protegido]
    pedido = dict(nome='ANA EXEMPLO', documento='11122233344',
                  modalidade='ALIENACAO_FIDUCIARIA', produto='SOJA', safra='2026/2027')
    assert _registro_atende_custas(indice, pedido, protegido)
    for divergencia in (dict(produto='MILHO'), dict(safra='2025/2026'), dict(modalidade='PENHOR')):
        assert not _registro_atende_custas(indice, {**pedido, **divergencia}, protegido)
    assert '11122233344' not in str(indice)


def test_matriz_tem_cem_apresentacoes_unicas():
    assert len(CASOS) == len(set(CASOS)) == 100


@pytest.mark.parametrize('papel', ['CREDORA', 'AVALISTA', 'CÔNJUGE', 'PROPRIETÁRIA',
                                  'GARANTIDORA', 'ANUENTE', 'FIEL DEPOSITÁRIA', 'DEPOSITÁRIA'])
def test_papel_isolado_nao_se_torna_emitente_ou_devedor(papel):
    assert _extrair_pessoas(f'{papel}: Ana Exemplo, inscrita no CPF sob o n.º 111.222.333-44.') == []


def test_caso_devedora_depositaria_com_cpf_e_conjuge_sem_capturar_terceiros(monkeypatch):
    monkeypatch.setenv('AERI_BUSCAS_HMAC_KEY', 'chave-sintetica-cabecalhos')
    indice = extrair_indice_registro_auxiliar(101,
        'EMITENTE/DEVEDORA/FIEL DEPOSITÁRIA: Maria Exemplo, produtora rural, inscrita no CPF/MF '
        'sob o n.º 111.222.333-44, casada com Carlos Exemplo, inscrito no CPF sob o n.º 555.666.777-88. '
        'CREDORA: Empresa Exemplo. Produto: Soja; Safra: 2026/2027; '
        'OBJETO DA GARANTIA: Em ALIENAÇÃO FIDUCIÁRIA, a colheita de soja da safra 2026/2027.')
    assert [p['nome'] for p in indice['pessoas']] == ['Maria Exemplo']
    assert indice['pessoas'][0]['papel'] == 'EMITENTE/DEVEDORA/FIEL DEPOSITARIA'


def test_duas_emitentes_sao_preservadas():
    pessoas = _extrair_pessoas(
        'EMITENTES/DEVEDORAS/FIÉIS DEPOSITÁRIAS: 1)- Ana Exemplo, CPF 111.222.333-44; '
        'e 2)- Maria Exemplo, CPF 555.666.777-88. CREDOR: Empresa Exemplo.')
    assert [p['nome'] for p in pessoas] == ['Ana Exemplo', 'Maria Exemplo']
