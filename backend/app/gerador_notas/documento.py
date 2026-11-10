# -*- coding: utf-8 -*-
"""Escreve a nota em .docx reaproveitando uma nota real como molde.

Nao usa python-docx, por escolha (ver Ambiente no CLAUDE.md). Um .docx e um zip de
XML: copiamos todas as pecas do molde e trocamos so word/document.xml, mantendo
inclusive o <w:sectPr> original - papel, margens e orientacao vem do arquivo do
cartorio, nao de numeros escritos aqui.

As medidas abaixo foram lidas do proprio acervo, em twips (1 cm = 566,93).
"""
import io
import re
import shutil
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET
from .baloes import renderizar_baloes

NS = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
      'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"')

ARIAL_10, ARIAL_9 = 20, 18          # meio-pontos
RECUO_1A_LINHA = 709                # 1,25 cm
RECUO_EXIGENCIA = 714               # 1,26 cm
DESLOCAMENTO = 357                  # 0,63 cm
RECUO_FUNDAMENTO = 2268             # 4,00 cm
ENTRELINHAS_CORPO = 360             # 1,5
ENTRELINHAS_FUNDAMENTO = 240        # 1,0
ESPACO_ANTES = 100                  # 5 pt

FORMATO = {
    "resumo_titulo": dict(tam=24, ind="", linha=280, antes=0, depois=300, alinhamento="center", manter=True),
    "resumo_balao": dict(tam=ARIAL_10, ind="", linha=280, antes=160, depois=120, alinhamento="left"),
    "resumo_meta": dict(tam=ARIAL_10, ind="", linha=240, antes=0, depois=100, alinhamento="left"),
    "resumo_item": dict(tam=ARIAL_10, ind="", linha=280, antes=240, alinhamento="left", manter=True),
    "resumo_recuado": dict(tam=ARIAL_10, ind='<w:ind w:left="850"/>', linha=240, antes=280, depois=100),
    "resumo_detalhe_inicio": dict(tam=ARIAL_10, ind='<w:ind w:left="850"/>', linha=240, antes=240, manter=True),
    "resumo_detalhe": dict(tam=ARIAL_10, ind='<w:ind w:left="850"/>', linha=240, antes=0, manter=True),
    "resumo_texto": dict(tam=ARIAL_10, ind="", linha=280, antes=0, alinhamento="left", depois=100),
    "corpo":       dict(tam=ARIAL_10, ind=f'<w:ind w:firstLine="{RECUO_1A_LINHA}"/>',
                        linha=ENTRELINHAS_CORPO, antes=0),
    "vazio":       dict(tam=ARIAL_10, ind="", linha=ENTRELINHAS_CORPO, antes=0),
    "exigencia":   dict(tam=ARIAL_10,
                        ind=f'<w:ind w:left="{RECUO_EXIGENCIA}" w:hanging="{DESLOCAMENTO}"/>',
                        linha=ENTRELINHAS_CORPO, antes=ESPACO_ANTES),
    "vazio_fund":  dict(tam=ARIAL_9, ind=f'<w:ind w:left="{RECUO_FUNDAMENTO}"/>',
                        linha=ENTRELINHAS_FUNDAMENTO, antes=0),
    "fund_norma":  dict(tam=ARIAL_9, ind=f'<w:ind w:left="{RECUO_FUNDAMENTO}"/>',
                        linha=ENTRELINHAS_FUNDAMENTO, antes=0),
    "fund_artigo": dict(tam=ARIAL_9, ind=f'<w:ind w:left="{RECUO_FUNDAMENTO}"/>',
                        linha=ENTRELINHAS_FUNDAMENTO, antes=0),
}


