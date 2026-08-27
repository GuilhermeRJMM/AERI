import base64
import io
import json
import os
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from unittest.mock import patch
from urllib.error import HTTPError

from backend.app.servicos.tri7 import (
    ClienteTri7,
    ConfiguracaoTri7,
    ConfiguracaoTri7Invalida,
    MatriculaTri7NaoEncontrada,
    MatriculaTri7SemTexto,
    ProtocoloTri7NaoEncontrado,
    RegistroAuxiliarTri7NaoEncontrado,
    RespostaTri7Invalida,
    normalizar_numero_matricula,
)
from backend.app.servicos import tri7 as modulo_tri7


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


class RespostaBruta(RespostaFalsa):
    def __init__(self, conteudo: bytes, status=200):
        self.status = status
        self._conteudo = conteudo


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

    def test_limita_configuracao_de_tentativas_transitorias(self):
        with patch.dict(
            os.environ,
            {
                "TRI7_API_BASE_URL": "https://tri7.example",
                "TRI7_API_USERNAME": "usuario",
                "TRI7_API_PASSWORD": "senha",
                "TRI7_API_ACCESS_TOKEN": "",
                "TRI7_API_TRANSIENT_ATTEMPTS": "99",
            },
            clear=False,
        ):
            configuracao = ConfiguracaoTri7.do_ambiente()

        self.assertEqual(configuracao.tentativas_transitorias, 5)

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

    def test_log_nao_expoe_token_nem_parametro_consultado(self):
        def abrir(_requisicao, timeout):
            return RespostaFalsa({"numero_matricula": 39767, "texto": "MATRÍCULA 39.767."})

        configuracao = ConfiguracaoTri7(
            "https://tri7.example", "", "", timeout=5,
            access_token="token-muito-sensivel",
        )
        with patch.object(modulo_tri7.limitador_tri7(), "aguardar"), self.assertLogs(
            "aeri.tri7", level="INFO"
        ) as logs:
            ClienteTri7(configuracao, abridor=abrir).buscar_texto_matricula(39767)

        texto_logs = " ".join(logs.output)
        self.assertNotIn("token-muito-sensivel", texto_logs)
        self.assertNotIn("numero_matricula=39767", texto_logs)
        self.assertIn("/api/v1/imoveis/texto-matricula", texto_logs)

    def test_repete_falha_transitoria_e_para_apos_sucesso(self):
        chamadas = 0

        def abrir(_requisicao, timeout):
            nonlocal chamadas
            chamadas += 1
            if chamadas < 3:
                return RespostaFalsa({"detail": "temporário"}, status=503)
            return RespostaFalsa({"numero_matricula": 1, "texto": "MATRÍCULA 1."})

        configuracao = ConfiguracaoTri7(
            "https://tri7.example", "", "", timeout=5, access_token="token"
        )
        with patch.object(modulo_tri7.limitador_tri7(), "aguardar"), patch.object(
            modulo_tri7.time, "sleep"
        ):
            resultado = ClienteTri7(configuracao, abridor=abrir).buscar_texto_matricula(1)

        self.assertEqual(resultado["numero_matricula"], "1")
        self.assertEqual(chamadas, 3)

    def test_repete_erro_503_mesmo_quando_proxy_devolve_html(self):
        chamadas = 0

        def abrir(_requisicao, timeout):
            nonlocal chamadas
            chamadas += 1
            if chamadas == 1:
                return RespostaBruta(b"Internal Server Error", status=503)
            return RespostaFalsa({"numero_matricula": 1, "texto": "MATRÍCULA 1."})

        configuracao = ConfiguracaoTri7(
            "https://tri7.example", "", "", timeout=5, access_token="token"
        )
        with patch.object(modulo_tri7.limitador_tri7(), "aguardar"), patch.object(
            modulo_tri7.time, "sleep"
        ):
            resultado = ClienteTri7(configuracao, abridor=abrir).buscar_texto_matricula(1)

        self.assertEqual(resultado["numero_matricula"], "1")
        self.assertEqual(chamadas, 2)

    def test_numero_de_tentativas_transitorias_e_configuravel(self):
        chamadas = 0

        def abrir(_requisicao, timeout):
            nonlocal chamadas
            chamadas += 1
            return RespostaFalsa({"detail": "temporário"}, status=503)

        configuracao = ConfiguracaoTri7(
            "https://tri7.example", "", "", timeout=5, access_token="token",
            tentativas_transitorias=1,
        )
        with patch.object(modulo_tri7.limitador_tri7(), "aguardar"):
            with self.assertRaises(modulo_tri7.ErroTri7):
                ClienteTri7(configuracao, abridor=abrir).buscar_texto_matricula(1)

        self.assertEqual(chamadas, 1)

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

    def test_busca_indice_de_atos_da_matricula(self):
        resposta = {
            "numero_matricula": 15914,
            "atos": [
                {"codigo": 338045, "status": "Registrado", "ato": "R.7"},
                {"codigo": 338046, "status": "Registrado", "ato": "Av.6"},
            ],
        }

        def abrir(requisicao, timeout):
            if requisicao.full_url.endswith("/api/v1/users/login"):
                return RespostaFalsa({"access_token": "token"})
            self.assertIn("/api/v1/imoveis/matricula-atos", requisicao.full_url)
            self.assertIn("numero_matricula=15914", requisicao.full_url)
            return RespostaFalsa(resposta)

        resultado = ClienteTri7(self.configuracao(), abridor=abrir).buscar_atos_matricula("15.914")

        self.assertEqual(resultado["numero_matricula"], "15914")
        self.assertEqual(resultado["atos"], resposta["atos"])

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

    def test_renova_token_uma_vez_para_consultas_concorrentes(self):
        logins = 0
        trava = threading.Lock()
        consultas_com_token_antigo = threading.Barrier(2)

        def abrir(requisicao, timeout):
            nonlocal logins
            if requisicao.full_url.endswith("/api/v1/users/login"):
                with trava:
                    logins += 1
                return RespostaFalsa({"access_token": "token-novo"})
            if requisicao.headers["Authorization"] == "Bearer token-antigo":
                consultas_com_token_antigo.wait(timeout=2)
                raise HTTPError(
                    requisicao.full_url, 401, "Unauthorized", {},
                    io.BytesIO(b'{"detail":"expired"}'),
                )
            self.assertEqual(requisicao.headers["Authorization"], "Bearer token-novo")
            return RespostaFalsa({"numero_matricula": 1, "texto": "MATRÍCULA 1."})

        configuracao = ConfiguracaoTri7(
            "https://tri7.example", "usuario", "senha", timeout=5,
            access_token="token-antigo",
        )
        cliente = ClienteTri7(configuracao, abridor=abrir)
        with patch.object(modulo_tri7.limitador_tri7(), "aguardar"):
            with ThreadPoolExecutor(max_workers=2) as executor:
                resultados = list(executor.map(cliente.buscar_texto_matricula, (1, 1)))

        self.assertEqual([item["numero_matricula"] for item in resultados], ["1", "1"])
        self.assertEqual(logins, 1)

    def test_renova_antes_da_consulta_quando_jwt_esta_expirando(self):
        def parte_jwt(dados):
            bruto = json.dumps(dados, separators=(",", ":")).encode("utf-8")
            return base64.urlsafe_b64encode(bruto).decode("ascii").rstrip("=")

        token_expirado = f"{parte_jwt({'alg': 'none'})}.{parte_jwt({'exp': time.time() - 1})}.x"
        logins = 0

        def abrir(requisicao, timeout):
            nonlocal logins
            if requisicao.full_url.endswith("/api/v1/users/login"):
                logins += 1
                return RespostaFalsa({"access_token": "token-renovado"})
            self.assertEqual(requisicao.headers["Authorization"], "Bearer token-renovado")
            return RespostaFalsa({"numero_matricula": 1, "texto": "MATRÍCULA 1."})

        configuracao = ConfiguracaoTri7(
            "https://tri7.example", "usuario", "senha", timeout=5,
            access_token=token_expirado,
        )
        with patch.object(modulo_tri7.limitador_tri7(), "aguardar"):
            resultado = ClienteTri7(configuracao, abridor=abrir).buscar_texto_matricula(1)

        self.assertEqual(resultado["numero_matricula"], "1")
        self.assertEqual(logins, 1)

    def test_converte_404_em_erro_de_dominio(self):
        def abrir(requisicao, timeout):
            if requisicao.full_url.endswith("/api/v1/users/login"):
                return RespostaFalsa({"access_token": "token"})
            raise HTTPError(requisicao.full_url, 404, "Not Found", {}, io.BytesIO(b'{"detail":"not found"}'))

        with self.assertRaises(MatriculaTri7NaoEncontrada) as contexto:
            ClienteTri7(self.configuracao(), abridor=abrir).buscar_texto_matricula(999999)
        self.assertEqual(contexto.exception.status, 404)

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

    def test_busca_texto_do_registro_auxiliar(self):
        def abrir(requisicao, timeout):
            if requisicao.full_url.endswith("/api/v1/users/login"):
                return RespostaFalsa({"access_token": "token"})
            self.assertIn("/api/v1/imoveis/texto-reg-auxiliar", requisicao.full_url)
            self.assertIn("numero_matricula=29538", requisicao.full_url)
            return RespostaFalsa({"numero_matricula": 29538, "texto": "R.01 - PENHOR DE SOJA."})

        resultado = ClienteTri7(self.configuracao(), abridor=abrir).buscar_texto_registro_auxiliar(29538)

        self.assertEqual(resultado, {"numero_registro": "29538", "texto": "R.01 - PENHOR DE SOJA."})

    def test_registro_auxiliar_404_tem_erro_proprio(self):
        def abrir(requisicao, timeout):
            if requisicao.full_url.endswith("/api/v1/users/login"):
                return RespostaFalsa({"access_token": "token"})
            raise HTTPError(requisicao.full_url, 404, "Not Found", {}, io.BytesIO(b'{"detail":"not found"}'))

        with self.assertRaises(RegistroAuxiliarTri7NaoEncontrado):
            ClienteTri7(self.configuracao(), abridor=abrir).buscar_texto_registro_auxiliar(7)

    def test_busca_protocolo_completo(self):
        resposta = {
            "protocolo": {"protocolo_numero": 185126, "descricao_titulo": "ESCRITURA PÚBLICA DE VENDA E COMPRA"},
            "itens_do_pedido": [{"natureza_formal_descricao": "Venda e Compra"}],
        }

        def abrir(requisicao, timeout):
            if requisicao.full_url.endswith("/api/v1/users/login"):
                return RespostaFalsa({"access_token": "token"})
            self.assertIn("/api/v1/imoveis/protocolo-completo", requisicao.full_url)
            self.assertIn("protocolo=185126", requisicao.full_url)
            return RespostaFalsa(resposta)

        resultado = ClienteTri7(self.configuracao(), abridor=abrir).buscar_protocolo_completo("185.126")

        self.assertEqual(resultado, resposta)

    def test_protocolo_404_tem_erro_proprio(self):
        def abrir(requisicao, timeout):
            if requisicao.full_url.endswith("/api/v1/users/login"):
                return RespostaFalsa({"access_token": "token"})
            raise HTTPError(requisicao.full_url, 404, "Not Found", {}, io.BytesIO(b'{"detail":"not found"}'))

        with self.assertRaises(ProtocoloTri7NaoEncontrado):
            ClienteTri7(self.configuracao(), abridor=abrir).buscar_protocolo_completo(999999)

    def test_protocolo_recusa_numero_diferente_na_resposta(self):
        def abrir(requisicao, timeout):
            if requisicao.full_url.endswith("/api/v1/users/login"):
                return RespostaFalsa({"access_token": "token"})
            return RespostaFalsa({"protocolo": {"protocolo_numero": 999999}, "itens_do_pedido": []})

        with self.assertRaises(RespostaTri7Invalida):
            ClienteTri7(self.configuracao(), abridor=abrir).buscar_protocolo_completo(185126)

    def test_protocolo_sem_chave_protocolo_e_resposta_invalida(self):
        def abrir(requisicao, timeout):
            if requisicao.full_url.endswith("/api/v1/users/login"):
                return RespostaFalsa({"access_token": "token"})
            return RespostaFalsa({"itens_do_pedido": []})

        with self.assertRaises(RespostaTri7Invalida):
            ClienteTri7(self.configuracao(), abridor=abrir).buscar_protocolo_completo(185126)

    def test_busca_livro_protocolos_por_periodo(self):
        resposta = {
            "data_inicio": "2026-08-01",
            "data_fim": "2026-08-25",
            "protocolos": [{"protocolo": 185569}],
        }

        def abrir(requisicao, timeout):
            if requisicao.full_url.endswith("/api/v1/users/login"):
                return RespostaFalsa({"access_token": "token"})
            self.assertIn("/api/v1/imoveis/livro-protocolo", requisicao.full_url)
            self.assertIn("data_inicio=2026-08-01", requisicao.full_url)
            self.assertIn("data_fim=2026-08-25", requisicao.full_url)
            return RespostaFalsa(resposta)

        resultado = ClienteTri7(self.configuracao(), abridor=abrir).buscar_livro_protocolos(
            date(2026, 8, 1), date(2026, 8, 25),
        )
        self.assertEqual(resultado, resposta)

    def test_livro_recusa_intervalo_superior_a_trinta_e_um_dias(self):
        cliente = ClienteTri7(self.configuracao(), abridor=lambda *_args, **_kwargs: None)
        with self.assertRaises(ValueError):
            cliente.buscar_livro_protocolos(date(2026, 7, 1), date(2026, 8, 1))

    def test_livro_recusa_resposta_sem_lista_de_protocolos(self):
        def abrir(requisicao, timeout):
            if requisicao.full_url.endswith("/api/v1/users/login"):
                return RespostaFalsa({"access_token": "token"})
            return RespostaFalsa({"protocolos": None})

        with self.assertRaises(RespostaTri7Invalida):
            ClienteTri7(self.configuracao(), abridor=abrir).buscar_livro_protocolos(
                date(2026, 8, 1), date(2026, 8, 25),
            )


if __name__ == "__main__":
    unittest.main()
