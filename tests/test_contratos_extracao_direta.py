"""Extração por clique: sem scheduler, sem OCR implícito e sem duplicar pendências."""
import io
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from backend.app.rotas import contratos as rotas
from backend.app.servicos.tri7 import ConfiguracaoTri7, ErroTri7
from backend.app.servicos.documentos_contratos import (
    extrair_documento, OcrIndisponivel, TempoExtracaoExcedido,
)


def pdf_teste(*, curta=False, imagem=False):
    import pymupdf
    with pymupdf.open() as pdf:
        p=pdf.new_page()
        p.insert_textbox(p.rect+(30,30,-30,-30),'Contrato digital de teste. '*40,fontsize=10)
        if curta:
            pdf.new_page().insert_text((40,40),'Assinaturas')
        if imagem:
            from PIL import Image
            buf=io.BytesIO();Image.new('RGB',(100,100),'white').save(buf,format='PNG')
            p=pdf.new_page();p.insert_image(p.rect,stream=buf.getvalue())
        return pdf.tobytes()


def test_pdf_textual_nao_precisa_executor_ou_ocr():
    with patch('backend.app.servicos.documentos_contratos.reconhecer_png') as ocr:
        r=extrair_documento(pdf_teste(curta=True),permitir_ocr=False,prazo=time.monotonic()+10)
    assert len(r['paginas'])==2 and not r['ocr']
    assert 'Assinaturas' in r['paginas'][1]['texto']
    assert r['paginas'][1]['insuficiente']
    ocr.assert_not_called()


def test_pdf_misto_nao_gera_ficha_parcial_nem_dispara_ocr():
    with patch('backend.app.servicos.documentos_contratos.reconhecer_png') as ocr:
        with pytest.raises(OcrIndisponivel,match='página 2'):
            extrair_documento(pdf_teste(imagem=True),permitir_ocr=False)
    ocr.assert_not_called()


def test_imagem_orienta_ocr_sem_executa_lo():
    """O caminho direto nao tenta OCR: manda o trabalho para a fila do executor.

    A mensagem dizia "o executor de OCR nao esta ativado", o que deixou de ser
    verdade quando ele foi ativado -- e mandava o conferente procurar
    configuracao em vez de esperar a fila.
    """
    with patch('backend.app.servicos.documentos_contratos.reconhecer_png') as ocr:
        with pytest.raises(OcrIndisponivel,match='fila do executor'):
            extrair_documento(b'\x89PNG\r\n',permitir_ocr=False)
    ocr.assert_not_called()


def test_prazo_expirado_nao_inicia_parser():
    with pytest.raises(TempoExtracaoExcedido):
        extrair_documento(pdf_teste(),permitir_ocr=False,prazo=time.monotonic()-1)


def registro(**mudancas):
    return dict(id=uuid4(),usuario='TESTE',protocolo='185623',documento_id='7',
        estado='AGUARDANDO',versao=1,progresso=0,payload_cifrado=None,erro=None,
        trava_ate=None,**mudancas)


@pytest.fixture
def ambiente(monkeypatch):
    cur=MagicMock()
    con=MagicMock();con.__enter__.return_value=con
    con.cursor.return_value.__enter__.return_value=cur
    monkeypatch.setattr(rotas,'conectar',lambda:con)
    monkeypatch.setattr(rotas,'cifrador',lambda:None)
    monkeypatch.setattr(rotas,'registrar_auditoria_cursor',MagicMock())
    base=MagicMock(configuracao=ConfiguracaoTri7('https://example.invalid','teste','teste'))
    base.listar_documentos_protocolo.return_value={'documentos':[{'ged_documento_id':7}]}
    monkeypatch.setattr(rotas,'cliente_tri7',lambda:base)
    cli=MagicMock();monkeypatch.setattr(rotas,'ClienteTri7',MagicMock(return_value=cli))
    req=SimpleNamespace(state=SimpleNamespace(sessao={'perfil':'USUARIO'}))
    return SimpleNamespace(cur=cur,con=con,req=req,cli=cli)


