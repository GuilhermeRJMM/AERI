"""Clareza editorial e prevenção de mensagens que pareçam autorizar o registro."""
from backend.app.gerador_notas.resumo import catalogo_resumos

def test_72_resumos_com_mensagem_especifica_e_acao():
    dados=catalogo_resumos()
    assert dados['versao']=='2026-11-11.2'
    assert len(dados['itens'])==72
    for id_,partes in dados['itens'].items():
        assert len(partes)==4
        assert all(10<=len(t)<=1100 for t in partes), id_
        for termo in ['juridicamente','modalidade legalmente','fólio real','formas admitidas de regularidade']:
            assert termo not in ' '.join(partes).lower(), id_

def test_itcd_parcelado_nao_parece_liberacao_automatica():
    titulo,problema,motivo,acao=catalogo_resumos()['itens']['dare-parcelamento-sem-quitacao']
    assert 'não é obrigatório quitar' not in motivo
    assert 'pode permitir o registro' not in motivo
    assert 'sozinho' in motivo and 'não' in motivo
    assert 'Secretaria de Estado da Economia' in acao
    assert 'garantia' in acao and 'registrada' in acao and 'total do imposto' in acao
    assert 'cartório' in acao and 'conferir' in acao

def test_itbi_explica_quem_precisa_corrigir_sem_repetir_numero_de_artigo():
    _,problema,motivo,acao=catalogo_resumos()['itens']['itbi-transmitentes-divergentes']
    assert '{transmitentes}' in problema and '{transmitentes_guia}' in problema
    assert 'prefeitura' in acao.lower()
    assert 'art.810' not in motivo.lower() and '§' not in motivo

def test_resumos_de_endereco_e_profissao_nao_sao_o_mesmo_texto_generico():
    dados=catalogo_resumos()['itens']
    assert 'endereço' in dados['qualificacao-endereco-ausente'][1]
    assert 'profissão' in dados['qualificacao-profissao-ausente'][1]
    assert dados['qualificacao-endereco-ausente'][3]!=dados['qualificacao-profissao-ausente'][3]