def _esc(t):
    return (t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _run(texto, marcas, tam, tab=False):
    fonte='Segoe UI Emoji' if 'icone' in marcas else 'Arial'
    prop = f'<w:rFonts w:ascii="{fonte}" w:hAnsi="{fonte}" w:cs="{fonte}"/><w:sz w:val="{tam}"/><w:szCs w:val="{tam}"/>'
    if "negrito" in marcas:
        prop += "<w:b/>"
    if "sublinhado" in marcas:
        prop += '<w:u w:val="single"/>'
    corpo = "<w:tab/>" if tab else ""
    if texto:
        corpo += f'<w:t xml:space="preserve">{_esc(texto)}</w:t>'
    return f"<w:r><w:rPr>{prop}</w:rPr>{corpo}</w:r>"


def _paragrafo(bloco):
    f = FORMATO[bloco.papel]
    extras = ('<w:pageBreakBefore/>' if f.get('quebra') else '') + ('<w:keepNext/>' if f.get('manter') else '')
    ppr = (f'<w:pPr>{extras}<w:jc w:val="{f.get("alinhamento", "both")}"/>' + f["ind"] +
           f'<w:spacing w:line="{f["linha"]}" w:lineRule="auto" '
           f'w:before="{f["antes"]}" w:after="{f.get("depois", 0)}"/></w:pPr>')
    runs = ""
    if bloco.papel == "exigencia":
        runs += _run(f"{bloco.numero}.", set(), f["tam"])
        runs += _run("", set(), f["tam"], tab=True)
    for texto, marcas in bloco.partes:
        runs += _run(texto, marcas, f["tam"])
    return f"<w:p>{ppr}{runs}</w:p>"


def _bloco_xml(bloco,largura_pt=466,identificador=10000):
    if bloco.papel!='resumo_balao':
        return _paragrafo(bloco)
    return renderizar_baloes(bloco.partes,_run,largura_pt,identificador)


def _largura_util(original):
    w='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
    sec=ET.fromstring(original).find('.//'+w+'sectPr')
    pagina=sec.find(w+'pgSz'); margem=sec.find(w+'pgMar')
    return (int(pagina.get(w+'w'))-int(margem.get(w+'left'))-int(margem.get(w+'right')))/20-2


def _sect_pr(molde_xml):
    """Papel e margens do molde. Sem isso a nota sairia em Letter."""
    m = re.search(r"<w:sectPr[ >].*?</w:sectPr>", molde_xml, re.S)
    return m.group(0) if m else ""


def grava(blocos, molde, destino):
    molde, destino = Path(molde), Path(destino)
    if not molde.is_file():
        raise FileNotFoundError(f"molde nao encontrado: {molde}")

    with zipfile.ZipFile(molde) as z:
        original = z.read("word/document.xml").decode("utf-8")
        pecas = [(i, z.read(i.filename)) for i in z.infolist()
                 if i.filename != "word/document.xml"]

    largura=_largura_util(original)
    corpo = "".join(_bloco_xml(b,largura,10000+i*1000) for i,b in enumerate(blocos))
    doc = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
           f"<w:document {NS}><w:body>{corpo}{_sect_pr(original)}</w:body></w:document>")

    destino.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as z:
        for info, dados in pecas:
            z.writestr(info, dados)
        z.writestr("word/document.xml", doc.encode("utf-8"))
    return destino


def em_bytes(blocos, molde, *, referencia=None, inicio_formal=None):
    """Gera o DOCX integralmente em memória para uso seguro no serverless."""
    molde = Path(molde)
    if not molde.is_file():
        raise FileNotFoundError(f"molde nao encontrado: {molde}")

    with zipfile.ZipFile(molde) as arquivo:
        original = arquivo.read("word/document.xml").decode("utf-8")
        pecas = [
            (item, arquivo.read(item.filename))
            for item in arquivo.infolist()
            if item.filename != "word/document.xml"
        ]

    corpo=''
    largura=_largura_util(original)
    for indice,bloco in enumerate(blocos):
        trecho=_bloco_xml(bloco,largura,10000+indice*1000)
        if indice==inicio_formal:
            trecho=trecho.replace('<w:pPr>','<w:pPr><w:pageBreakBefore/>',1)
        corpo+=trecho
    doc = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f"<w:document {NS}><w:body>{corpo}{_sect_pr(original)}</w:body></w:document>"
    )
    memoria = io.BytesIO()
    with zipfile.ZipFile(memoria, "w", zipfile.ZIP_DEFLATED) as arquivo:
        for item, dados in pecas:
            if referencia and item.filename.startswith('word/footer') and item.filename.endswith('.xml'):
                rodape=('<w:p><w:pPr><w:jc w:val="center"/><w:spacing w:before="80" w:after="0"/></w:pPr>'
                    +_run('Referência conjunta: '+str(referencia),set(),16)+'</w:p>')
                dados=dados.decode('utf-8').replace('</w:ftr>',rodape+'</w:ftr>').encode('utf-8')
            arquivo.writestr(item, dados)
        arquivo.writestr("word/document.xml", doc.encode("utf-8"))
    return memoria.getvalue()
