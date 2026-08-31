"""Regressões da navegação por setores, decisões e processamento independente."""
import copy
import io
from datetime import date, datetime, timezone, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from backend.app.autenticacao import permissoes_sessao, exigir_permissao
from backend.app.permissoes import PADRAO_SUPERVISOR, projecao_permissoes
from backend.app.servicos.painel import modulos_permitidos
from backend.app.servicos.intimacoes import situacao_conferencia
from backend.app.servicos.automacoes_operacionais import dentro_do_horario, executar_passo
from backend.app.servicos.contratos import (ficha_de,servico,modelos,aplicar_decisoes,
    documentos_publicos,cifrar,decifrar,confrontar)
from backend.app.servicos.documentos_contratos import extrair_documento,DocumentoInvalido,normalizar_texto
from backend.app.rotas.contratos import _buscar,_versao
from backend.app.rotas.usuarios import _validar_permissoes


def sessao(perfil='USUARIO', **permissoes):
    return dict(perfil=perfil,permissoes_relacionais=permissoes,deve_trocar_senha=False)


def test_comum_nao_ganha_permissao_por_existir():
    assert not any(permissoes_sessao(sessao()).values())
    assert modulos_permitidos(permissoes_sessao(sessao()))==[]


def test_modulo_exige_setor_e_negacao_prevalece():
    assert not permissoes_sessao(sessao(acessar_buscas=True))['acessar_buscas']
    assert permissoes_sessao(sessao(acessar_buscas=True,acessar_certidao=True))['acessar_buscas']
    assert not permissoes_sessao(sessao(acessar_buscas=True,acessar_certidao=False))['acessar_buscas']
    assert 'up.concedida' in projecao_permissoes() and ' || ' in projecao_permissoes()


@pytest.mark.parametrize('perfil',['ADMIN','SUBSTITUTO'])
def test_administrativos_integrais(perfil):
    assert all(permissoes_sessao(sessao(perfil)).values())


def test_supervisor_nao_tem_bloqueio_hardcoded():
    p={k:True for k in PADRAO_SUPERVISOR}
    efetivas=permissoes_sessao(sessao('SUPERVISOR',**p))
    assert efetivas['acessar_contratos'] and not efetivas['ver_intimacoes']
    assert not efetivas['gerenciar_usuarios']
    p.update(ver_intimacoes=True,gerenciar_usuarios=True)
    assert permissoes_sessao(sessao('SUPERVISOR',**p))['ver_intimacoes']
    assert permissoes_sessao(sessao('SUPERVISOR',**p))['gerenciar_usuarios']


def test_rota_exige_acesso_no_backend():
    request=SimpleNamespace(state=SimpleNamespace(sessao=sessao(acessar_contratos=True)))
    with pytest.raises(HTTPException) as e: exigir_permissao('acessar_contratos')(request,'TESTE')
    assert e.value.status_code==403
    request.state.sessao=sessao(acessar_contratos=True,acessar_rgi=True)
    assert exigir_permissao('acessar_contratos')(request,'TESTE')=='TESTE'


def test_booleano_textual_nao_concede_acesso():
    with pytest.raises(HTTPException): _validar_permissoes({'permissoes':{'acessar_buscas':'false'}},'USUARIO')


@pytest.mark.parametrize('dias,cor',[(None,'vermelho'),(0,'verde'),(1,'amarelo'),(2,'vermelho'),(4,'vermelho'),(5,'cinza')])
def test_alerta_mesma_regra_da_rotina(dias,cor):
    hoje=date(2026,8,31)
    assert situacao_conferencia({'ultima_conferencia':hoje-timedelta(days=dias) if dias is not None else None},hoje)['classe']==cor


def test_janela_brasilia_e_nao_utc():
    c=dict(dias_semana=[0],hora_inicio=7,hora_fim=19)
    assert dentro_do_horario(c,datetime(2026,8,31,10,tzinfo=timezone.utc))
    assert not dentro_do_horario(c,datetime(2026,8,31,9,tzinfo=timezone.utc))


