"""Regressões de pertinência e de exceções: não substituem revisão do registrador."""
import json
import pytest
from backend.app.gerador_notas.catalogo import Catalogo, BASE
from backend.app.gerador_notas.redator import Item, Redator
from backend.app.gerador_notas.servico import indice_artigos, legislacao

CAT=Catalogo()

def texto(id_):
    e=CAT.exigencia(id_)
    return (e['defeito']+' '+e['providencia']).lower()

def base(id_):
    e=CAT.exigencia(id_)
    return ' '.join(CAT.texto_dispositivo(f['norma'],f['artigo'],f.get('partes')) for f in e['fundamentos'])

def test_itcd_parcelado_nao_exige_quitacao_integral_incondicional():
    s=texto('dare-parcelamento-sem-quitacao')
    assert 'garantia real' in s and 'regularidade' in s
    assert 'todos os dares' not in s
    assert 'alternativamente' in base('dare-parcelamento-sem-quitacao').lower()

def test_itbi_cita_documentacao_e_identificacao_das_partes():
    for id_ in ['itbi-adquirentes-divergentes','itbi-transmitentes-divergentes','itbi-nao-apresentado']:
        b=base(id_).lower()
        assert 'comprovante de pagamento' in b
        assert 'transmitentes' in b and 'adquirentes' in b

def test_qualificacao_pessoal_cita_item_4_e_requisitos_do_registro():
    for id_ in ['qualificacao-endereco-ausente','qualificacao-profissao-ausente']:
        b=base(id_).lower()
        assert 'domicílio' in b and 'profissão' in b
        assert 'complementados' in b

def test_prenotacao_considera_dias_uteis_e_inercia():
    s=texto('prenotacao-vencida')
    assert 'úteis' in s and 'inércia' in s and 'prorrogação' in s
    assert 'dias úteis' in base('prenotacao-vencida').lower()

def test_certidao_civil_exclui_obito_e_titulo_judicial():
    s=texto('certidao-rcpn-vencida')
    assert 'óbito' in s and 'judicial' in s

def test_itr_admite_certidao_fiscal_e_excecoes():
    for id_ in ['itr-ausente','itr-nao-apresentado']:
        s=texto(id_)
        assert 'certidão' in s and 'dispensa' in s

def test_hipoteca_nao_impede_alienacao_so_por_existir():
    s=texto('hipoteca-ativa')
    assert 'não impede' in s
    assert 'não' in base('hipoteca-ativa') and 'alienar imóvel hipotecado' in base('hipoteca-ativa')

def test_usufruto_nao_exige_anuencia_para_vender_apenas_nua_propriedade():
    s=texto('usufruto-ativo-sem-anuencia')
    assert 'nua-propriedade' in s and 'preservado' in s

def test_indisponibilidade_nao_e_cancelada_por_simples_requerimento():
    s=texto('indisponibilidade-ativa')
    assert 'simples requerimento' in s and 'não' in s
    assert '320-H' in base('indisponibilidade-ativa')

def test_representacao_observa_dispensa_de_documentos_ja_qualificados():
    assert '806' in base('procuracao-poderes-ausente')
    assert '808' in base('pj-atos-constitutivos-ausentes')

def test_retificacao_nao_inventa_teto_legal_de_dez_por_cento():
    e=CAT.exigencia('retificacao-acima-do-limite')
    assert '10%' not in e['rotulo']
    assert not e.get('impossibilidade')
    assert not e.get('precedentes')
    assert 'não constitui' in texto(e['id'])

def test_anuencia_observa_notificacao_e_dispensas_legais():
    for id_ in ['confrontante-sem-declaracao','declaracao-limites-sem-assinatura']:
        s=texto(id_)
        assert 'notificação' in s and 'dispensa' in s

def test_edificacao_cita_dispensa_legal_de_habite_se():
    assert 'dispensa' in texto('construcao-sem-habite-se')
    assert '§ 1' in base('construcao-sem-habite-se')

def test_fundamentos_72_rastreaveis_sem_fingir_aprovacao_humana():
    dados=json.loads((BASE/'revisoes'/'2026-11-11.json').read_text(encoding='utf-8'))
    assert {x['id'] for x in dados['itens']}==set(CAT.exigencias)
    assert len(dados['itens'])==72
    for item in dados['itens']:
        assert item['correcao'] and item['aplicabilidade']
        assert item['fontes']
        assert not CAT.exigencia(item['id']).get('revisado')

def test_legislacao_exibida_usa_mesma_versao_dos_dispositivos_conferidos():
    indice=indice_artigos()
    for d in CAT.dispositivos.values():
        if d.get('conferido_em'):
            item=next(x for x in indice[d['norma']] if x['artigo']==d['artigo'])
            assert item['texto']==d['texto']
    norma=next(x for x in legislacao() if x['id']=='CNPFE-GO')
    assert norma['arquivo']=='https://tjdocs.tjgo.jus.br/documentos/913955'

def test_recortes_nao_inventam_texto_e_marcam_omissoes():
    for d in CAT.dispositivos.values():
        if not d.get('conferido_em'): continue
        for parte in [d['caput']]+[p['texto'] for p in d['partes']]:
            for segmento in parte.split(' (...) '):
                assert segmento.strip() in d['texto'], (d['norma'],d['artigo'],segmento)

def test_sobreposicao_e_indisponibilidade_nao_bloqueiam_partilha_automaticamente():
    assert 'não bloqueia' in texto('sobreposicao-de-area')
    assert 'sucessão causa mortis' in base('indisponibilidade-ativa')

@pytest.mark.parametrize('id_', list(CAT.exigencias))
def test_todo_fundamento_tem_fonte_oficial_e_trecho_valido(id_):
    e=CAT.exigencia(id_)
    assert e['fundamentos']
    for f in e['fundamentos']:
        # [] significa caput escolhido conscientemente; omissão não é escolha.
        assert 'partes' in f
        d=CAT.dispositivos[(f['norma'],f['artigo'])]
        assert d.get('url_oficial','').startswith('https://')
        assert len(d.get('sha256_fonte',''))==64
        assert CAT.texto_dispositivo(f['norma'],f['artigo'],f.get('partes'))
