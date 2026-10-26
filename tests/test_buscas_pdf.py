from unittest.mock import patch

import pymupdf
import pytest
from fastapi import HTTPException

from backend.app.rotas import buscas
from backend.app.servicos.buscas_pdf import gerar_pdf_buscas


def item(numero):
    return {'matricula':numero, 'nome':'José <Exemplo> & Maria', 'documento':'***.123.456-**',
            'situacao':'ATIVA', 'revisaoPendente':True}


def test_pdf_paginado_sem_exigir_conferencia(tmp_path):
    conteudo = gerar_pdf_buscas({'itens':[item(n) for n in range(12000,12180)]},
                                'José Exemplo', '', True)
    assert conteudo.startswith(b'%PDF')
    with pymupdf.open(stream=conteudo, filetype='pdf') as pdf:
        assert len(pdf) > 1
        texto = ''.join(p.get_text() for p in pdf)
        assert '12.000' in texto and '12.179' in texto
        assert 'José <Exemplo> & Maria' in texto
        assert '180 resultado(s) em 180 matrícula(s)' in texto
        assert 'sem conferência individual' in texto
        assert 'Página 1 de' in texto
        pdf[0].get_pixmap(matrix=pymupdf.Matrix(1.4,1.4)).save(tmp_path/'buscas-pdf-primeira.png')
        pdf[-1].get_pixmap(matrix=pymupdf.Matrix(1.4,1.4)).save(tmp_path/'buscas-pdf-ultima.png')
        (tmp_path/'buscas-exemplo.pdf').write_bytes(conteudo)


def test_pdf_vazio_nao_afirma_negativa_certificada():
    conteudo = gerar_pdf_buscas({'itens':[]}, 'Pessoa Exemplo', '', True)
    with pymupdf.open(stream=conteudo,filetype='pdf') as pdf:
        texto = ''.join(p.get_text() for p in pdf)
    assert 'Nenhum resultado localizado no índice' in texto
    assert 'não substitui certidão' in texto


def test_rota_exporta_todas_paginas_sem_preparar_ou_reconsultar():
    with patch.object(buscas,'pesquisar_combinado',return_value={'total':2,'itens':[item(1),item(2)]}) as pesquisar:
        resposta = buscas.exportar_pdf_pesquisa('José Exemplo','',False,'teste')
    pesquisar.assert_called_once_with('José Exemplo','',1,5001,False,False,'teste')
    assert resposta.media_type == 'application/pdf'
    assert resposta.headers['cache-control'] == 'no-store'
    assert 'attachment' in resposta.headers['content-disposition']
    assert resposta.body.startswith(b'%PDF')


def test_rota_nao_exporta_silenciosamente_uma_lista_truncada():
    with patch.object(buscas,'pesquisar_combinado',return_value={'total':5002,'itens':[]}), pytest.raises(HTTPException) as erro:
        buscas.exportar_pdf_pesquisa('Pessoa Exemplo','',True,'teste')
    assert erro.value.status_code == 422
