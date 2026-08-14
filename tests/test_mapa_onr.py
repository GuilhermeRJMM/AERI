import asyncio
import os
import unittest
from unittest.mock import Mock, patch

from fastapi import HTTPException, Request
from fastapi.responses import Response

from backend.app.main import seguranca_http
from backend.app.rotas.mapa_onr import consultar_matricula_mapa_onr
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

    def test_conversor_pode_ser_incorporado_apenas_na_mesma_origem_sem_sync(self):
        escopo = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "https",
            "path": "/static/mapa_onr/index.html",
            "raw_path": b"/static/mapa_onr/index.html",
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


if __name__ == "__main__":
    unittest.main()
