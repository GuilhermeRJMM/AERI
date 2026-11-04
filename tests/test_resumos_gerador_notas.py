"""Cobertura editorial, identidade do par e preservação do texto formal."""
from io import BytesIO
import json
import re
from unittest.mock import patch
from zipfile import ZipFile
from xml.etree import ElementTree as ET

import pytest

from backend.app.gerador_notas.catalogo import BASE
from backend.app.gerador_notas.servico import previa, gerar_documento_com_resumo, redator, MOLDE
from backend.app.gerador_notas.resumo import catalogo_resumos
from backend.app.gerador_notas import documento
from backend.app.gerador_notas.redator import Item

CAT = json.loads((BASE / 'dados/exigencias.json').read_text(encoding='utf-8'))
EXIGENCIAS = CAT['exigencias']
ESPECIES = list(redator().modelo['especies'])
NS = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}


def dados_para(e, especie='devolutiva'):
    valores = {c: e.get('exemplos', {}).get(c, CAT['campos'].get(c, {}).get('exemplo', 'Exemplo de '+c)) for c in e.get('campos', [])}
    return {'especie': especie, 'protocolo': '186.999', 'titulo': 'Documento fictício para teste',
            'itens': [{'exigencia': e['id'], 'valores': valores}]}


def paragrafo_texto(p):
    return ''.join(t.text or '' for t in p.findall('.//w:t', NS))


def test_72_ids_exatamente_e_sem_campos_inventados():
    resumo = catalogo_resumos()['itens']
    assert len(resumo) == 72
    assert set(resumo) == {e['id'] for e in EXIGENCIAS}
    for e in EXIGENCIAS:
        textos = resumo[e['id']]
        assert len(textos) == 4 and all(isinstance(t, str) and t.strip() for t in textos)
        usados = set(re.findall(r'\{(\w+)\}', ' '.join(textos)))
        assert usados <= set(e.get('campos', [])), e['id']


@pytest.mark.parametrize('e', EXIGENCIAS, ids=lambda e:e['id'])
@pytest.mark.parametrize('especie', ESPECIES)
def test_cada_item_nas_quatro_especies_tem_nota_e_resumo_no_mesmo_docx(e, especie):
    dados = dados_para(e, especie)
    previa_nota = previa(dados)
    resumo = previa_nota['resumo']
    assert resumo['itens'][0]['exigencia'] == e['id']
    assert resumo['itens'][0]['numero'] == 1
    assert '«' not in json.dumps(resumo, ensure_ascii=False)
    nome, conteudo, avisos, resumo_doc = gerar_documento_com_resumo(dados)
    assert resumo_doc == resumo
    assert nome.endswith('.docx')
    assert e['id'] in avisos  # não muda a revisão jurídica original
    with ZipFile(BytesIO(conteudo)) as z:
        raiz = ET.fromstring(z.read('word/document.xml'))
    ps = raiz.findall('w:body/w:p', NS)
    pos = next(i for i,p in enumerate(ps) if paragrafo_texto(p) == 'RESUMO')
    assert ps[pos].find('w:pPr/w:pageBreakBefore', NS) is not None
    # Todo o prefixo XML da nota formal permanece exatamente como antes.
    itens = [Item(e['id'], dados['itens'][0]['valores'])]
    formal = redator().redige(especie, dados['titulo'], itens)
    with ZipFile(BytesIO(documento.em_bytes(formal, MOLDE))) as z:
        originais = ET.fromstring(z.read('word/document.xml')).findall('w:body/w:p', NS)
    assert [ET.tostring(p) for p in ps[:pos]] == [ET.tostring(p) for p in originais]
    texto = '\n'.join(paragrafo_texto(p) for p in ps[pos:])
    assert 'ITEM 1 - ' in texto and '186.999' in texto and resumo['vinculo'] in texto


def test_ordem_mesmos_dados_e_atualizacao_do_resumo():
    a, b = EXIGENCIAS[0], EXIGENCIAS[11]
    dados = dados_para(a)
    dados['itens'] += dados_para(b)['itens']
    r = previa(dados)['resumo']
    assert [x['exigencia'] for x in r['itens']] == [a['id'], b['id']]
    assert [x['numero'] for x in r['itens']] == [1, 2]
    dados['itens'][0]['valores']['area_documento'] = '123,456 ha'
    novo = previa(dados)['resumo']
    assert '123,456 ha' in novo['itens'][0]['pendencia']
    assert novo['vinculo'] != r['vinculo']
    dados['itens'].reverse()
    invertido = previa(dados)['resumo']
    assert invertido['itens'][0]['exigencia'] == b['id']
    assert invertido['vinculo'] != novo['vinculo']


def test_html_escapado_inclusive_titulo_protocolo_e_campos():
    dados = dados_para(EXIGENCIAS[0])
    dados['titulo'] = '<script>alert(1)</script>'
    dados['protocolo'] = '<img src=x>'
    dados['itens'][0]['valores']['area_documento'] = '<svg onload=alert(1)>'
    r = previa(dados)
    assert '<script>' not in r['html'] and '<svg' not in r['html'] and '<img' not in r['html']
    assert '&lt;svg' in r['html'] and '&lt;img' in r['html']


def test_faltas_na_previa_nao_geram_resumo_com_dados_inventados():
    r = previa({'especie': 'devolutiva', 'itens': [{'exigencia': EXIGENCIAS[0]['id'], 'valores': {}}]})
    assert len(r['faltando']) == 2
    assert '«' in r['resumo']['itens'][0]['pendencia']
    with pytest.raises(ValueError):
        gerar_documento_com_resumo({'especie': 'devolutiva', 'titulo':'Teste', 'itens':[{'exigencia': EXIGENCIAS[0]['id'], 'valores': {}}]})


