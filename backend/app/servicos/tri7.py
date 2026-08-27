import base64
import binascii
import json
import logging
import os
import re
import threading
import time
from dataclasses import dataclass
from datetime import date
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request as UrlRequest
from urllib.request import urlopen


TAMANHO_MAXIMO_RESPOSTA = 8_000_000
TIMEOUT_PADRAO = 20
HEADERS_PADRAO = {"Accept": "application/json", "User-Agent": "AERI/1.0"}
REQUISICOES_POR_SEGUNDO = 3.0
TENTATIVAS_TRANSITORIAS_PADRAO = 3
MARGEM_RENOVACAO_TOKEN_SEGUNDOS = 30
logger = logging.getLogger("aeri.tri7")


class LimitadorTaxaTri7:
    """Limite compartilhado por todos os módulos desta instância.

    Um limitador por tela permitia que Buscas, INCRA e Livro de Protocolos
    enviassem três requisições por segundo cada um ao mesmo tempo. O objeto
    único mantém o teto combinado em três requisições por segundo.
    """

    def __init__(self, requisicoes_por_segundo: float = REQUISICOES_POR_SEGUNDO):
        self._intervalo = 1.0 / requisicoes_por_segundo
        self._proximo = 0.0
        self._trava = threading.Lock()

    def aguardar(self) -> None:
        with self._trava:
            agora = time.monotonic()
            reservado = max(agora, self._proximo)
            self._proximo = reservado + self._intervalo
        if reservado > agora:
            time.sleep(reservado - agora)


_limitador_compartilhado = LimitadorTaxaTri7()


def limitador_tri7() -> LimitadorTaxaTri7:
    return _limitador_compartilhado


class ErroTri7(RuntimeError):
    """Falha controlada na comunicação com a Tri7."""

    def __init__(self, mensagem: str, *, status: int | None = None):
        super().__init__(mensagem)
        self.status = status


class ConfiguracaoTri7Invalida(ErroTri7):
    pass


class AutenticacaoTri7Falhou(ErroTri7):
    pass


class MatriculaTri7NaoEncontrada(ErroTri7):
    pass


class MatriculaTri7SemTexto(ErroTri7):
    pass


class RegistroAuxiliarTri7NaoEncontrado(ErroTri7):
    pass


class RegistroAuxiliarTri7SemTexto(ErroTri7):
    pass


class ProtocoloTri7NaoEncontrado(ErroTri7):
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
    tentativas_transitorias: int = TENTATIVAS_TRANSITORIAS_PADRAO

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
        try:
            tentativas = max(1, min(int(os.getenv(
                "TRI7_API_TRANSIENT_ATTEMPTS", str(TENTATIVAS_TRANSITORIAS_PADRAO)
            )), 5))
        except ValueError:
            tentativas = TENTATIVAS_TRANSITORIAS_PADRAO
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
            tentativas_transitorias=tentativas,
        )


