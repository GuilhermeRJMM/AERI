"""Regressões sintéticas do protocolo 185.771; sem dados pessoais do acervo."""
import copy
from types import SimpleNamespace
from unittest.mock import patch
from unittest.mock import MagicMock
from uuid import uuid4
from fastapi import HTTPException

import pytest

from backend.app.contratos_nucleo import matricula, qualificacao
from backend.app.contratos_nucleo.comparacao import area_m2, areas_iguais, designativo
from backend.app.servicos.contratos import (
    FolioAeri, VERSAO_CONFRONTO, confrontar, modelos, servico, aplicar_decisoes,
)

TEXTO = '''IMÓVEL: Lote 11, da Quadra 4, com área de 200 m².
PROPRIETÁRIA: Pessoa Anterior, casada.
AV-02-10.879 - Morrinhos, 26 de fevereiro de 1993. Construção de Prédio.
Averba-se uma casa de n° 20, com a área construída de 29,00m².
AV.08-10.879 - Data: 20.06.2025. RETIFICAÇÃO DE NOME EX-OFFICIO.
R.09-10.879 - Data: 20.06.2025. Protocolo n.º 177.528, de 18.06.2025. VENDA E COMPRA.
TRANSMITENTE: Pessoa Anterior, casada. ADQUIRENTE: Fulano de Teste, advogado,
CPF 123.456.789-01, casado sob o regime da comunhão parcial de bens. IMÓVEL: o desta matrícula.
'''
DESCRICAO = ('TERRENO: LOTE DE TERRAS N 11, DA QUADRA 04, COM ÁREA DE 200,00m2. '
             'CASA: UMA CASA RESIDENCIAL DE N 20, EDIFICADA NO TERRENO ACIMA CITADO, '
             'COM 29,00M2 DE ÁREA CONSTRUÍDA. IMÓVEL HAVIDO CONFORME AV-02 DA MATRÍCULA 10.879.')


def analise(titulares=None):
    return {'proprietarios_atuais':titulares or [{'nome':'Fulano de Teste','cpf':'123.456.789-01'}],
            'atos':[], 'imovel':{'situacao':{'status':'ATIVA'}, 'areas':[{'rotulo':'Área','valor':'200 m²'}],
              'identificacao':[{'rotulo':'Lote','valor':'11'},{'rotulo':'Quadra','valor':'4'}]}}


def ficha():
    return modelos.Ficha(matricula=modelos.Matricula(numero='10.879'),
        vendedores=[modelos.Pessoa(nome='Fulano de Teste',cpf='123.456.789-01',estado_civil='casado')],
        brutos={'imovel':DESCRICAO})


@pytest.mark.parametrize('a,b', [('200,00m2','200 m²'),('29,00M2','29 m²'),('1 ha','10.000 m²'),('1.234,50 m²','1234.5 m2')])
def test_area_ignora_apenas_formatacao_e_converte_unidade(a,b):
    assert areas_iguais(a,b)


@pytest.mark.parametrize('a,b', [('200,01 m²','200 m²'),('200 ha','200 m²'),('200','200 m²'),('29 m²','200 m²')])
def test_area_nao_esconde_divergencia_real(a,b):
    assert not areas_iguais(a,b)


def test_designativos_preservam_sufixos_e_letras():
    assert designativo('04')==designativo('4')
    assert designativo('09-A')==designativo('9-A')
    assert designativo('9-A')!=designativo('9-B')
    assert designativo('C')!=designativo('D')


def test_leitor_compartilhado_reconhece_av_antiga_e_nao_citacao_interna():
    texto=TEXTO.replace('IMÓVEL: o desta matrícula.', 'IMÓVEL: o desta matrícula, com construção citada na AV-02-10.879.')
    m=matricula.le(texto)
    assert [(a.rotulo,a.titulo) for a in m.atos]==[
        ('AV.02','CONSTRUÇÃO DE PRÉDIO'),('AV.08','RETIFICAÇÃO DE NOME EX-OFFICIO'),('R.09','VENDA E COMPRA')]
    assert m.averbacao('CONSTRUÇÃO').numero==2
    assert m.area=='200 m²'
    assert matricula.le('IMÓVEL: '+DESCRICAO).area=='200,00m2'
    assert 'casado' in m.proprietarios
    assert matricula.le(texto.replace('\n',' ')).averbacao('CONSTRUÇÃO').numero==2