def test_clique_processa_id_solicitado_sem_varrer_fila(ambiente):
    a=ambiente;r=registro();final={**r,'estado':'EXTRAIDO','progresso':100}
    a.cur.fetchone.side_effect=[r,final]
    with patch.object(rotas,'_processar_contrato_reservado') as processar:
        resultado=rotas.extrair_agora(r['id'],a.req,'TESTE')
    assert resultado['estado']=='EXTRAIDO'
    assert processar.call_args.args==(r,processar.call_args.args[1])
    assert processar.call_args.kwargs['permitir_ocr'] is False
    assert processar.call_args.kwargs['cli'] is a.cli
    assert processar.call_args.kwargs['prazo']>time.monotonic()
    sql=' '.join(c.args[0] for c in a.cur.execute.call_args_list)
    assert "INTERVAL '90 seconds'" in sql
    assert 'SKIP LOCKED' not in sql


@pytest.mark.parametrize('estado',['EXTRAIDO','CONFERIDO','MINUTA'])
def test_repeticao_nao_sobrescreve_contrato_conferido(ambiente,estado):
    a=ambiente;r=registro();r['estado']=estado;a.cur.fetchone.return_value=r
    with patch.object(rotas,'_processar_contrato_reservado') as processar:
        assert rotas.extrair_agora(r['id'],a.req,'TESTE')['estado']==estado
    processar.assert_not_called()


def test_clique_concorrente_nao_duplica_extracao(ambiente):
    a=ambiente;r=registro();r.update(estado='PROCESSANDO',trava_ate=datetime.now(timezone.utc)+timedelta(seconds=60))
    a.cur.fetchone.return_value=r
    with patch.object(rotas,'_processar_contrato_reservado') as processar:
        assert rotas.extrair_agora(r['id'],a.req,'TESTE')['estado']=='PROCESSANDO'
    processar.assert_not_called()


def test_lease_expirada_permite_retomada(ambiente):
    a=ambiente;r=registro();r.update(estado='PROCESSANDO',trava_ate=datetime.now(timezone.utc)-timedelta(seconds=1))
    a.cur.fetchone.return_value=r
    with patch.object(rotas,'_processar_contrato_reservado') as processar:
        rotas.extrair_agora(r['id'],a.req,'TESTE')
    processar.assert_called_once()


def test_outro_usuario_nao_processa_documento(ambiente):
    a=ambiente;r=registro();r['usuario']='OUTRO';a.cur.fetchone.return_value=r
    with patch.object(rotas,'_processar_contrato_reservado') as processar:
        with pytest.raises(HTTPException) as erro: rotas.extrair_agora(r['id'],a.req,'TESTE')
    assert erro.value.status_code==404
    processar.assert_not_called()


def test_retomada_nao_bloqueada_pelo_limite_de_cinco(ambiente):
    a=ambiente;r=registro();a.cur.fetchone.return_value=r
    resultado=rotas.iniciar({'protocolo':'185.623','documentoId':'7'},a.req,'TESTE')
    assert resultado['id']==str(r['id'])
    sql=' '.join(c.args[0] for c in a.cur.execute.call_args_list)
    assert 'COUNT(*)' not in sql and 'INSERT INTO contratos_trabalhos' not in sql


@pytest.mark.parametrize('falha',[ErroTri7('Falha controlada na Tri7'),TempoExtracaoExcedido('Tempo excedido')])
def test_falha_libera_trava_e_nao_grava_extracao_parcial(ambiente,falha):
    a=ambiente;r=registro();a.cur.fetchone.return_value=r
    a.cli.listar_documentos_protocolo.return_value={'documentos':[{'ged_documento_id':7}]}
    a.cli.buscar_documento_ged.return_value={'dados':b'%PDF teste'}
    with patch.object(rotas,'extrair_contrato',side_effect=falha),patch.object(rotas,'_salvar') as salvar:
        resultado=rotas._processar_contrato_reservado(r,uuid4(),cli=a.cli,permitir_ocr=False)
    assert resultado['estado']=='FALHA';salvar.assert_not_called()
    sql=' '.join(c.args[0] for c in a.cur.execute.call_args_list)
    assert "estado='FALHA'" in sql and 'trava=NULL' in sql


