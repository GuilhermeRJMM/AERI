from datetime import datetime,timezone
from pathlib import Path
from unittest.mock import MagicMock,patch

import pytest
import pymupdf

from backend.app.analise import contrato
from backend.app.servicos.pesquisa_titularidade import _item,pesquisar
from backend.app.servicos.buscas_pdf import gerar_pdf_buscas
from scripts.atualizar_executor import caminho_pacote


def linha(**mudancas):
    return dict(numero=100,nome='Ana Exemplo',nome_busca='ANA EXEMPLO',documento_hash='exato',
        documento_mascarado='***.***.333-44',tipo_documento='CPF',proporcao='100%',origem='Cadeia dominial',
        situacao='ATIVA',confianca='ALTA',veredito_cadeia='OK',indice_busca_versao=2,
        consultado_em=datetime.now(timezone.utc),motor_versao=contrato.versao_indice_motor()) | mudancas


def test_preparar_texto_prioriza_motor_antigo_sem_bloquear_ou_consultar_tri7():
    from backend.app.rotas import buscas
    con=MagicMock()
    con.__enter__.return_value=con
    previa={'itens':[{'matricula':100,'motorDesatualizado':True,'revisaoPendente':False}],
            'candidatos':[],'maisCandidatos':False}
    with patch.object(buscas,'conectar',return_value=con), \
         patch('backend.app.servicos.pesquisa_titularidade.pesquisar',return_value=previa), \
         patch('backend.app.servicos.buscas_mencoes.enfileirar_matriculas') as fila, \
         patch.object(buscas,'registrar_auditoria_cursor'), \
         patch.object(buscas,'_consultar_lote') as tri7:
        resultado=buscas.preparar_texto_pesquisa(buscas.PesquisaTexto(nome='Pessoa Exemplo'),MagicMock(),'usuario-teste')
    assert resultado['reconsultadas']==0
    assert fila.call_args.args[1:]==({100},'PESQUISA_MOTOR_ANTIGO')
    tri7.assert_not_called()
    con.commit.assert_called_once()


def test_hash_regras_independe_de_crlf_sem_ocultar_mudanca_real():
    original = Path.read_bytes
    try:
        contrato.hash_regras.cache_clear()
        esperado = contrato.hash_regras()
        with patch.object(Path,'read_bytes',lambda p:original(p).replace(b'\r\n',b'\n').replace(b'\n',b'\r\n')):
            contrato.hash_regras.cache_clear()
            assert contrato.hash_regras() == esperado
        with patch.object(Path,'read_bytes',lambda p:original(p)+b'\n# mudanca de regra\n'):
            contrato.hash_regras.cache_clear()
            assert contrato.hash_regras() != esperado
    finally:
        contrato.hash_regras.cache_clear()


def test_motor_antigo_e_sinalizado_sem_novo_bloqueio_de_texto():
    r = linha(); r['motor_versao']='2.0.0'
    item = _item(r,'ANA EXEMPLO',None)
    assert item['motorDesatualizado']
    assert item['confianca']=='BAIXA'
    assert not item['revisaoPendente']
    assert any('versão anterior' in a for a in item['alertas'])


def test_motor_atual_nao_recebe_alerta_inventado():
    item = _item(linha(),'ANA EXEMPLO','exato')
    assert not item['motorDesatualizado']
    assert item['confianca']=='ALTA'
    assert item['alertas']==[]


def test_documento_divergente_continua_marcado_para_conferencia():
    item = _item(linha(),'ANA EXEMPLO','outro')
    assert item['revisaoPendente']
    assert item['correspondencia']=='DOCUMENTO_DIVERGENTE'
    assert any('Documento diferente' in a for a in item['alertas'])


@pytest.mark.parametrize('pendencia',['motor_pendente','falhas_consulta','carga_inicial_pendente'])
def test_ressalva_cobre_motor_falha_e_carga_sem_bloquear_busca(pendencia):
    cur=MagicMock()
    cur.fetchone.side_effect=[{'total':0,'matriculas':0},
        dict(sem_titular=0,mencoes_pendentes=0,motor_pendente=0,falhas_consulta=0,
             carga_inicial_pendente=False,mais_antiga=None,**{}) | {pendencia:1}]
    cur.fetchall.side_effect=[[],[]]
    resultado=pesquisar(cur,nome='PESSOA EXEMPLO')
    assert resultado['quantidade']==0
    assert resultado['cobertura']['negativa_segura'] is False
    assert resultado['cobertura']['ressalvas']


def test_pdf_preserva_alerta_documento_versao_data_e_exporta_sem_conferir():
    r=linha();r['motor_versao']='2.0.0'
    item=_item(r,'ANA EXEMPLO','outro')
    pdf=gerar_pdf_buscas({'itens':[item],'cobertura':{'ressalvas':['Carga em atualização']}},'ANA EXEMPLO','',True)
    with pymupdf.open(stream=pdf,filetype='pdf') as doc:
        texto=''.join(p.get_text() for p in doc)
    assert 'Documento diferente do pesquisado' in texto
    assert 'versão anterior' in texto
    assert 'Consulta:' in texto
    assert '100%' in texto
    assert 'Carga em atualização' in texto
    assert 'sem conferência individual' in texto


@pytest.mark.parametrize('caminho',['../.env','/backend/app.py','C:/backend/app.py',
                                  'backend/../.env','backend/.env','scripts/outro.py',
                                  'backend\\..\\.env'])
def test_instalador_rejeita_escapes_e_credenciais(tmp_path,caminho):
    with pytest.raises(ValueError):
        caminho_pacote(caminho,tmp_path)


def test_instalador_so_instala_backend_e_worker(tmp_path):
    assert caminho_pacote('backend/app/analise/contrato.py',tmp_path).is_relative_to(tmp_path)
    assert caminho_pacote('scripts/worker_operacional.py',tmp_path).is_relative_to(tmp_path)