def test_casa_nao_vira_area_do_terreno():
    m=matricula.le('IMÓVEL: TERRENO: lote 11. CASA: com área de 29 m².')
    assert not m.area


def test_reproducao_quatro_alertas_e_quadro_com_mesma_comparacao():
    p={'ficha':servico.para_json(ficha())}
    with patch('backend.app.servicos.contratos.analisar_matricula',return_value=analise()):
        r=confrontar(p,TEXTO,'10879')
    titulos={e['titulo'] for e in r['exigencias']}
    assert not titulos.intersection({'Área divergente','Edificação não averbada',
        'Qualificação do proprietário incompleta na matrícula','Ato citado não consta da certidão',
        'Remissão do título aponta outro ato'})
    campos={c['campo']:c for c in r['comparacoes']}
    for c in ('matricula.numero','imovel.area','imovel.lote','imovel.quadra'):
        assert campos[c]['situacao']=='COMPATIVEL'
    assert campos['imovel.area']['contrato']=='200,00m2'
    assert 'imovel.descricao' not in campos
    assert r['versaoRegras']==VERSAO_CONFRONTO


def test_area_divergente_continua_alertada_nas_duas_camadas():
    p={'ficha':servico.para_json(ficha())}
    p['ficha']['brutos']['imovel']=DESCRICAO.replace('200,00','201,00')
    with patch('backend.app.servicos.contratos.analisar_matricula',return_value=analise()):
        r=confrontar(p,TEXTO,'10879')
    assert any(e['titulo']=='Área divergente' for e in r['exigencias'])
    assert next(c for c in r['comparacoes'] if c['campo']=='imovel.area')['situacao']=='REVISAR'


@pytest.mark.parametrize('area,erro',[('29',False),('29,00',False),('30,00',True)])
def test_area_da_casa_nas_duas_ordens_sem_confundir_terreno(area,erro):
    f=ficha();f.brutos['imovel']=DESCRICAO.replace('29,00M2',area+'M2')
    c=qualificacao.Conferencia();qualificacao._confere_edificacao(f,matricula.le(TEXTO),c)
    assert bool(c.exigencias)==erro


def test_qualificacao_nao_introduz_transmitente_na_titularidade():
    f=FolioAeri(TEXTO,analise(),'10879')
    assert 'Pessoa Anterior' not in f.proprietarios
    assert 'casado' in f.qualificacao_titular(ficha().vendedores[0])
    sem_civil=TEXTO.replace('casado sob o regime da comunhão parcial de bens','residente na cidade')
    outro=FolioAeri(sem_civil,analise(),'10879')
    c=qualificacao.Conferencia();qualificacao._especialidade_subjetiva(ficha(),outro,c)
    assert any('estado civil' in e.detalhe for e in c.exigencias)


def test_qualificacao_de_outro_titular_nao_supre_campo_ausente():
    texto=TEXTO.replace('casado sob o regime da comunhão parcial de bens',
        'residente na cidade; Beltrano de Teste, CPF 987.654.321-00, casado')
    titulares=[{'nome':'Fulano de Teste','cpf':'123.456.789-01'}, {'nome':'Beltrano de Teste','cpf':'987.654.321-00'}]
    f=FolioAeri(texto,analise(titulares),'10879')
    assert 'casado' not in f.qualificacao_titular(ficha().vendedores[0])


def test_nao_extrair_qualificacao_nao_comprova_ausencia():
    f=FolioAeri(TEXTO,analise([{'nome':'Outro Titular','cpf':'987.654.321-00'}]),'10879')
    c=qualificacao.Conferencia();qualificacao._especialidade_subjetiva(ficha(),f,c)
    assert c.exigencias[0].grau==qualificacao.ATENCAO
    assert c.exigencias[0].titulo=='Qualificação não extraída para conferência'


