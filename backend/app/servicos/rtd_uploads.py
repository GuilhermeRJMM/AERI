"""Leitura validada de PDFs temporários enviados ao Blob privado da Vercel."""
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


MAX_UPLOAD_RTD = 25 * 1024 * 1024


class ErroUploadRTD(Exception):
    pass


class _SemRedirecionamento(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def baixar_pdf_assinado(url: str, pathname_esperado: str) -> bytes:
    """Baixa apenas o blob privado e o caminho exatos autorizados para o usuário."""
    try:
        partes = urlsplit(str(url or ""))
        porta = partes.port
    except ValueError:
        raise ErroUploadRTD("A autorização temporária do documento é inválida ou expirou.") from None
    host = partes.hostname or ""
    caminho = unquote(partes.path.lstrip("/"))
    if (
        partes.scheme != "https"
        or not host.endswith(".private.blob.vercel-storage.com")
        or porta not in (None, 443)
        or partes.username
        or partes.password
        or partes.fragment
        or not partes.query
        or caminho != pathname_esperado
    ):
        raise ErroUploadRTD("A autorização temporária do documento é inválida ou expirou.")

    requisicao = Request(url, headers={"Accept": "application/pdf"}, method="GET")
    cliente = build_opener(_SemRedirecionamento())
    try:
        with cliente.open(requisicao, timeout=45) as resposta:
            tipo = (resposta.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
            tamanho = resposta.headers.get("Content-Length")
            if tamanho and int(tamanho) > MAX_UPLOAD_RTD:
                raise ErroUploadRTD("O PDF ultrapassa o limite de 25 MB.")
            if tipo != "application/pdf":
                raise ErroUploadRTD("O arquivo temporário não foi reconhecido como PDF.")
            conteudo = resposta.read(MAX_UPLOAD_RTD + 1)
    except ErroUploadRTD:
        raise
    except (HTTPError, URLError, TimeoutError, OSError, ValueError):
        raise ErroUploadRTD("Não foi possível acessar o PDF temporário. Selecione-o novamente.") from None

    if len(conteudo) > MAX_UPLOAD_RTD:
        raise ErroUploadRTD("O PDF ultrapassa o limite de 25 MB.")
    if not conteudo.startswith(b"%PDF"):
        raise ErroUploadRTD("O arquivo selecionado não é um PDF válido.")
    return conteudo
