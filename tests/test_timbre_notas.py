from hashlib import sha256
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET
import posixpath

from backend.app.gerador_notas.servico import MOLDE, gerar_documento


def test_timbre_e_logo_do_modelo_aprovado_sem_fontes_pesadas():
    with ZipFile(MOLDE) as z:
        assert sha256(z.read('word/header1.xml')).hexdigest() == '29c25d54ad229eee5d45263048871c6732b46f28f9618bc7db65577511fa32f6'
        assert sha256(z.read('word/footer1.xml')).hexdigest() == '484abc3cc5f414599063608c51bff9f561cb72e68d206661419c0581c4bb841e'
        assert sha256(z.read('word/media/image1.jpeg')).hexdigest() == '6ef0a77c4992949bd277c1689f992844819e810289a22bfe5a0507378e92e941'
        assert not any(n.startswith(('word/fonts/', 'customXml/')) for n in z.namelist())
        assert b'PAGE' in z.read('word/footer1.xml') and b'NUMPAGES' in z.read('word/footer1.xml')
        assert b'<w:updateFields w:val="true"/>' in z.read('word/settings.xml')
    assert MOLDE.stat().st_size < 300_000


def test_nota_e_resumo_preservam_timbre_a4_e_relacoes_validas():
    _, conteudo, _ = gerar_documento({'especie':'devolutiva','titulo':'Escritura fictícia',
        'protocolo':'186.999','itens':[{'exigencia':'cci-nao-averbado','valores':{'matricula':'12.345'}}]})
    ns = {'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
    with ZipFile(BytesIO(conteudo)) as z, ZipFile(MOLDE) as modelo:
        for n in ('word/header1.xml','word/footer1.xml','word/_rels/header1.xml.rels','word/media/image1.jpeg'):
            assert z.read(n) == modelo.read(n)
        corpo = ET.fromstring(z.read('word/document.xml'))
        secao = corpo.find('w:body/w:sectPr',ns)
        assert secao.find('w:headerReference',ns) is not None
        assert secao.find('w:footerReference',ns) is not None
        assert secao.find('w:pgSz',ns).get('{'+ns['w']+'}w') == '11907'
        assert secao.find('w:titlePg',ns) is None
        assert 'Resumo para o cliente' in z.read('word/document.xml').decode()
        for nome in z.namelist():
            if not nome.endswith('.rels'):
                continue
            base = posixpath.dirname(posixpath.dirname(nome))
            for r in ET.fromstring(z.read(nome)):
                if r.get('TargetMode') == 'External':
                    continue
                destino = posixpath.normpath(posixpath.join(base,r.get('Target',''))).lstrip('/')
                assert destino in z.namelist(), (nome,destino)
    assert len(conteudo) < 300_000
