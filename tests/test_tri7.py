import io
import json
import os
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from backend.app.servicos.tri7 import (
    ClienteTri7,
    ConfiguracaoTri7,
    ConfiguracaoTri7Invalida,
    MatriculaTri7NaoEncontrada,
    MatriculaTri7SemTexto,
    RespostaTri7Invalida,
    normalizar_numero_matricula,
)


class RespostaFalsa:
    def __init__(self, dados, status=200):
        self.status = status
        self._conteudo = json.dumps(dados).encode("utf-8")

    def read(self, limite=-1):
        return self._conteudo if limite < 0 else self._conteudo[:limite]

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class TesteClienteTri7(unittest.TestCase):
    def configuracao(self):
        return ConfiguracaoTri7("https://tri7.example", "usuario-teste", "senha-teste", timeout=5)

    def test_normaliza_numero_com_pontos_e_zeros(self):
        self.assertEqual(normalizar_numero_matricula(" 01.560 "), "1560")

    def test_recusa_matricula_invalida(self):
        for valor in ("", "12-A", "1/9-C", "12345678901", "0"):
            with self.subTest(valor=valor), self.assertRaises(ValueError):
                normalizar_numero_matricula(valor)

    def test_credenciais_sao_obrigatorias_no_ambiente(self):
        with patch.dict(
            os.environ,
            {"TRI7_API_USERNAME": "", "TRI7_API_PASSWORD": "", "TRI7_API_ACCESS_TOKEN": ""},
            clear=False,
        ):
            with self.assertRaises(ConfiguracaoTri7Invalida):
                ConfiguracaoTri7.do_ambiente()

    def test_normaliza_espacos_introduzidos_ao_copiar_token(self):
        with patch.dict(
            os.environ,
            {
                "TRI7_API_BASE_URL": "https://tri7.example",
                "TRI7_API_USERNAME": "",
                "TRI7_API_PASSWORD": "",
                "TRI7_API_ACCESS_TOKEN": "parte-1. parte-2.\nparte-3",
            },
            clear=False,
        ):
            configuracao = ConfiguracaoTri7.do_ambiente()

        self.assertEqual(configuracao.access_token, "parte-1.parte-2.parte-3")

    def test_token_inicial_dispensa_novo_login(self):
        requisicoes = []

        def abrir(requisicao, timeout):
            requisicoes.append(requisicao)
            self.assertFalse(requisicao.full_url.endswith("/api/v1/users/login"))
            self.assertEqual(requisicao.headers["Authorization"], "Bearer token-inicial")
            return RespostaFalsa({"numero_matricula": 1, "texto": "MATRÍCULA 1. R.01 - VENDA."})

        configuracao = ConfiguracaoTri7(
            "https://tri7.example",
            "",
            "",
            timeout=5,
            access_token="token-inicial",
        )
        resultado = ClienteTri7(configuracao, abridor=abrir).buscar_texto_matricula(1)

        self.assertEqual(resultado["numero_matricula"], "1")
        self.assertEqual(len(requisicoes), 1)

    def test_autentica_no_backend_e_busca_texto(self):
        requisicoes = []

        def abrir(requisicao, timeout):
            requisicoes.append((requisicao, timeout))
            if requisicao.full_url.endswith("/api/v1/users/login"):
                return RespostaFalsa({"access_token": "token-seguro"})
            self.assertEqual(requisicao.headers["Authorization"], "Bearer token-seguro")
            self.assertIn("numero_matricula=10148", requisicao.full_url)
            return RespostaFalsa({"numero_matricula": 10148, "texto": "MATRÍCULA 10.148. R.01 - COMPRA E VENDA."})

        cliente = ClienteTri7(self.configuracao(), abridor=abrir)
        primeira = cliente.buscar_texto_matricula("10.148")
        segunda = cliente.buscar_texto_matricula(10148)

        self.assertEqual(primeira, segunda)
        self.assertEqual(primeira["numero_matricula"], "10148")
        self.assertEqual(sum(req.full_url.endswith("/api/v1/users/login") for req, _ in requisicoes), 1)

    def test_renova_token_uma_vez_apos_401(self):
        logins = 0
        consultas = 0

        def abrir(requisicao, timeout):
            nonlocal logins, consultas
            if requisicao.full_url.endswith("/api/v1/users/login"):
                logins += 1
                return RespostaFalsa({"access_token": f"token-{logins}"})
            consultas += 1
            if consultas == 1:
                raise HTTPError(requisicao.full_url, 401, "Unauthorized", {}, io.BytesIO(b'{"detail":"expired"}'))
            self.assertEqual(requisicao.headers["Authorization"], "Bearer token-2")
            return RespostaFalsa({"numero_matricula": 8148, "texto": "MATRÍCULA 8.148. R.01 - VENDA."})

        resultado = ClienteTri7(self.configuracao(), abridor=abrir).buscar_texto_matricula(8148)
        self.assertEqual(resultado["numero_matricula"], "8148")
        self.assertEqual((logins, consultas), (2, 2))

    def test_converte_404_em_erro_de_dominio(self):
        def abrir(requisicao, timeout):
            if requisicao.full_url.endswith("/api/v1/users/login"):
                return RespostaFalsa({"access_token": "token"})
            raise HTTPError(requisicao.full_url, 404, "Not Found", {}, io.BytesIO(b'{"detail":"not found"}'))

        with self.assertRaises(MatriculaTri7NaoEncontrada):
            ClienteTri7(self.configuracao(), abridor=abrir).buscar_texto_matricula(999999)

    def test_recusa_numero_diferente_na_resposta(self):
        def abrir(requisicao, timeout):
            if requisicao.full_url.endswith("/api/v1/users/login"):
                return RespostaFalsa({"access_token": "token"})
            return RespostaFalsa({"numero_matricula": 10149, "texto": "texto"})

        with self.assertRaises(RespostaTri7Invalida):
            ClienteTri7(self.configuracao(), abridor=abrir).buscar_texto_matricula(10148)

    def test_diferencia_matricula_existente_sem_texto(self):
        def abrir(requisicao, timeout):
            if requisicao.full_url.endswith("/api/v1/users/login"):
                return RespostaFalsa({"access_token": "token"})
            return RespostaFalsa({"numero_matricula": 25, "texto": None})

        with self.assertRaises(MatriculaTri7SemTexto):
            ClienteTri7(self.configuracao(), abridor=abrir).buscar_texto_matricula(25)


if __name__ == "__main__":
    unittest.main()
