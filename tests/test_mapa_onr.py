import asyncio
import os
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi import HTTPException, Request
from fastapi.responses import Response

from backend.app.main import seguranca_http
from backend.app.rotas.mapa_onr import abrir_conversor_mapa_onr, consultar_matricula_mapa_onr
from backend.app.servicos.mapa_onr import (
    construir_contexto_mapa_onr,
    extrair_confrontantes_semanticos,
    modo_analise_mapa_onr,
)
from backend.app.servicos.tri7 import MatriculaTri7NaoEncontrada


class TesteMapaOnr(unittest.TestCase):
    @patch("backend.app.rotas.mapa_onr.registrar_auditoria")
    @patch("backend.app.rotas.mapa_onr.analisar_matricula")
    @patch("backend.app.rotas.mapa_onr.cliente_tri7")
    def test_consulta_tri7_entrega_texto_ao_conversor_sem_persistir(
        self,
        obter_cliente,
        analisar,
        auditoria,
    ):
        obter_cliente.return_value.buscar_texto_matricula.return_value = {
            "numero_matricula": "10151",
            "texto": "MATRÍCULA 10.151. IMÓVEL: Fazenda Samambaia.",
        }
        analisar.return_value = {"imovel": {"tipo": "RURAL"}}

        resultado = consultar_matricula_mapa_onr(
            {"numero_matricula": "10.151"},
            request=Mock(),
            usuario="operador",
        )

        self.assertEqual(resultado, {
            "numero_matricula": "10151",
            "tipo_imovel": "rural",
            "texto": "MATRÍCULA 10.151. IMÓVEL: Fazenda Samambaia.",
            "contexto_aeri": {
                "modo": "hibrido",
                "analise_aeri": {"tipo_imovel": "rural", "situacao": None},
                "confrontantes": [],
                "total_pendencias": 0,
            },
        })
        obter_cliente.return_value.buscar_texto_matricula.assert_called_once_with("10151")
        analisar.assert_called_once_with(
            "MATRÍCULA 10.151. IMÓVEL: Fazenda Samambaia.",
            numero_matricula="10151",
        )
        auditoria.assert_called_once()

    @patch("backend.app.rotas.mapa_onr.cliente_tri7")
    def test_matricula_ausente_retorna_404(self, obter_cliente):
        obter_cliente.return_value.buscar_texto_matricula.side_effect = MatriculaTri7NaoEncontrada(
            "Matrícula não encontrada na Tri7."
        )

        with self.assertRaises(HTTPException) as contexto:
            consultar_matricula_mapa_onr(
                {"numero_matricula": "999999"},
                request=Mock(),
                usuario="operador",
            )

        self.assertEqual(contexto.exception.status_code, 404)

    def test_numero_invalido_retorna_422(self):
        with self.assertRaises(HTTPException) as contexto:
            consultar_matricula_mapa_onr(
                {"numero_matricula": "10-A"},
                request=Mock(),
                usuario="operador",
            )

        self.assertEqual(contexto.exception.status_code, 422)

    def test_conversor_e_servido_fora_da_pasta_publica(self):
        resposta = abrir_conversor_mapa_onr(_usuario="operador")
        caminho = Path(resposta.path)

        self.assertEqual(caminho.name, "mapa_onr.html")
        self.assertEqual(caminho.parent.name, "private")
        self.assertTrue(caminho.exists())
        self.assertFalse(
            (Path(__file__).parents[1] / "backend/static/mapa_onr/index.html").exists()
        )

    def test_conversor_pode_ser_incorporado_apenas_na_mesma_origem_sem_sync(self):
        escopo = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "https",
            "path": "/api/mapa-onr/conversor",
            "raw_path": b"/api/mapa-onr/conversor",
            "query_string": b"",
            "root_path": "",
            "headers": [],
            "client": ("127.0.0.1", 12345),
            "server": ("aeri.example", 443),
        }

        async def responder(_request):
            return Response(status_code=200)

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SYNC_ORIGIN", None)
            os.environ.pop("SYNC_ORIGINS", None)
            resposta = asyncio.run(seguranca_http(Request(escopo), responder))

        self.assertIn(
            "frame-ancestors 'self';",
            resposta.headers["content-security-policy"],
        )
        self.assertEqual(resposta.headers["cache-control"], "no-store")

    def test_confrontante_nao_confunde_servidao_ou_nome_do_imovel_com_proprietario(self):
        texto = """
        confrontando com CNS: 02.618-7 | Mat. 30069 |
        SERVIDÃO DE LINHA DE TRANSMISSÃO, FAZENDA ABREUS no azimute 90°;
        confrontando com CNS: 02.618-7 | Mat. 21038 |
        FAZENDA ABREUS INCRA e propriedade de PESSOA APARECIDA... no azimute 91°;
        confrontando com CNS: 02.618-7 | Mat. 30067 |
        FAZENDA ABREUS, propriedade de PESSOA COMPLETA DA SILVA no azimute 92°.
        """

        confrontantes = extrair_confrontantes_semanticos(texto)
        por_matricula = {
            item["numero_matricula_confrontante"]: item for item in confrontantes
        }

        self.assertIsNone(
            por_matricula["30069"]["nome_proprietario_confrontante"]
        )
        self.assertIn(
            "SERVIDÃO DE LINHA DE TRANSMISSÃO, FAZENDA ABREUS",
            por_matricula["30069"]["descricoes_confrontacao"],
        )
        self.assertIsNotNone(por_matricula["30069"]["pendencia"])
        self.assertIsNone(
            por_matricula["21038"]["nome_proprietario_confrontante"]
        )
        self.assertIn("incompleto", por_matricula["21038"]["pendencia"])
        self.assertEqual(
            por_matricula["30067"]["nome_proprietario_confrontante"],
            "PESSOA COMPLETA DA SILVA",
        )
        self.assertEqual(por_matricula["30067"]["confianca"], "alta")

    def test_matricula_confrontante_repetida_e_agrupada(self):
        texto = """
        confrontando com CNS: 02.618-7 | Mat. 30069 |
        FAZENDA ABREUS, propriedade de PESSOA COMPLETA DA SILVA no azimute 90°;
        confrontando com CNS: 02.618-7 | Mat. 30.069 |
        FAZENDA ABREUS, propriedade de PESSOA COMPLETA DA SILVA no azimute 91°.
        """

        confrontantes = extrair_confrontantes_semanticos(texto)

        self.assertEqual(len(confrontantes), 1)
        self.assertEqual(confrontantes[0]["numero_matricula_confrontante"], "30069")
        self.assertEqual(len(confrontantes[0]["evidencias"]), 2)

    def test_modo_legado_desliga_contexto_hibrido_por_uma_variavel(self):
        with patch.dict(os.environ, {"MAPA_ONR_MODO_ANALISE": "legado"}):
            contexto = construir_contexto_mapa_onr(
                "confrontando com CNS: 02.618-7 | Mat. 30067 | FAZENDA ABREUS",
                {"imovel": {"tipo": "RURAL"}},
            )

        self.assertEqual(modo_analise_mapa_onr(), "hibrido")
        self.assertEqual(contexto, {
            "modo": "legado",
            "confrontantes": [],
            "total_pendencias": 0,
        })


if __name__ == "__main__":
    unittest.main()
