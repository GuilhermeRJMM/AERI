import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

spec = importlib.util.spec_from_file_location('conector_oficio', Path(__file__).resolve().parents[1] / 'scripts/oficio/consultar.py')
conector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(conector)


def resultado(texto, erro=False):
    return SimpleNamespace(is_error=erro, content=[SimpleNamespace(text=texto)])


def test_leitura_json_do_transporte():
    assert conector.extrair_json(resultado('Resposta\n```json\n{"versao":1}\n```')) == {'versao':1}


@pytest.mark.parametrize('r', [resultado('sem json'), resultado('segredo', True),
    resultado('```json\n{}\n```\n```json\n{}\n```'), resultado('```json\n{"erro":"<segredo>"}\n```')])
def test_recusa_respostas_inesperadas_sem_expor_conteudo(r):
    with pytest.raises(ValueError) as erro:
        conector.extrair_json(r)
    assert 'segredo' not in str(erro.value)


def test_so_uma_aba_https_na_lista():
    assert conector.paginas_oficio(resultado('4: Portal (https://oficioeletronico.com.br/Cartorios/Intimacoes) [selected]')) == 4
    for texto in ['1: Fake (https://oficioeletronico.com.br.evil.test/Cartorios/Intimacoes)',
                  '1: Portal (http://oficioeletronico.com.br/Cartorios/Intimacoes)',
                  '1: Portal (https://oficioeletronico.com.br/Home/Index)',
                  '1: Portal (https://oficioeletronico.com.br/Cartorios/Intimacoes)\n2: Portal (https://oficioeletronico.com.br/Cartorios/Intimacoes)']:
        with pytest.raises(ValueError):
            conector.paginas_oficio(resultado(texto))


def test_diagnostico_preserva_mensagem_controlada_em_grupo_mcp():
    erro = ExceptionGroup('CONTEUDO REMOTO', [conector.ErroConsulta('Aba de consulta não encontrada.')])
    assert conector.mensagem_erro(erro) == 'Aba de consulta não encontrada.'
    assert conector.mensagem_erro(ExceptionGroup('SEGREDO', [RuntimeError('SEGREDO')])).endswith('RuntimeError')
    assert 'SEGREDO' not in conector.mensagem_erro(ValueError('SEGREDO'))
