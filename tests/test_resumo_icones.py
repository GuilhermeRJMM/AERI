from io import BytesIO
from zipfile import ZipFile
from xml.etree import ElementTree as ET

from backend.app.gerador_notas.servico import previa,gerar_documento_com_resumo
from test_resumos_gerador_notas import dados_para,EXIGENCIAS,NS

ICONES=['📄','📋','🔎','⚖️','🛠️','📌']


def test_icones_com_rotulos_so_no_resumo_e_nota_formal_preservada():
    dados=dados_para(EXIGENCIAS[0])
    r=previa(dados)
    for icone in ICONES:
        assert icone in r['html']
        assert icone not in r['html_formal']
    assert r['html'].count('aria-hidden="true"')==6
    assert '<strong><u>Por que isso é necessário:</u></strong>' in r['html']
    assert '<strong><u>Como resolver:</u></strong>' in r['html']


def test_docx_icones_com_fonte_propria_e_corpo_arial():
    _,conteudo,_,_=gerar_documento_com_resumo(dados_para(EXIGENCIAS[0]))
    with ZipFile(BytesIO(conteudo)) as z:
        raiz=ET.fromstring(z.read('word/document.xml'))
    textos=''.join(raiz.itertext())
    for icone in ICONES:
        assert icone in textos
    mc='{http://schemas.openxmlformats.org/markup-compatibility/2006}'
    for alternative in raiz.iter(mc+'AlternateContent'):
        alternative.remove(alternative.find(mc+'Fallback'))
    runs=raiz.findall('.//w:r',NS)
    icones=[r for r in runs if any(i in ''.join(t.text or '' for t in r.findall('w:t',NS)) for i in ICONES)]
    assert len(icones)==6
    for r in icones:
        assert r.find('w:rPr/w:rFonts',NS).get('{'+NS['w']+'}hAnsi')=='Segoe UI Emoji'
    assert any(r.find('w:rPr/w:rFonts',NS).get('{'+NS['w']+'}hAnsi')=='Arial'
        for r in runs if r.find('w:rPr/w:rFonts',NS) is not None)
