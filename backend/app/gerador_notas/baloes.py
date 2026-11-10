"""Balões nativos DrawingML, editáveis, no fluxo do texto (não imagens)."""
import unicodedata
import copy
import re
from pathlib import Path
from functools import lru_cache
from xml.etree import ElementTree as ET

EMU_POR_PT=12700
MAX_LINHAS=6
N={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
   'a':'http://schemas.openxmlformats.org/drawingml/2006/main',
   'wp':'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing',
   'wps':'http://schemas.microsoft.com/office/word/2010/wordprocessingShape',
   'mc':'http://schemas.openxmlformats.org/markup-compatibility/2006',
   'v':'urn:schemas-microsoft-com:vml','o':'urn:schemas-microsoft-com:office:office',
   'w10':'urn:schemas-microsoft-com:office:word',
   'wp14':'http://schemas.microsoft.com/office/word/2010/wordprocessingDrawing',
   'w14':'http://schemas.microsoft.com/office/word/2010/wordml',
   'a14':'http://schemas.microsoft.com/office/drawing/2010/main'}
for prefixo,uri in N.items():
    ET.register_namespace(prefixo,uri)


@lru_cache(maxsize=1)
def _modelo():
    return ET.parse(Path(__file__).parent/'modelo/balao-nativo.xml').getroot()


def _largura_caractere(c):
    # Limites conservadores para Arial 10. Quebras explícitas tornam o resultado
    # independente de métricas/fontes instaladas no servidor Linux.
    if unicodedata.combining(c) or c in {'\ufe0f','\u200d','\n','\r'}:
        return 0
    if c.isspace(): return 3.4
    if unicodedata.category(c).startswith('S'): return 14
    if unicodedata.east_asian_width(c) in {'W','F'}: return 10
    if c in 'MW@%&mw': return 10
    return 7 if c.isupper() else 6


def _linhas(texto,largura):
    inicio=0
    while inicio<len(texto):
        fim=inicio; usado=0; espaco=None
        while fim<len(texto):
            if texto[fim]=='\n':
                fim+=1;break
            tamanho=_largura_caractere(texto[fim])
            if usado+tamanho>largura and fim>inicio:
                if espaco is not None: fim=espaco+1
                break
            usado+=tamanho
            if texto[fim].isspace(): espaco=fim
            fim+=1
        yield inicio,fim
        inicio=fim


def _trechos(partes,inicio,fim):
    pos=0
    for texto,marcas in partes:
        a=max(0,inicio-pos); b=min(len(texto),fim-pos)
        if a<b: yield texto[a:b],marcas
        pos+=len(texto)


def renderizar_baloes(partes,render_run,largura_pt=466,identificador=10000):
    texto=''.join(p[0] for p in partes)
    linhas=list(_linhas(texto,largura_pt-24)) or [(0,0)]
    saida=[]
    for offset in range(0,len(linhas),MAX_LINHAS):
        grupo=linhas[offset:offset+MAX_LINHAS]
        # Folga para a altura real das fontes/ícones do Word e para a ponta.
        altura=30+16*len(grupo)
        cx=round(largura_pt*EMU_POR_PT); cy=round(altura*EMU_POR_PT)
        numero=identificador+offset//MAX_LINHAS
        runs=[]
        for i,(a,b) in enumerate(grupo):
            if i: runs.append('<w:r><w:br/></w:r>')
            for trecho,marcas in _trechos(partes,a,b):
                run=render_run(trecho,marcas,20)
                # O texto deve ser escuro mesmo se o tema do Word usar fonte
                # branca para formas preenchidas. A nota formal não é alterada.
                runs.append(run.replace('</w:rPr>','<w:color w:val="10243A"/></w:rPr>'))
        conteudo=(''.join(runs))
        forma=copy.deepcopy(_modelo())
        ancora=forma.find('.//wp:anchor',N)
        ancora.set('allowOverlap','0')
        ancora.set('{'+N['wp14']+'}anchorId',f'{numero:08X}')
        ancora.find('wp:positionH/wp:posOffset',N).text='0'
        ancora.find('wp:positionV/wp:posOffset',N).text='0'
        ancora.find('wp:extent',N).attrib.update(cx=str(cx),cy=str(cy))
        ancora.find('wp:effectExtent',N).set('b',str(round(cy*.17)))
        wrap=ancora.find('wp:wrapNone',N)
        wrap.tag='{'+N['wp']+'}wrapTopAndBottom'
        ancora.find('wp:docPr',N).attrib.update(id=str(numero),name=f'Balão de orientação {numero}')
        ancora.find('.//a:xfrm/a:ext',N).attrib.update(cx=str(cx),cy=str(cy))
        # Mantém os ajustes nativos da forma, incluindo sua ponta.
        ancora.find('.//a:solidFill/a:srgbClr',N).set('val','EAF4FF')
        ancora.find('.//wps:bodyPr',N).set('anchor','t')
        p=ET.fromstring(f'<w:p xmlns:w="{N["w"]}"><w:pPr><w:spacing w:before="0" w:after="0" w:line="280" w:lineRule="exact"/><w:jc w:val="left"/></w:pPr>{conteudo}</w:p>')
        for caixa in forma.findall('.//w:txbxContent',N):
            for filho in list(caixa): caixa.remove(filho)
            caixa.append(copy.deepcopy(p))
        # Fallback nativo do Word para leitores anteriores ao DrawingML.
        v=forma.find('.//v:shape',N)
        v.set('id',f'Balao{numero}');v.set('{'+N['o']+'}spid',f'_x0000_s{numero}')
        v.set('type','#_x0000_t62');v.set('adj','3240,24840')
        v.set('fillcolor','#eaf4ff')
        estilo=v.get('style','')
        for chave,valor in [('width',largura_pt),('height',altura),('margin-left',0),('margin-top',0)]:
            estilo=re.sub(rf'(?<![a-z-]){chave}:[^;]+',f'{chave}:{valor}pt',estilo)
        v.set('style',estilo)
        vt=forma.find('.//v:textbox',N)
        vt.set('style','mso-fit-shape-to-text:f')
        vw=forma.find('.//w10:wrap',N)
        if vw is not None: vw.set('type','topAndBottom')
        saida.append('<w:p><w:pPr><w:spacing w:before="120" w:after="140"/></w:pPr><w:r>'+ET.tostring(forma,encoding='unicode')+'</w:r></w:p>')
    return ''.join(saida)