def test_digitalizado_no_caminho_direto_volta_para_a_fila_do_executor(ambiente):
    """Nao e falha: e trabalho para o executor, que tem o motor de OCR.

    Em FALHA o trabalho morria ali -- processar_proximo_contrato so olha
    AGUARDANDO e PROCESSANDO vencido -- e "Retomar extracao" repetia o mesmo
    caminho sem OCR, falhando para sempre.
    """
    a=ambiente;r=registro();a.cur.fetchone.return_value=r
    a.cli.listar_documentos_protocolo.return_value={'documentos':[{'ged_documento_id':7}]}
    a.cli.buscar_documento_ged.return_value={'dados':b'%PDF teste'}
    with patch.object(rotas,'extrair_contrato',side_effect=OcrIndisponivel('Precisa de OCR')),          patch.object(rotas,'_salvar') as salvar:
        resultado=rotas._processar_contrato_reservado(r,uuid4(),cli=a.cli,permitir_ocr=False)
    assert resultado['estado']=='AGUARDANDO'
    salvar.assert_not_called()
    sql=' '.join(c.args[0] for c in a.cur.execute.call_args_list)
    assert "estado='AGUARDANDO'" in sql and 'trava=NULL' in sql
    assert "estado='FALHA'" not in sql


def test_executor_sem_motor_de_ocr_falha_em_vez_de_repescar(ambiente):
    """Quando quem nao tem OCR e o proprio executor, devolver a fila faria ele
    pegar o mesmo trabalho sem parar."""
    a=ambiente;r=registro();a.cur.fetchone.return_value=r
    a.cli.listar_documentos_protocolo.return_value={'documentos':[{'ged_documento_id':7}]}
    a.cli.buscar_documento_ged.return_value={'dados':b'%PDF teste'}
    with patch.object(rotas,'extrair_contrato',side_effect=OcrIndisponivel('Sem motor')),          patch.object(rotas,'_salvar'):
        resultado=rotas._processar_contrato_reservado(r,uuid4(),cli=a.cli,permitir_ocr=True)
    assert resultado['estado']=='FALHA'
    sql=' '.join(c.args[0] for c in a.cur.execute.call_args_list)
    assert "estado='FALHA'" in sql


def test_documento_desvinculado_do_protocolo_nao_e_baixado(ambiente):
    a=ambiente;r=registro();a.cur.fetchone.return_value=r
    a.cli.listar_documentos_protocolo.return_value={'documentos':[{'ged_documento_id':99}]}
    assert rotas._processar_contrato_reservado(r,uuid4(),cli=a.cli,permitir_ocr=False)['estado']=='FALHA'
    a.cli.buscar_documento_ged.assert_not_called()


def test_processamento_salva_versao_somente_com_lease_atual(ambiente):
    a=ambiente;r=registro();a.cur.fetchone.return_value=None
    a.cli.listar_documentos_protocolo.return_value={'documentos':[{'ged_documento_id':7}]}
    a.cli.buscar_documento_ged.return_value={'dados':b'%PDF teste'}
    with patch.object(rotas,'extrair_contrato',return_value={}),patch.object(rotas,'_salvar') as salvar:
        assert rotas._processar_contrato_reservado(r,uuid4(),cli=a.cli,permitir_ocr=False)['estado']=='LEASE_PERDIDO'
    salvar.assert_not_called()


@pytest.mark.parametrize('texto,esperado',[
    ('PREFEITURA MUNICIPAL DE MORRINHOS GUIA DE INFORMACAO Guia de Lancamento e '
     'Pagamento do Imposto Sobre Transmissao de Bens Imoveis ITBI INTER VIVOS',
     'guia de ITBI da Prefeitura'),
    ('CERTIDAO NEGATIVA DE DEBITOS expedida em favor de Fulano de Tal.',
     'certidão negativa'),
    ('PROCURACAO bastante que faz Fulano de Tal a Beltrano.',
     'procuração'),
])
def test_documento_errado_do_ged_e_nomeado_em_vez_de_culpar_o_banco(texto,esperado):
    """Dizer "fora da familia CAIXA" para uma guia de ITBI manda procurar
    problema no contrato certo. Dois conferentes bateram nisso escolhendo a guia
    no lugar do contrato, no mesmo protocolo do GED."""
    from backend.app.servicos import contratos as servicos
    with patch.object(servicos,'extrair_documento',
                      return_value={'texto':texto,'paginas':[],'ocr':False}):
        with pytest.raises(ValueError) as falha:
            servicos.extrair_contrato(b'%PDF teste')
    assert esperado in str(falha.value)
    assert 'escolha o contrato da CAIXA' in str(falha.value)
    assert 'fora da familia' not in str(falha.value)