def test_lease_impede_duplicata():
    cur=MagicMock(); cur.fetchone.return_value=dict(habilitada=True,dias_semana=list(range(7)),hora_inicio=0,hora_fim=24,trava_ate=datetime.now(timezone.utc)+timedelta(minutes=10))
    con=MagicMock(); con.__enter__.return_value=con; con.cursor.return_value.__enter__.return_value=cur
    with patch('backend.app.servicos.automacoes_operacionais.conectar',return_value=con),patch('backend.app.servicos.automacoes_operacionais.cliente_tri7') as api:
        assert executar_passo('livro_protocolos')['estado']=='EM_EXECUCAO'
        api.assert_not_called()


def test_isolamento_trabalho_e_concorrencia():
    cur=MagicMock();cur.fetchone.return_value={'usuario':'OUTRA'}
    with pytest.raises(HTTPException) as e: _buscar(cur,'id','TESTE','USUARIO')
    assert e.value.status_code==404
    assert _buscar(cur,'id','TESTE','ADMIN')=={'usuario':'OUTRA'}
    with pytest.raises(HTTPException) as e: _versao({'versao':2},{'versao':1})
    assert e.value.status_code==409


def test_metadados_ged_nao_expoem_caminhos():
    assert documentos_publicos([{'ged_documento_id':7,'origem':'segredo','usuario_status':'pessoa'},None])[0].get('origem') is None


def test_payload_cifrado_e_integridade(monkeypatch):
    monkeypatch.setenv('AERI_CONTRATOS_ENCRYPTION_KEY','x'*40)
    valor=cifrar({'texto':'conteudo sigiloso'})
    assert 'conteudo' not in valor
    assert decifrar(valor)['texto']=='conteudo sigiloso'
    from cryptography.fernet import InvalidToken
    with pytest.raises(InvalidToken): decifrar(valor[:20]+'A'+valor[21:])


def test_roundtrip_empresa_e_terreno():
    ficha=modelos.Ficha(vendedores=[modelos.Empresa(razao_social='TESTE',representante=modelos.Pessoa(nome='REP'))],valores=modelos.Valores(terreno=10,obra=20))
    d=servico.para_json(ficha)
    assert servico.para_json(ficha_de(d))==d
    with pytest.raises(ValueError): ficha_de({'vendedores':'TESTE'})
    with pytest.raises(ValueError): ficha_de({'vendedores':[{'nome':{}}]})
    with pytest.raises(ValueError): ficha_de({'valores':{'total':float('nan')}})


def base_decisoes():
    f=servico.para_json(modelos.Ficha(matricula=modelos.Matricula(numero='1')))
    return {'ficha':f,'confronto':{'comparacoes':[dict(campo='matricula.numero',contrato='1',matricula='2',situacao='REVISAR',permiteMatricula=True)]}}


def test_decisao_aplicada_sem_mudar_original():
    p=base_decisoes(); d={'matricula.numero':{'acao':'MATRICULA','justificativa':'Conferido no texto atual'}}
    f,a=aplicar_decisoes(p,p['ficha'],d,True)
    assert f['matricula']['numero']=='2' and p['ficha']['matricula']['numero']=='1'
    assert a[0]['acao']=='MATRICULA'


@pytest.mark.parametrize('d,conf',[({},True),({'matricula.numero':{}},True),({'matricula.numero':{'acao':'MANUAL','justificativa':''}},True),({},False)])
def test_confirmacao_vazia_nao_gera(d,conf):
    p=base_decisoes()
    with pytest.raises(ValueError): aplicar_decisoes(p,p['ficha'],d,conf)


def test_edicao_apos_confronto_exige_nova_comparacao():
    p=base_decisoes(); f=copy.deepcopy(p['ficha']);f['matricula']['numero']='3'
    with pytest.raises(ValueError,match='novamente'): aplicar_decisoes(p,f,{},True)


