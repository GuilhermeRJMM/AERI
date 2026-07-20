import json
import os
import re
import threading
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request as UrlRequest
from urllib.request import urlopen


TAMANHO_MAXIMO_RESPOSTA = 8_000_000
TIMEOUT_PADRAO = 20
HEADERS_PADRAO = {"Accept": "application/json", "User-Agent": "AERI/1.0"}


class ErroTri7(RuntimeError):
    """Falha controlada na comunicação com a Tri7."""


class ConfiguracaoTri7Invalida(ErroTri7):
    pass


class AutenticacaoTri7Falhou(ErroTri7):
    pass


class MatriculaTri7NaoEncontrada(ErroTri7):
    pass


class MatriculaTri7SemTexto(ErroTri7):
    pass


class RespostaTri7Invalida(ErroTri7):
    pass


def normalizar_numero_matricula(valor: object) -> str:
    numero = str(valor or "").strip().replace(".", "").replace(" ", "")
    if not re.fullmatch(r"\d{1,10}", numero):
        raise ValueError("Informe uma matrícula com até 10 dígitos.")
    numero = numero.lstrip("0") or "0"
    if numero == "0":
        raise ValueError("O número da matrícula deve ser maior que zero.")
    return numero


@dataclass(frozen=True)
class ConfiguracaoTri7:
    base_url: str
    usuario: str
    senha: str
    timeout: int = TIMEOUT_PADRAO
    access_token: str = ""

    @classmethod
    def do_ambiente(cls) -> "ConfiguracaoTri7":
        base_url = os.getenv("TRI7_API_BASE_URL", "https://morrinhos-010-api.tri7-gsti.com.br").strip().rstrip("/")
        usuario = os.getenv("TRI7_API_USERNAME", "").strip()
        senha = os.getenv("TRI7_API_PASSWORD", "")
        # Tokens JWT não contêm espaços. Removê-los aqui também tolera
        # quebras de linha ou espaços introduzidos ao copiar e colar o token.
        access_token = "".join(os.getenv("TRI7_API_ACCESS_TOKEN", "").split())
        try:
            timeout = max(3, min(int(os.getenv("TRI7_API_TIMEOUT_SECONDS", str(TIMEOUT_PADRAO))), 60))
        except ValueError:
            timeout = TIMEOUT_PADRAO
        if not base_url.startswith("https://"):
            raise ConfiguracaoTri7Invalida("A URL da Tri7 deve usar HTTPS.")
        if not access_token and (not usuario or not senha):
            raise ConfiguracaoTri7Invalida("A integração com a Tri7 não está configurada.")
        return cls(
            base_url=base_url,
            usuario=usuario,
            senha=senha,
            timeout=timeout,
            access_token=access_token,
        )


class ClienteTri7:
    def __init__(self, configuracao: ConfiguracaoTri7 | None = None, abridor=urlopen):
        self.configuracao = configuracao or ConfiguracaoTri7.do_ambiente()
        self._abridor = abridor
        self._token = self.configuracao.access_token
        self._trava_token = threading.Lock()

    def _ler_json(self, requisicao: UrlRequest) -> tuple[int, object]:
        try:
            with self._abridor(requisicao, timeout=self.configuracao.timeout) as resposta:
                conteudo = resposta.read(TAMANHO_MAXIMO_RESPOSTA + 1)
                status = int(getattr(resposta, "status", 200))
        except HTTPError as erro:
            try:
                conteudo = erro.read(TAMANHO_MAXIMO_RESPOSTA + 1)
                status = erro.code
            finally:
                erro.close()
        except (URLError, TimeoutError, OSError) as erro:
            raise ErroTri7("A Tri7 está indisponível no momento.") from erro
        if len(conteudo) > TAMANHO_MAXIMO_RESPOSTA:
            raise RespostaTri7Invalida("A resposta da Tri7 excedeu o limite permitido.")
        try:
            return status, json.loads(conteudo.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as erro:
            raise RespostaTri7Invalida("A Tri7 retornou uma resposta inválida.") from erro

    def _autenticar(self) -> str:
        if not self.configuracao.usuario or not self.configuracao.senha:
            raise AutenticacaoTri7Falhou("O token da Tri7 expirou e não há credenciais para renová-lo.")
        corpo = json.dumps({"username": self.configuracao.usuario, "password": self.configuracao.senha}).encode("utf-8")
        requisicao = UrlRequest(
            f"{self.configuracao.base_url}/api/v1/users/login",
            data=corpo,
            method="POST",
            headers={**HEADERS_PADRAO, "Content-Type": "application/json"},
        )
        status, dados = self._ler_json(requisicao)
        token = dados.get("access_token") if isinstance(dados, dict) else None
        if status < 200 or status >= 300 or not isinstance(token, str) or not token:
            raise AutenticacaoTri7Falhou("Não foi possível autenticar na Tri7.")
        self._token = token
        return token

    def _obter_token(self, forcar: bool = False) -> str:
        with self._trava_token:
            if not forcar and self._token:
                return self._token
            return self._autenticar()

    def buscar_texto_matricula(self, numero_matricula: object) -> dict:
        numero = normalizar_numero_matricula(numero_matricula)
        caminho = "/api/v1/imoveis/texto-matricula?" + urlencode({"numero_matricula": numero})
        for tentativa in range(2):
            token = self._obter_token(forcar=tentativa > 0)
            requisicao = UrlRequest(
                f"{self.configuracao.base_url}{caminho}",
                method="GET",
                headers={**HEADERS_PADRAO, "Authorization": f"Bearer {token}"},
            )
            status, dados = self._ler_json(requisicao)
            if status in {401, 403} and tentativa == 0:
                continue
            if status == 404:
                raise MatriculaTri7NaoEncontrada(f"Matrícula {numero} não encontrada na Tri7.")
            if status < 200 or status >= 300:
                raise ErroTri7("A Tri7 não conseguiu consultar a matrícula.")
            if not isinstance(dados, dict):
                raise RespostaTri7Invalida("A Tri7 retornou uma resposta inválida para a matrícula.")
            if not isinstance(dados.get("texto"), str) or not dados["texto"].strip():
                raise MatriculaTri7SemTexto(f"A matrícula {numero} não possui texto disponível na Tri7.")
            numero_retornado = normalizar_numero_matricula(dados.get("numero_matricula", numero))
            if numero_retornado != numero:
                raise RespostaTri7Invalida("A Tri7 retornou uma matrícula diferente da solicitada.")
            return {"numero_matricula": numero, "texto": dados["texto"]}
        raise AutenticacaoTri7Falhou("A autenticação com a Tri7 expirou.")


_cliente_compartilhado: ClienteTri7 | None = None
_trava_cliente = threading.Lock()


def cliente_tri7() -> ClienteTri7:
    global _cliente_compartilhado
    with _trava_cliente:
        if _cliente_compartilhado is None:
            _cliente_compartilhado = ClienteTri7()
        return _cliente_compartilhado
