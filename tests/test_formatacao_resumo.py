from xml.etree import ElementTree as ET
from backend.app.gerador_notas.documento import _paragrafo,NS
from backend.app.gerador_notas.redator import Bloco
from backend.app.gerador_notas.servico import previa

W={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
def p(papel):
    return ET.fromstring('<w:document '+NS+'>'+_paragrafo(Bloco(papel,partes=[('Exemplo.',set())]))+'</w:document>')
def test_titulo_e_identificacao_centralizados_no_word():
    for papel in ['resumo_titulo','resumo_meta']:
        assert p(papel).find('.//w:jc',W).get('{'+W['w']+'}val')=='center'
def test_orientacoes_com_recuo_consistente_e_sem_justificacao_estourada():
    for papel in ['resumo_recuado','resumo_detalhe_inicio','resumo_detalhe']:
        r=p(papel)
        assert r.find('.//w:jc',W).get('{'+W['w']+'}val')=='left'
        assert r.find('.//w:ind',W).get('{'+W['w']+'}left')=='425'
        assert r.find('.//w:keepLines',W) is not None
def test_metadados_identificados_no_html_para_mesma_formatacao():
    html=previa({'especie':'devolutiva','titulo':'Exemplo','protocolo':'999001','itens':[{'exigencia':'dare-parcelamento-sem-quitacao','valores':{}}]})['html']
    assert html.count('class="nota-resumo-meta"')==2
