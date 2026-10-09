"""Cliente da API ONRTDPJ para consulta e cadastro manual de notificações."""
import hashlib
import io
import json
import os
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

BASES = {
    'producao': 'https://apicentral.rtdbrasil.org.br',
    'homologacao': 'https://apicentral.fpsti.com.br',
}
BASE = BASES['producao']
MAX_PDF = 25 * 1024 * 1024
MAX_ARQUIVO_ENVIO = 4_300_000


class ErroRTD(Exception):
    """Mensagens controladas: não expõem JWT, URLs privadas ou resposta bruta."""

    def __init__(self, mensagem, resultado_incerto=False):
        super().__init__(mensagem)
        self.resultado_incerto = resultado_incerto


class SemRedirecionamento(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def validar_url(url, host='apicentral.rtdbrasil.org.br'):
    partes = urlsplit(str(url or ''))
    if (partes.scheme != 'https' or partes.hostname != host
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
        from pypdf import PdfReader

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
    except ImportError:
        raise ErroRTD('RTD_PDF_BIBLIOTECA: instale as dependências do AERI para ler PDFs.') from None
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
    def __init__(self, token=None, ambiente='producao'):
        ambiente = str(ambiente or 'producao').strip().lower()
        if ambiente not in BASES:
            raise ErroRTD('RTD_CONFIG: ambiente inválido; use produção ou homologação.')
        self.ambiente = ambiente
        self.base = BASES[ambiente]
        nome_token = 'AERI_RTD_TOKEN_HOMOLOGACAO' if ambiente == 'homologacao' else 'AERI_RTD_TOKEN'
        self.token = token or os.getenv(nome_token, '').strip()
        if not self.token:
            raise ErroRTD(f'RTD_CONFIG: chave RTD não configurada para {ambiente}.')
        self.opener = build_opener(SemRedirecionamento())

    def baixar(self, url, limite=MAX_PDF):
        validar_url(url, urlsplit(self.base).hostname)
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
            return json.loads(self.baixar(self.base + caminho, 2_000_000))
        except (ValueError, UnicodeError):
            raise ErroRTD('RTD_JSON: resposta inválida da central.') from None

    def cartorios(self, uf, cidade):
        """Busca os destinos da Central sem expor a credencial ao navegador."""
        dados = self.json('/api/cartorio?' + urlencode({'uf': uf, 'cidade': cidade}))
        if not isinstance(dados, list):
            raise ErroRTD('RTD_CARTORIOS: resposta inválida da central.')
        resultado = []
        for item in dados:
            if not isinstance(item, dict):
                raise ErroRTD('RTD_CARTORIOS: resposta inválida da central.')
            identificador = item.get('Id', item.get('id'))
            nome = item.get('Nome', item.get('nome'))
            if type(identificador) is not int or not isinstance(nome, str):
                raise ErroRTD('RTD_CARTORIOS: resposta inválida da central.')
            resultado.append({'id': identificador, 'nome': nome[:160]})
        return resultado

    def _post(self, caminho, corpo, tipo_conteudo, limite=2_000_000, resposta_incerta=False):
        try:
            req = Request(self.base + caminho, data=corpo, method='POST', headers={
                'Authorization': f'Bearer {self.token}',
                'Accept': 'application/json, text/json',
                'Content-Type': tipo_conteudo,
            })
            with self.opener.open(req, timeout=35) as resposta:
                partes, total, inicio = [], 0, time.monotonic()
                while True:
                    parte = resposta.read(min(65536, limite + 1 - total))
                    if not parte:
                        break
                    partes.append(parte)
                    total += len(parte)
                    if total > limite or time.monotonic() - inicio > 45:
                        raise ErroRTD('RTD_LIMITE: resposta excedeu o limite permitido.', resultado_incerto)
                return b''.join(partes)
        except HTTPError as exc:
            incerto = resposta_incerta and (300 <= exc.code < 400 or exc.code in (408, 409) or exc.code >= 500)
            raise ErroRTD(f'RTD_HTTP_{exc.code}: a Central não confirmou a operação.', incerto) from None
        except (URLError, TimeoutError, OSError):
            raise ErroRTD('RTD_REDE: a Central não confirmou a operação.', resposta_incerta) from None

    def enviar_arquivo(self, nome, conteudo):
        """Envia PDF pelo campo `file` documentado pela Central RTDPJ."""
        nome_seguro = re.sub(r'[^A-Za-z0-9._-]', '_', str(nome or 'documento.pdf'))[:120]
        if not nome_seguro.lower().endswith('.pdf'):
            nome_seguro = 'documento.pdf'
        limite = MAX_ARQUIVO_ENVIO
        if not conteudo or len(conteudo) > limite or not conteudo.startswith(b'%PDF'):
            raise ErroRTD('RTD_PDF: selecione um PDF válido de até 4 MB.')
        boundary = '----AERIForm' + os.urandom(16).hex()
        corpo = (
            f'--{boundary}\r\n'
            f'Content-Disposition: form-data; name="file"; filename="{nome_seguro}"\r\n'
            'Content-Type: application/pdf\r\n\r\n'
        ).encode('ascii') + conteudo + f'\r\n--{boundary}--\r\n'.encode('ascii')
        bruto = self._post('/api/arquivo', corpo, f'multipart/form-data; boundary={boundary}')
        try:
            resposta = json.loads(bruto)
            identificador = resposta.get('id', resposta.get('Id')) if isinstance(resposta, dict) else None
            if type(identificador) is not int or identificador <= 0:
                raise ValueError
            return identificador
        except (ValueError, UnicodeError):
            raise ErroRTD('RTD_ARQUIVO: a Central não confirmou o recebimento do PDF.') from None

    def criar_notificacao(self, pedido):
        """Cadastra a notificação. Falhas de rede/servidor ficam sinalizadas como incertas."""
        corpo = json.dumps(pedido, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        bruto = self._post('/api/notificacao', corpo, 'application/json; charset=utf-8', resposta_incerta=True)
        try:
            resposta = json.loads(bruto)
            protocolo = resposta.get('Protocolo') if isinstance(resposta, dict) else None
            cartorio_id = resposta.get('CartorioId') if isinstance(resposta, dict) else None
            if not isinstance(protocolo, str) or not protocolo.strip() or type(cartorio_id) is not int:
                raise ValueError
            return {'protocolo': protocolo.strip(), 'cartorio_id': cartorio_id}
        except (ValueError, UnicodeError):
            # A Central pode ter criado o pedido mesmo se a resposta veio incompleta.
            raise ErroRTD('RTD_NOTIFICACAO_INCERTA: a Central respondeu sem confirmar o protocolo.', True) from None

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