def test_documento_desconhecido_mantem_o_aviso_generico():
    """Sem reconhecer o que e, o sistema nao inventa: diz que nao e da familia
    suportada e nao presume a instituicao credora."""
    from backend.app.servicos import contratos as servicos
    with patch.object(servicos,'extrair_documento',
                      return_value={'texto':'CONTRATO DE MUTUO COM O BANCO EXEMPLO S/A.',
                                    'paginas':[],'ocr':False}):
        with pytest.raises(ValueError,match='fora da fam'):
            servicos.extrair_contrato(b'%PDF teste')


def test_pagina_em_branco_nao_derruba_o_documento_digitalizado():
    """Verso em branco de folha digitalizada devolve texto vazio.

    Tratar vazio como "sem motor de OCR" abortava o documento inteiro: num
    contrato real de 24 paginas, 22 foram lidas e o trabalho morreu na 23.
    """
    from backend.app.servicos import documentos_contratos as docs
    with patch.object(docs.motor_ocr,'motor',return_value='windows'), \
         patch.object(docs.motor_ocr,'texto_de_pasta',return_value='   '):
        texto,metodo,_conf=docs.reconhecer_png(b'PNG falso')
    assert texto=='' and metodo=='OCR Windows'


def test_sem_motor_de_ocr_continua_avisando():
    from backend.app.servicos import documentos_contratos as docs
    with patch.object(docs.motor_ocr,'motor',return_value=None), \
         patch.object(docs.shutil,'which',return_value=None), \
         patch.dict('os.environ',{},clear=True):
        with pytest.raises(docs.OcrIndisponivel):
            docs.reconhecer_png(b'PNG falso')


def test_ficha_de_documento_digitalizado_diz_que_veio_de_ocr():
    """A marca liga as confirmacoes de seguranca da minuta: ela so pede
    conferencia dos campos que o OCR nao defende quando a natureza diz OCR."""
    from backend.app.servicos import contratos as servicos
    documento={'texto':'CAIXA ECONOMICA FEDERAL contrato de teste',
               'paginas':[{'metodo':'OCR Windows','texto':'x','insuficiente':False}],
               'ocr':True}
    ficha={'contrato':{'numero':'1'},'vendedores':[{}],'compradores':[{}],'origens':{'_natureza':'nato-digital'}}
    with patch.object(servicos,'extrair_documento',return_value=documento), \
         patch.object(servicos.servico,'para_json',return_value=ficha), \
         patch.object(servicos,'campos_ficha',return_value=[]):
        p=servicos.extrair_contrato(b'%PDF teste')
    assert p['ficha']['origens']['_natureza']=='digitalizado, lido por OCR (windows)'


def test_sucesso_limpa_o_erro_da_tentativa_anterior(ambiente):
    """Digitalizado passa por AGUARDANDO com o motivo gravado. Sem limpar, o
    trabalho terminava EXTRAIDO carregando o texto de uma falha superada."""
    a=ambiente;r=registro();a.cur.fetchone.return_value=r
    a.cli.listar_documentos_protocolo.return_value={'documentos':[{'ged_documento_id':7}]}
    a.cli.buscar_documento_ged.return_value={'dados':b'%PDF teste'}
    with patch.object(rotas,'extrair_contrato',return_value={'ficha':{}}), \
         patch.object(rotas,'_previa_minutas',return_value=None), \
         patch.object(rotas,'documentos_publicos',return_value=[{'ged_documento_id':7}]), \
         patch.object(rotas,'_salvar'):
        resultado=rotas._processar_contrato_reservado(r,uuid4(),cli=a.cli,permitir_ocr=True)
    assert resultado['estado']=='EXTRAIDO'
    conclusao=next(c.args[0] for c in a.cur.execute.call_args_list if 'progresso=100' in c.args[0])
    assert 'erro=NULL' in conclusao