def test_nota_nunca_e_baixada_sem_resumo_ao_faltar_modelo():
    dados = dados_para(EXIGENCIAS[0])
    with patch('backend.app.gerador_notas.resumo.catalogo_resumos', return_value={'versao':'teste','itens':{}}):
        with pytest.raises(ValueError, match='não foi gerada sem o resumo'):
            gerar_documento_com_resumo(dados)


def test_todos_os_72_juntos_com_assinatura_protocolo_e_alternativas():
    dados = dados_para(EXIGENCIAS[0])
    dados['itens'] = [dados_para(e)['itens'][0] for e in EXIGENCIAS]
    r = previa(dados)['resumo']
    assert len(r['itens']) == 72
    por_id = {i['exigencia']:i for i in r['itens']}
    for e in EXIGENCIAS:
        acao = por_id[e['id']]['comoResolver']
        if '{assinatura}' in e['defeito'] + e['providencia']:
            assert 'firma reconhecida' in acao and 'ICP-Brasil' in acao
        if '{protocolo_apartado}' in e['defeito'] + e['providencia']:
            assert 'protocolo separado' in acao
    assert 'cinco últimos exercícios' in por_id['itr-ausente']['comoResolver']
    assert 'ou' in por_id['usufruto-ativo-sem-anuencia']['comoResolver']
    assert 'se houver' in por_id['itbi-adquirentes-divergentes']['comoResolver']
    assert 'não serve para adquirir' in por_id['retificacao-acima-do-limite']['comoResolver']


def test_endpoint_entrega_par_conjunto_e_audita_sem_textos_pessoais():
    import base64
    from starlette.requests import Request
    from backend.app.rotas.gerador_notas import gerar_nota
    request = Request({'type':'http','method':'POST','path':'/api/gerador-notas/gerar','headers':[]})
    with patch('backend.app.rotas.gerador_notas.registrar_auditoria') as auditoria:
        resultado = gerar_nota(dados_para(EXIGENCIAS[0]), request, 'operador-ficticio')
    assert resultado['resumo_incluido'] is True
    assert len(resultado['resumo']['itens']) == 1
    with ZipFile(BytesIO(base64.b64decode(resultado['conteudo']))) as z:
        assert '>RESUMO<' in z.read('word/document.xml').decode()
    detalhes = auditoria.call_args.args[-1]
    assert detalhes == {'especie':'devolutiva','quantidade_exigencias':1,'resumo_incluido':True,'versao_resumo':catalogo_resumos()['versao']}


@pytest.mark.parametrize('rota', ['/previa', '/gerar'])
def test_rotas_continuam_exigindo_sessao_e_csrf(rota):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.app.database import preparar_banco
    from backend.app.rotas.gerador_notas import router
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[preparar_banco] = lambda: None
    with TestClient(app) as client:
        r = client.post('/api/gerador-notas' + rota, json=dados_para(EXIGENCIAS[0]))
    assert r.status_code in (401,403)


def test_layout_resumo_centralizado_rotulos_destacados_e_detalhes_separados():
    e = next(e for e in EXIGENCIAS if e['id'] == 'art-area-nao-corresponde')
    dados = dados_para(e)
    dados['itens'][0]['valores'] = {'area_art':'94,2547 ha','area_memorial':'60,4500 ha','area_matricula':'94,5000 ha'}
    r = previa(dados)
    item = r['resumo']['itens'][0]
    assert item['detalhes'] == [
        {'rotulo':'Na ART', 'valor':'94,2547 ha'},
        {'rotulo':'No memorial', 'valor':'60,4500 ha'},
        {'rotulo':'Na matrícula', 'valor':'94,5000 ha'},
    ]
    assert '94,2547' not in item['pendencia']
    assert '<h2>RESUMO</h2>' in r['html']
    assert '<strong><u>Por que isso é necessário:</u></strong>' in r['html']
    assert 'Resumo para o cliente' not in r['html']
    _, conteudo, _, _ = gerar_documento_com_resumo(dados)
    with ZipFile(BytesIO(conteudo)) as z:
        ps = ET.fromstring(z.read('word/document.xml')).findall('w:body/w:p',NS)
    titulo = next(p for p in ps if paragrafo_texto(p) == 'RESUMO')
    w = '{'+NS['w']+'}'
    assert titulo.find('w:pPr/w:jc',NS).get(w+'val') == 'center'
    detalhe = next(p for p in ps if paragrafo_texto(p).startswith('Na ART:'))
    assert detalhe.find('w:pPr/w:ind',NS).get(w+'left') == '850'
    assert detalhe.find('w:r/w:rPr/w:b',NS) is not None
    assert detalhe.find('w:r/w:rPr/w:u',NS) is not None


def test_detalhes_opcionais_nao_sao_inventados():
    e = next(e for e in EXIGENCIAS if e['id'] == 'art-area-nao-corresponde')
    dados = dados_para(e)
    dados['itens'][0]['valores'] = {'area_matricula':'94 ha'}
    item = previa(dados)['resumo']['itens'][0]
    assert item['detalhes'] == [{'rotulo':'Na matrícula','valor':'94 ha'}]
    dados['itens'][0]['valores'] = {}
    assert previa(dados)['resumo']['itens'][0]['detalhes'] == []
