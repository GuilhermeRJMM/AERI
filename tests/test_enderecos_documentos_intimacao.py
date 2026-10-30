import pytest
from backend.app.servicos.enderecos_documentos_intimacao import preparar_enderecos, endereco_de_morrinhos


def dados(imovel='',enderecos=None):
    return dict(enderecoImovel=imovel,enderecos=enderecos or [],avisos=[],origens={'enderecoImovel':{'descricao_abertura_matricula':imovel}})


def resultados():
    return [dict(cep='75656-485',logradouro='Avenida Perimetral',bairro='Jardim Vera Cruz',localidade='Morrinhos',uf='GO',complemento='',unidade=''),
            dict(cep='75650-732',logradouro='Avenida Perimetral',bairro='Vila Santa Rosa',localidade='Morrinhos',uf='GO',complemento='',unidade='')]


def test_compacta_descricao_sem_area_confrontacoes_ou_proprietario_e_confirma_cep():
    endereco='Lote comercial n.º 02, Quadra 01, situado na Avenida Perimetral, Jardim Vera Cruz, nesta cidade, com área de 179,92m², sendo: 6,92m de frente'
    d=dados(endereco);preparar_enderecos(d,buscar=lambda _:resultados())
    assert d['enderecoImovel']=='Lote comercial n.º 02, Quadra 01, situado na Avenida Perimetral, Jardim Vera Cruz, Morrinhos-GO, CEP: 75.656-485'


@pytest.mark.parametrize('lista',[[],[dict(cep='11111-111',logradouro='Rua Outra',bairro='Jardim Vera Cruz',localidade='Morrinhos',uf='GO')],resultados()+[dict(cep='22222-222',logradouro='Avenida Perimetral',bairro='Jardim Vera Cruz',localidade='Morrinhos',uf='GO')]])
def test_sem_correspondencia_unica_nao_repete_cep_antigo_ou_generico(lista):
    d=dados('Avenida Perimetral, 336, Jardim Vera Cruz, Morrinhos-GO, CEP: 75650-000')
    preparar_enderecos(d,buscar=lambda _:lista)
    assert d['enderecoImovel'].endswith('CEP: ________') and '75650-000' not in d['enderecoImovel']


@pytest.mark.parametrize('endereco',[
    'Rua A, 1, Centro, Morrinhos-GO',
    'Fazenda Exemplo, zona rural, Morrinhos/GO',
    'Sítio Exemplo, Município de Morrinhos',
])
def test_urbano_e_rural_de_morrinhos_sao_aceitos(endereco):
    assert endereco_de_morrinhos(endereco)


@pytest.mark.parametrize('endereco',[
    'Rua Morrinhos, 1, Centro, Goiânia-GO',
    'Fazenda Exemplo, Morrinhos-CE',
    'Rua A, 2, Morrinhos do Sul-RS',
    'Fazenda sem município identificado',
])
def test_cidade_errada_ou_nao_confirmada_nao_entra(endereco):
    assert not endereco_de_morrinhos(endereco)


def test_varios_enderecos_locais_preservados_e_origem_oficio_prioritaria():
    d=dados(enderecos=['Rua da Projeção, 9, Morrinhos-GO'])
    d['enderecosDoOficio']=['Rua A, 1, Centro, Morrinhos-GO','Fazenda X, Município de Morrinhos','Rua B, Goiânia-GO']
    preparar_enderecos(d,buscar=lambda _:[])
    assert len(d['enderecosPrimeiraNotificacao'])==2
    assert len(d['enderecosForaDaPrimeiraNotificacao'])==1
    assert not any('Projeção' in a for a in d['enderecosPrimeiraNotificacao'])


def test_segmento_por_numeracao_do_viacep_nao_e_escolhido_sem_regra():
    r=resultados()[0];r['complemento']='lado par'
    d=dados('Avenida Perimetral, 336, Jardim Vera Cruz, Morrinhos-GO')
    preparar_enderecos(d,buscar=lambda _:[r])
    assert d['enderecoImovel'].endswith('________')

def test_inicial_do_bairro_so_expande_quando_rua_cidade_e_cep_sao_unicos():
    d=dados('Avenida Perimetral, 336, Quadra 01 Lote 02, Jardim V Cruz, Morrinhos-GO')
    preparar_enderecos(d,buscar=lambda _:resultados())
    assert 'Jardim Vera Cruz' in d['enderecoImovel']
    assert d['enderecoImovel'].endswith('CEP: 75.656-485')
    d=dados('Avenida Perimetral, 336, Jardim V Cruz, Morrinhos-GO')
    ambiguo=dict(resultados()[0],bairro='Jardim Verde Cruz',cep='75656-999')
    preparar_enderecos(d,buscar=lambda _:resultados()+[ambiguo])
    assert d['enderecoImovel'].endswith('CEP: ________')
def test_oficio_rural_quebrado_em_linhas_sem_coletar_remetente():
    from backend.app.servicos.anexos_intimacao import _enderecos_do_oficio
    texto = 'Fazenda Remetente, Morrinhos-GO\nFiduciante(s):\nPESSOA EXEMPLO\nFazenda Boa Vista, zona rural,\nMunicípio de Morrinhos\n3.1 Instruções\nFazenda Fora, Goiânia-GO'
    enderecos = _enderecos_do_oficio(texto)
    assert enderecos == ['Fazenda Boa Vista, zona rural, Município de Morrinhos']