class ClienteTri7:
    def __init__(self, configuracao: ConfiguracaoTri7 | None = None, abridor=urlopen):
        self.configuracao = configuracao or ConfiguracaoTri7.do_ambiente()
        self._abridor = abridor
        self._token = self.configuracao.access_token
        self._trava_token = threading.Lock()

    @staticmethod
    def _token_expira_em_breve(token: str) -> bool:
        """Lê apenas o ``exp`` do JWT para antecipar renovação.

        A assinatura continua sendo validada exclusivamente pela Tri7. O
        conteúdo local nunca concede acesso; serve somente para evitar uma
        consulta que já nasceria com token vencido.
        """
        try:
            partes = token.split(".")
            if len(partes) != 3:
                return False
            corpo = partes[1] + "=" * (-len(partes[1]) % 4)
            dados = json.loads(base64.urlsafe_b64decode(corpo).decode("utf-8"))
            expiracao = float(dados["exp"])
            return expiracao <= time.time() + MARGEM_RENOVACAO_TOKEN_SEGUNDOS
        except (ValueError, TypeError, KeyError, UnicodeDecodeError, json.JSONDecodeError, binascii.Error):
            return False

    @staticmethod
    def _rota_segura(requisicao: UrlRequest) -> str:
        """Retorna somente o caminho, sem consulta, credencial ou conteúdo."""
        return urlsplit(requisicao.full_url).path

    def _ler_json_uma_vez(self, requisicao: UrlRequest) -> tuple[int, object]:
        inicio = time.perf_counter()
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
            logger.warning(
                "tri7_rede_falhou metodo=%s rota=%s tipo=%s duracao_ms=%s",
                requisicao.method, self._rota_segura(requisicao),
                type(erro).__name__, round((time.perf_counter() - inicio) * 1000, 1),
            )
            raise ErroTri7("A Tri7 está indisponível no momento.") from erro
        if len(conteudo) > TAMANHO_MAXIMO_RESPOSTA:
            raise RespostaTri7Invalida("A resposta da Tri7 excedeu o limite permitido.")
        try:
            dados = json.loads(conteudo.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as erro:
            # Proxies e indisponibilidades da Tri7 podem devolver HTML/texto
            # em respostas de erro. O status ainda precisa chegar à política
            # central para permitir nova tentativa ou renovação do token.
            if status < 200 or status >= 300:
                dados = {}
            else:
                raise RespostaTri7Invalida("A Tri7 retornou uma resposta inválida.") from erro
        logger.info(
            "tri7_resposta metodo=%s rota=%s status=%s duracao_ms=%s",
            requisicao.method, self._rota_segura(requisicao), status,
            round((time.perf_counter() - inicio) * 1000, 1),
        )
        return status, dados

    def _ler_json(self, requisicao: UrlRequest) -> tuple[int, object]:
        """Repete somente falhas transitórias, com espera curta e limitada."""
        ultimo_erro = None
        total = self.configuracao.tentativas_transitorias
        for tentativa in range(total):
            limitador_tri7().aguardar()
            try:
                status, dados = self._ler_json_uma_vez(requisicao)
            except ErroTri7 as erro:
                if isinstance(erro, RespostaTri7Invalida):
                    raise
                ultimo_erro = erro
                if tentativa == total - 1:
                    raise
                time.sleep(0.5 * (2 ** tentativa))
                continue
            if status not in {429, 500, 502, 503, 504} or tentativa == total - 1:
                return status, dados
            time.sleep(0.5 * (2 ** tentativa))
        raise ultimo_erro or ErroTri7("A Tri7 está indisponível no momento.")

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
            if not forcar and self._token and not (
                self.configuracao.usuario
                and self.configuracao.senha
                and self._token_expira_em_breve(self._token)
            ):
                return self._token
            return self._autenticar()

    def _renovar_token_rejeitado(self, token_rejeitado: str) -> str:
        """Renova uma única vez mesmo quando várias threads recebem 401."""
        with self._trava_token:
            if self._token and self._token != token_rejeitado:
                return self._token
            self._token = ""
            return self._autenticar()

    def _buscar_json_autenticado(self, caminho: str, parametros: dict[str, str]) -> tuple[int, object]:
        url = f"{self.configuracao.base_url}{caminho}?{urlencode(parametros)}"
        token = self._obter_token()
        for tentativa_autenticacao in range(2):
            requisicao = UrlRequest(
                url,
                method="GET",
                headers={**HEADERS_PADRAO, "Authorization": f"Bearer {token}"},
            )
            status, dados = self._ler_json(requisicao)
            if status not in {401, 403}:
                return status, dados
            if tentativa_autenticacao == 0:
                token = self._renovar_token_rejeitado(token)
        raise AutenticacaoTri7Falhou("A autenticação com a Tri7 expirou.", status=status)

    def buscar_texto_matricula(self, numero_matricula: object) -> dict:
        numero = normalizar_numero_matricula(numero_matricula)
        status, dados = self._buscar_json_autenticado(
            "/api/v1/imoveis/texto-matricula", {"numero_matricula": numero}
        )
        if status == 404:
            raise MatriculaTri7NaoEncontrada(f"Matrícula {numero} não encontrada na Tri7.", status=status)
        if status < 200 or status >= 300:
            raise ErroTri7("A Tri7 não conseguiu consultar a matrícula.", status=status)
        if not isinstance(dados, dict):
            raise RespostaTri7Invalida("A Tri7 retornou uma resposta inválida para a matrícula.")
        if not isinstance(dados.get("texto"), str) or not dados["texto"].strip():
            raise MatriculaTri7SemTexto(f"A matrícula {numero} não possui texto disponível na Tri7.")
        numero_retornado = normalizar_numero_matricula(dados.get("numero_matricula", numero))
        if numero_retornado != numero:
            raise RespostaTri7Invalida("A Tri7 retornou uma matrícula diferente da solicitada.")
        return {"numero_matricula": numero, "texto": dados["texto"]}

    def buscar_atos_matricula(self, numero_matricula: object) -> dict:
        """Consulta o índice objetivo de atos da matrícula na Tri7.

        Esse endpoint é separado do texto corrido e pode refletir um ato já
        registrado enquanto ``texto-matricula`` ainda está sendo atualizado.
        O AERI usa o retorno apenas como confirmação de existência/status; a
        conferência do conteúdo continua dependendo do texto registral.
        """
        numero = normalizar_numero_matricula(numero_matricula)
        status, dados = self._buscar_json_autenticado(
            "/api/v1/imoveis/matricula-atos", {"numero_matricula": numero}
        )
        if status == 404:
            raise MatriculaTri7NaoEncontrada(
                f"Matrícula {numero} não encontrada na Tri7.", status=status
            )
        if status < 200 or status >= 300:
            raise ErroTri7("A Tri7 não conseguiu consultar os atos da matrícula.", status=status)
        if not isinstance(dados, dict) or not isinstance(dados.get("atos"), list):
            raise RespostaTri7Invalida("A Tri7 retornou uma resposta inválida para os atos da matrícula.")
        numero_retornado = normalizar_numero_matricula(dados.get("numero_matricula", numero))
        if numero_retornado != numero:
            raise RespostaTri7Invalida("A Tri7 retornou atos de uma matrícula diferente da solicitada.")
        return {"numero_matricula": numero, "atos": dados["atos"]}

    def buscar_texto_registro_auxiliar(self, numero_registro: object) -> dict:
        numero = normalizar_numero_matricula(numero_registro)
        status, dados = self._buscar_json_autenticado(
            "/api/v1/imoveis/texto-reg-auxiliar", {"numero_matricula": numero}
        )
        if status == 404:
            raise RegistroAuxiliarTri7NaoEncontrado(
                f"Registro Auxiliar {numero} não encontrado na Tri7.", status=status
            )
        if status < 200 or status >= 300:
            raise ErroTri7("A Tri7 não conseguiu consultar o Registro Auxiliar.", status=status)
        if not isinstance(dados, dict):
            raise RespostaTri7Invalida("A Tri7 retornou uma resposta inválida para o Registro Auxiliar.")
        if not isinstance(dados.get("texto"), str) or not dados["texto"].strip():
            raise RegistroAuxiliarTri7SemTexto(
                f"O Registro Auxiliar {numero} não possui texto disponível na Tri7."
            )
        numero_retornado = normalizar_numero_matricula(dados.get("numero_matricula", numero))
        if numero_retornado != numero:
            raise RespostaTri7Invalida("A Tri7 retornou um Registro Auxiliar diferente do solicitado.")
        return {"numero_registro": numero, "texto": dados["texto"]}

    def buscar_protocolo_completo(self, numero_protocolo: object) -> dict:
        numero = normalizar_numero_matricula(numero_protocolo)
        status, dados = self._buscar_json_autenticado(
            "/api/v1/imoveis/protocolo-completo", {"protocolo": numero}
        )
        if status == 404:
            raise ProtocoloTri7NaoEncontrado(f"Protocolo {numero} não encontrado na Tri7.", status=status)
        if status < 200 or status >= 300:
            raise ErroTri7("A Tri7 não conseguiu consultar o protocolo.", status=status)
        if not isinstance(dados, dict) or not isinstance(dados.get("protocolo"), dict):
            raise RespostaTri7Invalida("A Tri7 retornou uma resposta inválida para o protocolo.")
        protocolo = dados["protocolo"]
        try:
            numero_retornado = normalizar_numero_matricula(protocolo.get("protocolo_numero", numero))
        except ValueError as erro:
            raise RespostaTri7Invalida("A Tri7 retornou um número de protocolo inválido.") from erro
        if numero_retornado != numero:
            raise RespostaTri7Invalida("A Tri7 retornou um protocolo diferente do solicitado.")
        return dados

    def buscar_livro_protocolos(self, data_inicio: date, data_fim: date) -> dict:
        if not isinstance(data_inicio, date) or not isinstance(data_fim, date):
            raise ValueError("Informe datas válidas para consultar o Livro de Protocolos.")
        intervalo = (data_fim - data_inicio).days
        if intervalo < 0:
            raise ValueError("A data inicial do Livro não pode ser posterior à final.")
        if intervalo > 30:
            raise ValueError("Cada consulta do Livro pode abranger no máximo 31 dias.")
        status, dados = self._buscar_json_autenticado(
            "/api/v1/imoveis/livro-protocolo",
            {"data_inicio": data_inicio.isoformat(), "data_fim": data_fim.isoformat()},
        )
        if status < 200 or status >= 300:
            raise ErroTri7("A Tri7 não conseguiu consultar o Livro de Protocolos.", status=status)
        if not isinstance(dados, dict) or not isinstance(dados.get("protocolos"), list):
            raise RespostaTri7Invalida("A Tri7 retornou uma resposta inválida para o Livro de Protocolos.")
        return dados


_cliente_compartilhado: ClienteTri7 | None = None
_trava_cliente = threading.Lock()


def cliente_tri7() -> ClienteTri7:
    global _cliente_compartilhado
    with _trava_cliente:
        if _cliente_compartilhado is None:
            _cliente_compartilhado = ClienteTri7()
        return _cliente_compartilhado
