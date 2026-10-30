from copy import deepcopy
from backend.app.servicos.enriquecimento_intimacao import complementar_preparacao
from backend.app.servicos.tri7 import ErroTri7
from backend.app.servicos.enriquecimento_intimacao import SIGNATARIO_PADRAO
import pytest

@pytest.fixture(autouse=True)
def sem_consulta_cep_externa(monkeypatch):
    monkeypatch.setattr('backend.app.servicos.enderecos_documentos_intimacao.consultar_viacep',lambda _:[])


TEXTO='''IMÓVEL: Lote 1, Quadra 2, Rua Exemplo, nesta cidade. PROPRIETÁRIO: HISTÓRICO.
R.05-1.234 - Data: 01.01.2020. COMPRA E VENDA. Cita garantia R.06 seguinte.
R.06-1.234 - Data: 01.01.2020. ALIENAÇÃO FIDUCIÁRIA.
DEVEDOR: PESSOA EXEMPLO, CPF 111.444.777-35. CREDOR: BANCO EXEMPLO, CNPJ 00.360.305/0001-04.
FORMA DO TÍTULO: Contrato de Venda e Compra de Imóvel e Alienação Fiduciária n.° 123456789012-0, com caráter de escritura pública, datado de 16.11.2023.
OUTORGA DE PROCURAÇÕES: em conformidade com o item 26 do contrato, poderes recíprocos.
Selo: 00000000000000000000001.
'''


class Tri7:
    def __init__(self, texto=TEXTO, itens=None):
        self.texto=texto
        self.itens=itens if itens is not None else [dict(natureza_formal_descricao='Intimação',dados_imovel={'numero_registro':1234},selos=[{'selo':'00000000000000000000002'}])]
    def buscar_texto_matricula(self, numero):
        return dict(numero_matricula=1234,texto=self.texto)
    def buscar_protocolo_completo(self, numero):
        return dict(protocolo={'protocolo_numero':123456},itens_do_pedido=self.itens)


def dados():
    return dict(matricula='1234',protocoloTri7='123456',contrato=dict(numero='123456789012',data='16/11/2023'),
                credor=dict(nome='BANCO EXEMPLO',cnpj='00360305000104'),devedores=[dict(nome='PESSOA EXEMPLO',cpf='11144477735')],
                titulo='',registroGarantia='',dataTituloAutuacao='',enderecoImovel='',avisos=[],origens={},inconsistencias=[],projecao={'valor':'10545.44'})


def test_preenche_garantia_titulo_data_clausula_selo_sem_inventar_ou_recalcular():
    d=dados();complementar_preparacao(d,'Escrevente Exemplo',cliente=Tri7())
    assert d['registroGarantia']=='R.06' and 'Alienação Fiduciária' in d['titulo']
    assert d['contrato']['numero']=='123456789012-0'
    assert d['dataTituloAutuacao']=='16/11/2023' and d['contrato']['data']=='16/11/2023'
    assert d['clausula']=='26 OUTORGA DE PROCURAÇÕES'
    assert d['selo']=='00000000000000000000002'
    assert d['signatario']==SIGNATARIO_PADRAO
    assert d['projecao']['valor']=='10545.44'
    assert 'PROPRIETÁRIO' not in d['enderecoImovel']
    assert d['consultaAutomatica']['garantiaConfirmada']
    assert 'texto' not in d['consultaAutomatica']


def test_titulo_longo_nao_e_truncado_em_220_caracteres():
    longo='Contrato de Venda e Compra '+('descrição literal extensa '*16)
    texto=TEXTO.replace('Contrato de Venda e Compra de Imóvel e Alienação Fiduciária',longo)
    d=dados();complementar_preparacao(d,cliente=Tri7(texto))
    assert len(d['titulo'])>220 and d['titulo'].endswith('extensa')


def test_credor_ou_devedor_diferente_nao_preenche_garantia():
    for campo in ('credor','devedores'):
        d=dados()
        if campo=='credor':d['credor']['cnpj']='12345678000199'
        else:d['devedores'][0]['cpf']='52998224725'
        complementar_preparacao(d,cliente=Tri7())
        assert not d['consultaAutomatica']['garantiaConfirmada'] and not d['registroGarantia']


