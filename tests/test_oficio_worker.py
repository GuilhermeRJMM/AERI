import asyncio
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch
import urllib.error

import pytest
from scripts.oficio import conector
from scripts.oficio.credencial_windows import proteger
from scripts.oficio.consultar import ErroConsulta


@pytest.mark.parametrize('url',['http://site.test','https://user:senha@site.test',
    'https://site.test/api','https://site.test?token=x','https://site.test#x','https://site.test:1234'])
def test_origem_exata_https(url):
    with pytest.raises(ValueError):
        conector.origem(url)


def test_sem_redirecionamento_e_sem_proxy_arbitrario():
    assert conector.SemRedirecionamento().redirect_request(None,None,None,None,None,None) is None
    with pytest.raises(ValueError):
        conector.enviar('https://teste.invalid','/oficio/Enviar',{},'segredo')


def test_dpapi_roundtrip_sem_credencial_em_claro():
    claro=b'{"token":"somente-credencial-sintetica"}'
    cifra=proteger(claro)
    assert claro not in cifra
    assert proteger(cifra,abrir=True)==claro


def test_job_nao_pode_escolher_url_acao_ou_outro_cartorio():
    valido={'id':'11111111-1111-4111-8111-111111111111','cartorio':'8422','minimo':257}
    assert conector.validar_trabalho(valido,'8422')==valido
    for dados in [valido|{'url':'https://evil.test'},valido|{'cartorio':'1234'},valido|{'minimo':True}]:
        with pytest.raises(ValueError):
            conector.validar_trabalho(dados,'8422')


def test_fila_vazia_nao_abre_chrome():
    with patch.object(conector,'enviar',return_value={'trabalho':None}), patch.object(conector,'abrir_sessao') as chrome:
        asyncio.run(conector.executar({'servidor':'https://teste.invalid','token':'sintetico','cartorio':'8422'},uma_vez=True))
        chrome.assert_not_called()


def test_duas_consultas_uma_conexao_sem_arquivo_e_sem_retry_de_resultado():
    aberturas=[];resultados=[];rodada=0
    trabalho={'id':'11111111-1111-4111-8111-111111111111','cartorio':'8422','minimo':257}
    @asynccontextmanager
    async def abrir():
        aberturas.append(True)
        yield object()
    def enviar(servidor,rota,dados,token):
        if rota=='/conector/proximo': return {'trabalho':trabalho}
        resultados.append(dados);return {'recebido':True}
    async def dormir(_):
        nonlocal rodada
        rodada+=1
        if rodada==2: raise asyncio.CancelledError()
    with patch.object(conector,'enviar',side_effect=enviar), patch.object(conector,'abrir_sessao',abrir), \
         patch.object(conector,'ler_sessao',new=AsyncMock(side_effect=[ErroConsulta('filtro_ativo_ou_desconhecido'),{'total':257}])), \
         patch.object(conector.asyncio,'sleep',side_effect=dormir):
        with pytest.raises(asyncio.CancelledError):
            asyncio.run(conector.executar({'servidor':'https://teste.invalid','token':'sintetico','cartorio':'8422'}))
    assert len(aberturas)==1
    assert resultados==[{'erro':'filtro_ativo_ou_desconhecido'},{'captura':{'total':257}}]


def test_token_revogado_para_worker_sem_repetir():
    with patch.object(conector,'enviar',side_effect=urllib.error.HTTPError('https://teste.invalid',401,'',None,None)) as http:
        with pytest.raises(ValueError):
            asyncio.run(conector.executar({'servidor':'https://teste.invalid','token':'sintetico','cartorio':'8422'}))
        assert http.call_count==1
