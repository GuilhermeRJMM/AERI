from io import BytesIO
from zipfile import ZipFile
from xml.etree import ElementTree as ET
import pytest

from backend.app.gerador_notas.servico import previa, gerar_documento_com_resumo, catalogo_para_tela
from backend.app.gerador_notas.campos import preparar_campos
from backend.app.gerador_notas.documento import _bloco_xml
from backend.app.gerador_notas.redator import Bloco
from test_resumos_gerador_notas import dados_para, EXIGENCIAS, NS


def test_resumo_primeiro_referencia_somente_rodape_e_caixa_visual_law():
    dados=dados_para(EXIGENCIAS[0])
    r=previa(dados)
    assert r['html'].index('nota-resumo') < r['html'].index('nota-formal')
    assert 'nota-resumo-balao' in r['html']
    _,conteudo,_,resumo=gerar_documento_com_resumo(dados)
    with ZipFile(BytesIO(conteudo)) as z:
        raiz=ET.fromstring(z.read('word/document.xml'))
        corpo=raiz.find('w:body',NS)
        assert ''.join(t.text or '' for t in corpo[0].findall('.//w:t',NS))=='RESUMO'
        assert resumo['vinculo'] not in ''.join(raiz.itertext())
        assert any(resumo['vinculo'] in z.read(p).decode() for p in z.namelist() if p.startswith('word/footer') and p.endswith('.xml'))
        assert raiz.find('.//w:shd',NS) is not None


@pytest.mark.parametrize('campo',['matricula','matricula_confrontante'])
@pytest.mark.parametrize('valor',['texto','R.20','123 e 456','-123','123.4','1e5','１２３'])
def test_numero_nao_aceita_texto_nem_junta_matriculas(campo,valor):
    with pytest.raises(ValueError):
        preparar_campos({'itens':[{'exigencia':'teste','valores':{campo:valor}}]})


def test_lista_numerica_independente_e_campos_livres_preservados():
    dados={'itens':[{'exigencia':'teste','valores':{'matriculas_confrontantes':['10100','10200'],
        'matricula':'12.345','area_matricula':'100,50 ha','denominacao_matricula':'Fazenda Exemplo'}}]}
    r=preparar_campos(dados)
    assert r['itens'][0]['valores']=={'matriculas_confrontantes':'10.100 e 10.200','matricula':'12.345',
        'area_matricula':'100,50 ha','denominacao_matricula':'Fazenda Exemplo'}
    assert dados['itens'][0]['valores']['matricula']=='12.345'


def test_metadados_de_campos_e_filtros_explicitos():
    c=catalogo_para_tela()
    assert c['campos']['matricula']['tipo']=='matricula'
    assert c['campos']['matriculas_confrontantes']['tipo']=='matriculas'
    assert c['campos']['area_matricula'].get('tipo') not in {'matricula','matriculas'}
    assert c['filtros_titulo']['perfis']
    assert all('contextos' in e for e in c['exigencias'])


def test_balao_longo_nao_usa_caixa_de_altura_fixa():
    texto='Explicação extensa e editável. '*100
    xml=_bloco_xml(Bloco('resumo_balao',partes=[(texto,set())]))
    assert xml.startswith('<w:tbl>')
    assert 'roundrect' not in xml
    assert texto in xml