def test_cpf_do_representante_do_banco_nao_e_tratado_como_devedor():
    texto=TEXTO.replace('FORMA DO TÍTULO:', 'Representado por PROCURADOR EXEMPLO CPF 529.982.247-25. FORMA DO TÍTULO:')
    d=dados();d['devedores'][0]['cpf']='52998224725'
    complementar_preparacao(d,cliente=Tri7(texto))
    assert not d['consultaAutomatica']['garantiaConfirmada']


def test_duas_garantias_mesmo_contrato_nao_escolhe_a_ultima():
    texto=TEXTO+'\n'+TEXTO[TEXTO.index('R.06'):].replace('R.06','R.08')
    d=dados();complementar_preparacao(d,cliente=Tri7(texto))
    assert not d['consultaAutomatica']['garantiaConfirmada']
    d=dados();d['registroIndicado']='R-6';complementar_preparacao(d,cliente=Tri7(texto))
    assert d['registroGarantia']=='R.06'


def test_ato_indicado_incompativel_nao_e_trocado_pelo_mais_recente():
    d=dados();d['registroIndicado']='R.09';complementar_preparacao(d,cliente=Tri7())
    assert not d['registroGarantia']


def test_garantia_cancelada_nao_completa_minuta():
    texto=TEXTO+'\nAV.07-1.234 - CANCELAMENTO. Cancela-se a alienação fiduciária objeto do R.06, por quitação integral.'
    d=dados();complementar_preparacao(d,cliente=Tri7(texto))
    assert not d['consultaAutomatica']['garantiaConfirmada']


def test_data_conflitante_vira_excecao_e_nao_e_sobreposta():
    d=dados();d['contrato']['data']='01/01/2020';complementar_preparacao(d,cliente=Tri7())
    assert d['contrato']['data']=='' and any(i['campo']=='dataContrato' for i in d['inconsistencias'])
    complementar_preparacao(d,cliente=Tri7())
    assert d['contrato']['data']==''  # repetir o complemento não resolve divergência silenciosamente


def test_selo_prenotacao_ou_garantia_antiga_nao_vira_selo_da_intimacao():
    item=dict(natureza_formal_descricao='Prenotação',dados_imovel={'numero_registro':1234},selos=[{'selo':'00000000000000000000003'}])
    d=dados();complementar_preparacao(d,cliente=Tri7(itens=[item]))
    assert not d.get('selo')


def test_selo_de_outra_matricula_ou_multiplo_exige_conferencia():
    base=Tri7().itens
    outro=deepcopy(base);outro[0]['dados_imovel']['numero_registro']=9999
    multiplo=deepcopy(base);multiplo[0]['selos'].append({'selo':'00000000000000000000004'})
    for itens in (outro,multiplo):
        d=dados();complementar_preparacao(d,cliente=Tri7(itens=itens));assert not d.get('selo')


def test_falha_matricula_nao_impede_consulta_independente_do_protocolo():
    class Falha(Tri7):
        def buscar_texto_matricula(self,n):raise ErroTri7('indisponível')
    d=dados();complementar_preparacao(d,cliente=Falha())
    assert not d['consultaAutomatica']['matriculaConsultada'] and d['selo']


def test_grupo_cota_e_consorcio_nao_e_numero_do_contrato_de_adesao():
    texto=TEXTO.replace('123456789012-0','9999999999')+' Cota n.º 0655 do Grupo n.º 000790: Contrato de Adesão nº 8888888888.'
    d=dados();d['contrato']['numero']='000790/0655';complementar_preparacao(d,cliente=Tri7(texto))
    assert d['registroGarantia']=='R.06' and d['contrato']['numero']=='000790/0655'


def test_resposta_outra_matricula_e_outro_protocolo_nao_sao_aceitos():
    class Outra(Tri7):
        def buscar_texto_matricula(self,n):return dict(numero_matricula=9999,texto=TEXTO)
        def buscar_protocolo_completo(self,n):return dict(protocolo={'protocolo_numero':9999},itens_do_pedido=self.itens)
    d=dados();complementar_preparacao(d,cliente=Outra())
    assert not d['registroGarantia'] and not d.get('selo')


def test_responsavel_padrao_do_setor_nao_depende_do_nome_da_conta():
    d=dados();complementar_preparacao(d,'Administrador do Sistema',cliente=Tri7())
    assert d['signatario']==SIGNATARIO_PADRAO