@pytest.mark.parametrize('referencia,esperado', [('AV-02',None),('R-09',None),('AV-08','Remissão do título aponta outro ato'),('R-02','Ato citado não consta da certidão')])
def test_remissao_edificacao_nao_se_confunde_com_aquisicao(referencia,esperado):
    f=ficha();f.brutos['imovel']=DESCRICAO.replace('AV-02',referencia)
    c=qualificacao.Conferencia();qualificacao._confere_remissao_ao_ato(f,matricula.le(TEXTO),c)
    assert [e.titulo for e in c.exigencias]==([esperado] if esperado else [])


def test_minuta_exige_decisoes_e_nao_altera_ficha_original():
    original=servico.para_json(ficha())
    # Divergencia real de area. Antes este teste passava sem ela porque os
    # blocos de comprador/credora/valores/financiamento ficavam sempre
    # pendentes -- ou seja, ele testava aqueles blocos, nao a exigencia de
    # decisao sobre uma divergencia.
    original['brutos']['imovel']=DESCRICAO.replace('200,00','201,00')
    p={'ficha':original}
    with patch('backend.app.servicos.contratos.analisar_matricula',return_value=analise()):
        p['confronto']=confrontar(p,TEXTO,'10879')
    with pytest.raises(ValueError,match='campo pendente'):
        aplicar_decisoes(p,original,{},True)
    decisoes={c['campo']:{'acao':'CONTRATO','justificativa':'Conferido no original e na Tri7.'}
              for c in p['confronto']['comparacoes'] if c['situacao']!='COMPATIVEL'}
    antes=copy.deepcopy(original)
    nova,registradas=aplicar_decisoes(p,original,decisoes,True)
    assert nova==antes and original==antes and len(registradas)==len(decisoes)
    minutas=servico.atos(modelos.Ficha())
    assert set(minutas)=={'venda','alienacao'}


def test_rota_bloqueia_reutilizacao_de_comparacao_anterior_sem_gravar():
    from backend.app.rotas import contratos as rotas
    id=uuid4();registro={'id':id,'versao':3,'payload_cifrado':'teste'}
    req=SimpleNamespace(state=SimpleNamespace(sessao={'perfil':'ADMIN'}))
    with patch.object(rotas,'conectar',MagicMock()),patch.object(rotas,'_buscar',return_value=registro), \
            patch.object(rotas,'decifrar',return_value={'confronto':{'comparacoes':[]}}),patch.object(rotas,'_salvar') as salvar:
        with pytest.raises(HTTPException) as exc:
            rotas.gerar(id,{'versao':3},req,'TESTE')
    assert exc.value.status_code==409 and 'regras anteriores' in exc.value.detail
    salvar.assert_not_called()


def test_confronto_nao_pede_decisao_para_dados_da_nova_operacao():
    """Comprador, credora, valores e financiamento não têm contraparte na
    matrícula: emiti-los como pendência exigia decisão e justificativa por bloco
    sem nada a decidir, e afogava as divergências reais no formulário."""
    p = {'ficha': servico.para_json(ficha())}
    with patch('backend.app.servicos.contratos.analisar_matricula', return_value=analise()):
        confronto = confrontar(p, TEXTO, '10879')
    campos = {c['campo'] for c in confronto['comparacoes']}
    assert not campos & {'compradores', 'credora', 'valores', 'financiamento'}
    # Com tudo compativel nao sobra pendencia alguma. Antes, os quatro blocos
    # criavam quatro decisoes obrigatorias mesmo sem divergencia.
    assert all(c['situacao'] == 'COMPATIVEL' for c in confronto['comparacoes'])


def test_previa_devolve_a_minuta_sem_gravar_nada():
    """A prévia acompanha a digitação: recalcula e devolve, sem persistir.

    Se ela gravasse, cada tecla viraria versão nova no histórico e disputaria
    o controle de versão com a geração conferida.
    """
    from backend.app.rotas import contratos as rotas
    identificador = uuid4()
    registro = {'id': identificador, 'versao': 3, 'payload_cifrado': 'teste'}
    req = SimpleNamespace(state=SimpleNamespace(sessao={'perfil': 'ADMIN'}))
    with patch.object(rotas, 'conectar', MagicMock()), \
         patch.object(rotas, '_buscar', return_value=registro), \
         patch.object(rotas, '_salvar') as salvar:
        r = rotas.previa(identificador, {'ficha': servico.para_json(ficha())}, req, 'conferente')
    salvar.assert_not_called()
    assert set(r['minutasPrevia']) == {'venda', 'alienacao'}
    assert r['minutasPrevia']['venda']['texto']


