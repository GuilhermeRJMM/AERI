import os
from unittest.mock import MagicMock, patch

from backend.app.rotas import buscas_indexacao as indice
from backend.app.servicos.buscas import texto_hash
from backend.app.servicos.buscas_mencoes import extrair_mencoes, INDICE_BUSCA_VERSAO
from backend.app.servicos.analise_matricula import analisar_matricula
from backend.app.servicos.pesquisa_titularidade import filtros_identidade, _item


def test_hash_estavel_nao_reanalisa_nem_apaga_titulares():
    cur=MagicMock()
    cur.fetchone.return_value=dict(texto_hash=texto_hash('texto'), motor_versao='motor',
        indice_busca_versao=INDICE_BUSCA_VERSAO, documentos_hash_versao=1,
        situacao='ATIVA', auditoria={'estado':'VALIDADA_AUTOMATICAMENTE'})
    with patch.object(indice,'versao_indice_motor',return_value='motor'), \
            patch.object(indice,'analisar_matricula') as analisar:
        _,novo,alterado,_,_=indice._salvar_indice(cur,1,'texto')
    analisar.assert_not_called()
    assert not novo and not alterado
    assert not any('DELETE FROM proprietarios' in c.args[0] for c in cur.execute.call_args_list)


def test_mudanca_de_versao_forca_reanalise_com_texto_igual():
    cur=MagicMock()
    cur.fetchone.return_value=dict(texto_hash=texto_hash('texto'), motor_versao='antigo',
        resultado_hash='a', indice_busca_versao=INDICE_BUSCA_VERSAO, documentos_hash_versao=1,
        auditoria={'estado':'VALIDADA_AUTOMATICAMENTE'})
    with patch.dict(os.environ,{'AERI_BUSCAS_HMAC_KEY':'chave-apenas-teste'}), \
            patch.object(indice,'analisar_matricula',side_effect=RuntimeError('REANALISOU')) as analisar:
        import pytest
        with pytest.raises(RuntimeError, match='REANALISOU'):
            indice._salvar_indice(cur,1,'texto')
    analisar.assert_called_once()


def test_resposta_vazia_nao_apaga_indice_anterior():
    cur=MagicMock();cur.fetchone.return_value={'texto_hash':'a'*64}
    indice._salvar_ausencia(cur,10,'SEM_TEXTO')
    comandos=[c.args[0] for c in cur.execute.call_args_list]
    assert not any('DELETE FROM proprietarios' in c for c in comandos)
    assert any('proxima_tentativa_em' in c for c in comandos)
    assert any('falha_consulta_em' in c for c in comandos)


def test_erro_permanente_nao_monopoliza_fila():
    modos=[]
    for ciclo in range(1,7):
        cur=MagicMock()
        cur.fetchone.side_effect=[dict(ciclo_automatico=ciclo,proximo_inicial=101,limite_inicial=100),{'total':1}]
        modos.append(indice._proximo_modo_automatico(cur))
    assert modos==['PRIORITARIA','NOVOS','REVISAO','LACUNAS','ERROS','REVISAO']


def test_mencoes_cobrem_venda_e_preservam_historico_sem_trocar_titular():
    texto='''MATRÍCULA 100. IMÓVEL: Lote. PROPRIETÁRIO: João da Silva, CPF 123.456.789-01.
R.01-100 - VENDA E COMPRA. TRANSMITENTE: João da Silva, CPF 123.456.789-01.
ADQUIRENTE: Maria de Souza, CPF 987.654.321-00. IMÓVEL: A totalidade. DOU FÉ.'''
    with patch.dict(os.environ,{'AERI_BUSCAS_HMAC_KEY':'chave-apenas-teste'}):
        resultado=analisar_matricula(texto,numero_matricula='100')
        mencoes=extrair_mencoes(texto,resultado)
    assert any(m['nome_busca']=='MARIA DE SOUZA' and m['papel']=='ADQUIRENTE' for m in mencoes)
    assert any(m['nome_busca']=='JOAO DA SILVA' and m['papel']=='TRANSMITENTE' for m in mencoes)
    assert [p['nome'] for p in resultado['proprietarios_atuais']]==['Maria de Souza']
    assert '123.456.789-01' not in str(mencoes)
    assert '98765432100' not in str(mencoes)


def test_busca_combina_documento_e_nome_sem_expor_documento_sql():
    with patch.dict(os.environ,{'AERI_BUSCAS_HMAC_KEY':'chave-apenas-teste'}):
        sql,params,nome,doc=filtros_identidade('JOÃO DA SILVA','123.456.789-01')
    assert ' OR ' in sql and ' AND ' in sql
    assert nome=='JOAO DA SILVA' and doc=='12345678901'
    assert '%JOAO%' in params and '%SILVA%' in params
    assert '12345678901' not in params


def test_homonimo_com_documento_diferente_exige_conferencia():
    from datetime import datetime,timezone
    row=dict(numero=1,nome='João',nome_busca='JOAO',documento_hash='outro',documento_mascarado='***',
        tipo_documento='CPF',proporcao='100%',origem='R.1',situacao='ATIVA',confianca='ALTA',
        veredito_cadeia='OK',indice_busca_versao=2,consultado_em=datetime.now(timezone.utc))
    item=_item(row,'JOAO','pesquisado')
    assert item['correspondencia']=='DOCUMENTO_DIVERGENTE'
    assert item['revisaoPendente'] and item['confianca']=='BAIXA'
