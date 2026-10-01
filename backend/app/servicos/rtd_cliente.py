"""Cliente somente leitura da API do cliente ONRTDPJ. Nunca registra/paga pedidos."""
import hashlib
import io
import json
import os
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from pypdf import PdfReader

BASE = 'https://apicentral.rtdbrasil.org.br'
MAX_PDF = 25 * 1024 * 1024


class ErroRTD(Exception):
    """Mensagens controladas: não expõem JWT, URLs privadas ou resposta bruta."""


class SemRedirecionamento(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def validar_url(url):
    partes = urlsplit(str(url or ''))
    if (partes.scheme != 'https' or partes.hostname != 'apicentral.rtdbrasil.org.br'
            or partes.port not in (None, 443) or partes.username or partes.password):
        raise ErroRTD('RTD_DOCUMENTO_HOST: endereço do documento não autorizado.')
    return url


def protocolo_valido(valor):
    valor = str(valor or '')
    if not re.fullmatch(r'\d{17}', valor):
        raise ErroRTD('RTD_PROTOCOLO: protocolo inválido.')
    return valor


def identificar_ins(texto):
    return sorted({re.sub(r'\s+', '', m).upper()
                   for m in re.findall(r'\bIN\s*(?:\d\s*){8}C\b', texto, re.I)})


def identificar_destinatarios(texto):
    nomes = []
    padrao = r'(?:Ao|À|A)\s+Ilm[oa](?:\(a\))?\.?\s+Sr(?:a|\(a\))?\.?\s+([^\n()]{5,160}?)\s*\(\s*CPF(?:/MF)?\s*:'
    for m in re.finditer(padrao, texto, re.I):
        nome = re.sub(r'\s+', ' ', m.group(1)).strip(' .,:;')
        if len(nome.split()) >= 2 and not re.search(r'\d|[/<>]', nome) and nome.upper() not in [n.upper() for n in nomes]:
            nomes.append(nome)
    return nomes


def extrair_documento_pdf(conteudo):
    if len(conteudo) > MAX_PDF or not conteudo.startswith(b'%PDF'):
        raise ErroRTD('RTD_PDF: documento não é um PDF válido ou excede 25 MB.')
    try:
        leitor = PdfReader(io.BytesIO(conteudo))
        if leitor.is_encrypted or len(leitor.pages) > 200:
            raise ErroRTD('RTD_PDF_LIMITE: PDF protegido ou com mais de 200 páginas.')
        textos = []
        tamanho = 0
        inicio = time.monotonic()
        for pagina in leitor.pages:
            texto = pagina.extract_text() or ''
            tamanho += len(texto)
            if tamanho > 2_000_000 or time.monotonic() - inicio > 30:
                raise ErroRTD('RTD_PDF_LIMITE: extração excedeu o limite.')
            textos.append(texto)
        texto = '\n'.join(textos)
        ins = identificar_ins(texto)
        # Vocativo do ofício de intimação observado no documento da serventia.
        # Não usa nomes de credores, procuradores ou endereços citados no corpo.
        return {'ins': ins, 'destinatarios': identificar_destinatarios(texto)}
    except ErroRTD:
        raise
    except Exception:
        raise ErroRTD('RTD_PDF_LEITURA: não foi possível extrair o IN do PDF.') from None


def extrair_ins_pdf(conteudo):
    return extrair_documento_pdf(conteudo)['ins']


def retrato(dados):
    """Apenas acompanhamento operacional; sem documento, devedor ou URL assinada."""
    if not isinstance(dados, dict) or not isinstance(dados.get('Situacao'), str):
        raise ErroRTD('RTD_JSON: resposta sem situação do pedido.')
    campos = ('SituacaoId', 'Situacao', 'DataSituacao', 'ValorOrcamento',
              'DataDiligencia', 'DiligenciaPositiva', 'QtdExigencia', 'NumeroRegistro',
              'DataExcluido', 'MotivoCancelamento')
    retorno = {}
    for campo in campos:
        valor = dados.get(campo)
        if valor is not None and not isinstance(valor, (str, int, float, bool)):
            raise ErroRTD('RTD_JSON: campo inesperado na resposta.')
        retorno[campo] = valor[:500] if isinstance(valor, str) else valor
    for campo in ('UrlArquivoEnviado', 'UrlArquivoRegistrado', 'UrlCertidao'):
        if dados.get(campo) is not None and not isinstance(dados[campo],str):
            raise ErroRTD('RTD_JSON: referência de documento inválida.')
        retorno[campo.replace('Url', 'Tem')] = bool(dados.get(campo))
    return retorno


def hash_resumo(dados):
    return hashlib.sha256(json.dumps(retrato(dados), sort_keys=True, ensure_ascii=False).encode()).hexdigest()


class ClienteRTD:
    def __init__(self, token=None):
        self.token = token or os.getenv('AERI_RTD_TOKEN', '').strip()
        if not self.token:
            raise ErroRTD('RTD_CONFIG: chave RTD não configurada no executor.')
        self.opener = build_opener(SemRedirecionamento())

    def baixar(self, url, limite=MAX_PDF):
        validar_url(url)
        try:
            req = Request(url, headers={'Authorization': f'Bearer {self.token}',
                                        'Accept': 'application/json, application/pdf, application/octet-stream'})
            with self.opener.open(req, timeout=25) as resposta:
                partes, total, inicio = [], 0, time.monotonic()
                while True:
                    parte = resposta.read(min(65536, limite + 1 - total))
                    if not parte:
                        break
                    partes.append(parte)
                    total += len(parte)
                    if total > limite or time.monotonic() - inicio > 45:
                        raise ErroRTD('RTD_LIMITE: resposta excedeu o limite de tamanho ou tempo.')
                return b''.join(partes)
        except HTTPError as exc:
            raise ErroRTD(f'RTD_HTTP_{exc.code}: não foi possível consultar a central.') from None
        except (URLError, TimeoutError, OSError):
            raise ErroRTD('RTD_REDE: falha de conexão com a central; haverá nova tentativa.') from None

    def json(self, caminho):
        try:
            return json.loads(self.baixar(BASE + caminho, 2_000_000))
        except (ValueError, UnicodeError):
            raise ErroRTD('RTD_JSON: resposta inválida da central.') from None

    def pedido(self, protocolo):
        dados = self.json('/api/pedido/' + protocolo_valido(protocolo))
        if not isinstance(dados, dict) or str(dados.get('Protocolo')) != protocolo:
            raise ErroRTD('RTD_IDENTIDADE: resposta não corresponde ao pedido solicitado.')
        retrato(dados)
        return dados

    def atualizacoes(self, desde, pagina):
        # A API em produção rejeita datas contendo horário. Páginas começam em 1.
        dados = self.json(f'/api/pedido/{desde.isoformat()}?page={pagina}&size=20')
        if (not isinstance(dados, dict) or not isinstance(dados.get('Data'), list)
                or type(dados.get('TotalPages')) is not int
                or dados['TotalPages'] < 0 or dados.get('Number') != pagina
                or (pagina < dados['TotalPages'] and not dados['Data'])):
            raise ErroRTD('RTD_PAGINA: paginação inválida; cursor preservado.')
        diligencias = []
        for item in dados['Data']:
            if not isinstance(item, dict):
                raise ErroRTD('RTD_JSON: pedido inválido na listagem.')
            # A mesma listagem inclui certidões (17 dígitos + C), não são diligências.
            if re.fullmatch(r'\d{17}C\d*', str(item.get('Protocolo', ''))):
                continue
            protocolo_valido(item.get('Protocolo'))
            retrato(item)
            diligencias.append(item)
        dados['OutrosServicos'] = len(dados['Data']) - len(diligencias)
        dados['Data'] = diligencias
        return dados
