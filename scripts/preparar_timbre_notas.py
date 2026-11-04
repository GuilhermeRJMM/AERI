"""Importa somente o timbre aprovado; não copia fontes incorporadas ou dados ocultos."""
import argparse
import re
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from xml.etree import ElementTree as ET

RAIZ = Path(__file__).resolve().parents[1]
REL = 'http://schemas.openxmlformats.org/package/2006/relationships'
TIPOS = 'http://schemas.openxmlformats.org/package/2006/content-types'


def importar(origem):
    modelo = RAIZ / 'backend/app/gerador_notas/modelo'
    with ZipFile(origem) as z:
        partes = {n: z.read(n) for n in z.namelist()
                  if not n.startswith(('word/fonts/', 'customXml/'))}
        logo = z.read('word/media/image1.jpeg')
    # Conserva estilos e compatibilidade do modelo aprovado: eles também
    # determinam a posição dos desenhos ancorados do cabeçalho.
    rels = ET.fromstring(partes['word/_rels/document.xml.rels'])
    for r in list(rels):
        if r.get('Type', '').endswith('/customXml'):
            rels.remove(r)
    partes['word/_rels/document.xml.rels'] = ET.tostring(rels, encoding='utf-8', xml_declaration=True)
    # Não reserializar este XML: mc:Ignorable usa os prefixos declarados nele.
    fonte = partes['word/fontTable.xml'].decode('utf-8')
    partes['word/fontTable.xml'] = re.sub(r'<w:embed\w+\b[^>]*/>', '', fonte).encode('utf-8')
    settings = partes['word/settings.xml'].decode('utf-8')
    if '<w:updateFields' not in settings:
        settings = settings.replace('</w:settings>', '<w:updateFields w:val="true"/></w:settings>')
    partes['word/settings.xml'] = settings.encode('utf-8')
    if 'word/_rels/fontTable.xml.rels' in partes:
        del partes['word/_rels/fontTable.xml.rels']
    tipos = ET.fromstring(partes['[Content_Types].xml'])
    for t in list(tipos):
        if t.get('PartName','').startswith(('/customXml/', '/word/fonts/')) or t.get('Extension') == 'odttf':
            tipos.remove(t)
    partes['[Content_Types].xml'] = ET.tostring(tipos, encoding='utf-8', xml_declaration=True)
    destino = modelo / 'molde-nota-cartorio.docx'
    with ZipFile(destino,'w',ZIP_DEFLATED) as z:
        for nome, conteudo in partes.items():
            z.writestr(nome, conteudo)
    (RAIZ / 'backend/static/cartorio-primeiro-oficio-morrinhos.jpeg').write_bytes(logo)
    print('Timbre importado. Tamanho do molde:', destino.stat().st_size)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('origem', type=Path)
    importar(parser.parse_args().origem)