def test_previa_com_ficha_incompleta_nao_derruba_a_extracao():
    """Ficha pela metade é o caso normal logo após extrair."""
    from backend.app.rotas import contratos as rotas
    # Ficha vazia ainda monta o esqueleto dos dois atos, com as pendências.
    vazia = rotas._previa_minutas({})
    assert set(vazia) == {'venda', 'alienacao'}
    assert vazia['venda']['pendencias']
    # Ficha corrompida devolve None em vez de estourar: a prévia é acessório e
    # não pode derrubar a extração nem a rota.
    assert rotas._previa_minutas({'vendedores': 'texto no lugar de lista'}) is None


def test_onus_vigente_carrega_a_data_do_cabecalho_do_ato():
    """FolioAeri montava o ônus sem `data`, e qualificacao._onus lê esse campo.

    O confronto estourava em AttributeError toda vez que a matrícula tinha um
    ônus vivo -- caso comum. Passou despercebido porque as matrículas testadas
    até então não tinham nenhum.
    """
    from backend.app.servicos.contratos import FolioAeri
    analise = {'atos': [
        {'codigo': 'R.03', 'categoria': 'ÔNUS', 'tipo_onus': 'ALIENAÇÃO FIDUCIÁRIA',
         'status': 'ATIVO', 'descricao': 'R-03-25.434- Em: 06.11.2014. ALIENAÇÃO FIDUCIÁRIA.'},
        {'codigo': 'R.04', 'categoria': 'ÔNUS', 'tipo_onus': 'HIPOTECA',
         'status': 'ATIVO', 'descricao': 'R.04-25.434 - Data: 25.03.2026. HIPOTECA.'},
        {'codigo': 'R.05', 'categoria': 'ÔNUS', 'tipo_onus': 'PENHORA',
         'status': 'ATIVO', 'descricao': 'texto sem cabeçalho legível'},
        {'codigo': 'R.06', 'categoria': 'ÔNUS', 'status': 'CANCELADO', 'descricao': 'Data: 01.01.2020.'},
    ]}
    onus = FolioAeri('texto', analise, '25434').onus_vigentes
    assert [o.rotulo for o in onus] == ['R.03', 'R.04', 'R.05'], 'cancelado nao entra'
    datas = {o.rotulo: o.data for o in onus}
    # Duas formas convivem no acervo: "Em:" e "Data:".
    assert datas['R.03'] == '06.11.2014'
    assert datas['R.04'] == '25.03.2026'
    assert datas['R.05'] == '', 'sem cabeçalho legível a data fica vazia, não quebra'


def test_exigencia_de_onus_funciona_com_e_sem_data():
    """A exigência vale mesmo sem data; ler o atributo direto derrubava o
    confronto inteiro por causa de um único ônus sem cabeçalho."""
    from types import SimpleNamespace
    from backend.app.contratos_nucleo import qualificacao
    registradas = []
    coletor = SimpleNamespace(acrescenta=lambda t, d, f, g: registradas.append((t, d)))
    folio = SimpleNamespace(onus_vigentes=[
        SimpleNamespace(rotulo='R.03', titulo='ALIENAÇÃO FIDUCIÁRIA', data='06.11.2014'),
        SimpleNamespace(rotulo='R.05', titulo='PENHORA', data=''),
        SimpleNamespace(rotulo='R.07', titulo='HIPOTECA'),   # sem o atributo
    ])
    qualificacao._onus(folio, coletor)
    assert len(registradas) == 3
    assert 'de 06.11.2014,' in registradas[0][1]
    assert 'consta o R.05 sem cancelamento' in registradas[1][1]
    assert 'consta o R.07 sem cancelamento' in registradas[2][1]
