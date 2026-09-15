"""Cliente do executor: HTTPS restrito, lotes e cache limitado só em memória."""
import hashlib
import json
import os
import re
import ssl
import threading
import time
from collections import OrderedDict
from urllib.parse import urlsplit
from urllib.request import HTTPSHandler, HTTPRedirectHandler, ProxyHandler, Request, build_opener

URL_PADRAO = 'https://aeri-two.vercel.app/api/integracoes/executor/documentos-hash'
HOSTS = {'aeri-two.vercel.app', 'aeri-thaguienterprise.vercel.app', 'aeri-git-main-thaguienterprise.vercel.app'}
_cache = OrderedDict()
_trava = threading.RLock()
_config_ativa = None
_saude_ate = 0.0
_falha_ate = 0.0


class _SemRedirecionamento(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def configuracao():
    if os.getenv('VERCEL'):
        raise RuntimeError('O servidor exige a chave HMAC local; delegação recursiva bloqueada.')
    url = os.getenv('AERI_HASH_REMOTO_URL', URL_PADRAO).strip()
    token = os.getenv('AERI_HASH_REMOTO_TOKEN', '').strip()
    try:
        destino = urlsplit(url)
        valido = (destino.scheme == 'https' and destino.hostname in HOSTS
                  and destino.port in (None, 443) and not destino.username and not destino.password
                  and destino.path == '/api/integracoes/executor/documentos-hash'
                  and not destino.query and not destino.fragment)
    except ValueError:
        valido = False
    if not valido or not re.fullmatch(r'aeri_hash_[A-Za-z0-9_-]{43}', token):
        raise RuntimeError(
            'Configure AERI_BUSCAS_HMAC_KEY ou a credencial exclusiva AERI_HASH_REMOTO_TOKEN do executor.'
        )
    return url, token


def _preparar_config():
    global _config_ativa, _saude_ate, _falha_ate
    url, token = configuracao()
    identidade = (url, hashlib.sha256(token.encode()).hexdigest())
    if identidade != _config_ativa:
        _cache.clear()
        _saude_ate = _falha_ate = 0.0
        _config_ativa = identidade
    return url, token


def _solicitar(documentos, url, token):
    global _falha_ate, _saude_ate
    if time.monotonic() < _falha_ate:
        raise RuntimeError('Serviço de documentos indisponível; nova tentativa em até 60 segundos.')
    try:
        req = Request(url, data=json.dumps({'documentos': documentos}).encode('ascii'), method='POST',
            headers={'Authorization': 'Bearer '+token, 'Content-Type': 'application/json', 'Accept': 'application/json'})
        # Sem redirecionamento, proxy de ambiente ou URL fornecida por usuário.
        opener = build_opener(ProxyHandler({}), HTTPSHandler(context=ssl.create_default_context()), _SemRedirecionamento())
        with opener.open(req, timeout=15) as resposta:
            if resposta.status != 200 or resposta.headers.get_content_type() != 'application/json':
                raise ValueError('resposta')
            corpo = resposta.read(16385)
        if len(corpo) > 16384:
            raise ValueError('tamanho')
        dados = json.loads(corpo)
        from backend.app.servicos.buscas import HASH_DOCUMENTOS_VERSAO
        if not isinstance(dados, dict) or set(dados) != {'versao', 'hashes'} or dados['versao'] != HASH_DOCUMENTOS_VERSAO:
            raise ValueError('versao')
        hashes = dados['hashes']
        if (not isinstance(hashes, list) or len(hashes) != len(documentos)
                or any(not isinstance(h, str) or not re.fullmatch('[a-f0-9]{64}', h) for h in hashes)):
            raise ValueError('hashes')
    except Exception:
        # Não registrar corpo, documento, Authorization ou mensagem remota.
        _falha_ate = time.monotonic()+60
        _saude_ate = 0.0
        raise RuntimeError('Serviço de documentos indisponível. Nenhum resultado deve ser concluído neste lote.') from None
    _saude_ate = time.monotonic()+30
    return hashes


def verificar_servico():
    with _trava:
        url, token = _preparar_config()
        if time.monotonic() >= _saude_ate:
            _solicitar([], url, token)


def calcular_hashes(documentos):
    with _trava:
        url, token = _preparar_config()
        agora = time.monotonic()
        # Também autentica de tempos em tempos quando todos os documentos estão em cache.
        if agora >= _saude_ate:
            _solicitar([], url, token)
        for documento in list(_cache):
            if _cache[documento][1] <= agora:
                del _cache[documento]
        faltantes = list(dict.fromkeys(d for d in documentos if d not in _cache))
        obtidos = {d: _cache[d][0] for d in documentos if d in _cache}
        for inicio in range(0, len(faltantes), 100):
            lote = faltantes[inicio:inicio+100]
            hashes = _solicitar(lote, url, token)
            obtidos.update(zip(lote, hashes))
        # Só disponibiliza novos resultados depois de concluir todos os lotes.
        for documento in documentos:
            _cache[documento] = (obtidos[documento], time.monotonic()+300)
            _cache.move_to_end(documento)
        while len(_cache) > 4096:
            _cache.popitem(last=False)
        return [obtidos[d] for d in documentos]
