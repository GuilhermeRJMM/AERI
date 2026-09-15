"""Integração opt-in em tabelas TEMP isoladas; nunca altera tabelas operacionais."""
import os
from pathlib import Path
from unittest.mock import patch

import pytest
import psycopg
from psycopg.rows import dict_row

from backend.app.rotas.buscas_indexacao import _salvar_indice, _salvar_ausencia, _proximo_modo_automatico
from backend.app.servicos.pesquisa_titularidade import pesquisar


@pytest.fixture
def banco_temporario():
    url=os.getenv('AERI_TEST_POSTGRES_URL')
    if not url:
        pytest.skip('Requer conexão explícita para tabelas temporárias.')
    con=psycopg.connect(url,row_factory=dict_row)
    try:
        with con.cursor() as cur:
            cur.execute("SET LOCAL search_path=pg_temp")
            for tabela in ('matriculas_busca_aeri','proprietarios_matriculas_busca_aeri',
                'sincronizacao_matriculas_busca_aeri','matriculas_busca_erros_aeri','auditorias_matriculas_aeri'):
                cur.execute(f'CREATE TEMP TABLE {tabela} (LIKE public.{tabela} INCLUDING ALL) ON COMMIT DROP')
            sql=(Path(__file__).parents[1]/'backend/app/migrations/047_buscas_atualizacao_e_mencoes.sql').read_text(encoding='utf-8')
            cur.execute(sql.replace('CREATE TABLE IF NOT EXISTS','CREATE TEMP TABLE IF NOT EXISTS'))
            cur.execute('INSERT INTO sincronizacao_matriculas_busca_aeri(id,limite_inicial,proximo_inicial) VALUES(1,100,101)')
            yield cur
    finally:
        con.rollback()
        con.close()


TEXTO='''MATRÍCULA 100. IMÓVEL: Lote urbano. PROPRIETÁRIO: João da Silva, CPF 123.456.789-01.
R.01-100 - VENDA E COMPRA. TRANSMITENTE: João da Silva, CPF 123.456.789-01.
ADQUIRENTE: Maria de Souza, CPF 987.654.321-00. IMÓVEL: A totalidade. DOU FÉ.'''


def test_sql_migracao_indexacao_busca_e_historico(banco_temporario,monkeypatch):
    monkeypatch.setenv('AERI_BUSCAS_HMAC_KEY','somente-testes-nao-e-chave-operacional')
    cur=banco_temporario
    indice,novo,_,_,_=_salvar_indice(cur,100,TEXTO)
    assert novo
    with patch('backend.app.rotas.buscas_indexacao.analisar_matricula') as analisar:
        _,novo,alterado,_,_=_salvar_indice(cur,100,TEXTO)
        assert not novo and not alterado
        analisar.assert_not_called()
    maria=pesquisar(cur,'Maria de Souza','98765432100')
    assert maria['totalMatriculas']==1
    assert maria['itens'][0]['correspondencia']=='DOCUMENTO_EXATO'
    antigo=pesquisar(cur,'João da Silva','12345678901')
    assert antigo['total']==0 and len(antigo['candidatos'])==1
    assert any(m['papel']=='TRANSMITENTE' for m in antigo['candidatos'][0]['mencoes'])
    _salvar_ausencia(cur,100,'SEM_TEXTO')
    maria=pesquisar(cur,'Maria de Souza','98765432100')
    assert maria['total']==1 and maria['itens'][0]['revisaoPendente']
    for _ in range(6):
        assert _proximo_modo_automatico(cur) in {'PRIORITARIA','REVISAO','NOVOS','LACUNAS','ERROS'}
