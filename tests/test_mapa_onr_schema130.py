"""Pacote oficial por versão; nenhum acesso à rede ou dados reais nos testes."""
import hashlib
import json
from pathlib import Path

import pytest
from backend.app.servicos.mapa_onr import validar_json_mapa_onr

RAIZ = Path(__file__).resolve().parents[1]
SCHEMAS = RAIZ / 'backend/static/mapa_onr/schemas'


def judicial(tipo, **extras):
    return {'version':'1.3.0', 'cns':'026187', 'imoveis':[{
        'tipo_imovel':2 if tipo=='rural' else 1, 'contexto_'+tipo:1,
        'motivo_envio':2, 'tipo_matricula_transcricao':1,
        'numero_matricula':'9999', 'decisao_jud':True, **extras,
    }]}


@pytest.mark.parametrize('tipo', ['rural','urbano'])
def test_cumprimento_judicial_130_valido_no_backend(tipo):
    assert validar_json_mapa_onr(tipo,judicial(tipo))['valido']


@pytest.mark.parametrize('tipo', ['rural','urbano'])
@pytest.mark.parametrize('valor', [False,None,'true',1])
def test_nao_dispensa_campos_sem_booleano_judicial_verdadeiro(tipo,valor):
    assert not validar_json_mapa_onr(tipo,judicial(tipo,decisao_jud=valor))['valido']


@pytest.mark.parametrize('tipo', ['rural','urbano'])
def test_identificacao_obrigatoria_e_propriedades_adicionais_seguem_onr(tipo):
    for campo in ['numero_matricula','tipo_imovel','contexto_'+tipo,'motivo_envio']:
        d=judicial(tipo); del d['imoveis'][0][campo]
        assert not validar_json_mapa_onr(tipo,d)['valido'],campo
    # additionalProperties={} no ramo judicial publicado: manter paridade com o ONR.
    assert validar_json_mapa_onr(tipo,judicial(tipo,campo_inventado=True))['valido']


@pytest.mark.parametrize('versao', ['9.9.9','',None,13])
def test_versao_desconhecida_nunca_usa_esquema_por_aproximacao(versao):
    d=judicial('rural');d['version']=versao
    r=validar_json_mapa_onr('rural',d)
    assert not r['valido']
    assert any(e['caminho']=='version' for e in r['erros'])


def test_esquemas_intactos_e_rastreaveis_por_hash():
    manifesto=json.loads((SCHEMAS/'origem-oficial.json').read_text(encoding='utf-8'))
    assert manifesto['portal']=='https://ridigital.org.br/Suporte/frmITNS.aspx'
    assert manifesto['versao']=='1.3.0'
    for tipo,plural in [('rural','rurais'),('urbano','urbanos')]:
        nome=f'imoveis-{plural}-onr.schema.json'
        bruto=(SCHEMAS/nome).read_bytes()
        assert hashlib.sha256(bruto).hexdigest()==manifesto['arquivos'][nome]['sha256']
        atual=json.loads(bruto)
        assert atual['properties']['version']['const']=='1.3.0'
        antigo=json.loads((SCHEMAS/'v1.2.0'/nome).read_text(encoding='utf-8'))
        assert antigo['properties']['version']['const']=='1.2.0'


def test_arquivo_120_continua_validado_pela_versao_original():
    # Uma remessa vazia pode ser inválida por conteúdo; a versão conhecida não é erro.
    r=validar_json_mapa_onr('rural',{'version':'1.2.0','cns':'026187','imoveis':[]})
    assert not any(e['caminho']=='version' for e in r['erros'])