def test_normalizacao_nao_corrige_numeros_silenciosamente():
    assert normalizar_texto('CPF O12 I99\r\n  R$ 1.100,00')=='CPF O12 I99\nR$ 1.100,00'


def test_pdf_digital_e_scan_usam_mesmo_pipeline():
    import pymupdf
    texto='CONTRATO TESTE '+('Texto digital verificável para teste. '*20)
    with pymupdf.open() as pdf:
        p=pdf.new_page();p.insert_textbox(p.rect+ (30,30,-30,-30),texto,fontsize=10)
        b=pdf.tobytes()
    with patch('backend.app.servicos.documentos_contratos.reconhecer_png') as ocr:
        d=extrair_documento(b)
        assert not d['ocr'];ocr.assert_not_called()
    from PIL import Image
    buf=io.BytesIO();Image.new('RGB',(200,200),'white').save(buf,format='PNG')
    with patch('backend.app.servicos.documentos_contratos.reconhecer_png',return_value=(texto,'OCR teste',87)) as ocr:
        d=extrair_documento(buf.getvalue())
        assert d['ocr'] and d['paginas'][0]['confianca']==87
        ocr.assert_called_once()
    with pytest.raises(DocumentoInvalido): extrair_documento(b'nao e documento')


def test_adaptador_compara_usando_motor_aeri():
    p=base_decisoes()
    r=confrontar(p,'IMÓVEL: Lote 3, área de 100m², em Morrinhos. PROPRIETÁRIO: Fulano de Teste.','1')
    assert r['comparacoes'][0]['situacao']=='COMPATIVEL'
    assert r['analise']['imovel'] and r['textoHash']


@pytest.mark.parametrize('conteudo',[None,{}, {'base64_data':'!!!'}, {'base64_data':''}])
def test_ged_rejeita_corpo_invalido(conteudo):
    from backend.app.servicos.tri7 import ClienteTri7,ConfiguracaoTri7,RespostaTri7Invalida
    cli=ClienteTri7(ConfiguracaoTri7('https://example.invalid','teste','teste'))
    with patch.object(cli,'_buscar_json_autenticado',return_value=(200,conteudo)):
        with pytest.raises(RespostaTri7Invalida): cli.buscar_documento_ged('1')


def test_ged_base64_decodificado():
    import base64
    from backend.app.servicos.tri7 import ClienteTri7,ConfiguracaoTri7
    cli=ClienteTri7(ConfiguracaoTri7('https://example.invalid','teste','teste'))
    with patch.object(cli,'_buscar_json_autenticado',return_value=(200,{'base64_data':base64.b64encode(b'%PDF teste').decode(),'content_type':'application/pdf'})):
        assert cli.buscar_documento_ged('1')['dados']==b'%PDF teste'


def test_toda_mutacao_contrato_exige_csrf_e_acesso():
    from backend.app.rotas.contratos import router,acesso
    from backend.app.autenticacao import proteger_csrf
    for rota in router.routes:
        deps={d.call for d in rota.dependant.dependencies}
        assert acesso in deps
        if rota.methods & {'POST','PUT','DELETE','PATCH'}: assert proteger_csrf in deps


def test_selecao_de_documento_fora_do_protocolo_bloqueada():
    from backend.app.rotas.contratos import iniciar
    with patch('backend.app.rotas.contratos.cifrador'),patch('backend.app.rotas.contratos.cliente_tri7') as tri7,patch('backend.app.rotas.contratos.conectar') as db:
        tri7.return_value.listar_documentos_protocolo.return_value={'documentos':[{'ged_documento_id':1}]}
        with pytest.raises(HTTPException) as e: iniciar({'protocolo':'2','documentoId':'9'},MagicMock(),usuario='TESTE')
        assert e.value.status_code==422
        db.assert_not_called()
