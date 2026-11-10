from xml.etree import ElementTree as ET
from backend.app.gerador_notas.documento import _bloco_xml,NS
from backend.app.gerador_notas.redator import Bloco

N={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
   'a':'http://schemas.openxmlformats.org/drawingml/2006/main',
   'wp':'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing',
   'mc':'http://schemas.openxmlformats.org/markup-compatibility/2006'}


def raiz(texto):
    return ET.fromstring(f'<w:document {NS}><w:body>'+_bloco_xml(Bloco('resumo_balao',partes=[(texto,set())]))+'</w:body></w:document>')


def test_forma_nativa_de_balao_com_ponta_e_texto_editavel():
    r=raiz('Explicação profissional em linguagem simples.')
    geom=r.find('.//a:prstGeom',N)
    assert geom is not None and geom.get('prst')=='wedgeRoundRectCallout'
    assert r.find('.//w:txbxContent',N) is not None
    assert r.find('.//wp:anchor/wp:wrapTopAndBottom',N) is not None
    assert r.find('.//w:tbl',N) is None
    assert r.find('.//a:srgbClr',N).get('val')=='EAF4FF'


def test_texto_longo_continua_em_baloes_sem_perder_conteudo():
    texto='Orientação com providências claras para o interessado. '*100
    r=raiz(texto)
    assert len(r.findall('.//wp:anchor',N))>1
    for branch in ['Choice','Fallback']:
        assert ''.join(t.text or '' for e in r.findall('.//mc:'+branch,N) for t in e.findall('.//w:t',N))==texto
    ids=[e.get('id') for e in r.findall('.//wp:docPr',N)]
    assert len(ids)==len(set(ids))
    assert all(int(e.get('cy'))<2_000_000 for e in r.findall('.//wp:extent',N))
