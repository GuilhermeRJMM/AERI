import inspect
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi import HTTPException

from backend.app.rotas.analisador import (
    analisar,
    analisar_por_numero,
)
from backend.app.servicos.tri7 import MatriculaTri7NaoEncontrada


class TesteRotaAnalisadorTri7(unittest.TestCase):
    def test_texto_manual_e_restrito_exclusivamente_ao_admin(self):
        dependencia = inspect.signature(analisar).parameters["usuario"].default.dependency
        requisicao_admin = SimpleNamespace(
            state=SimpleNamespace(sessao={"perfil": "ADMIN", "deve_trocar_senha": False})
        )
        requisicao_substituto = SimpleNamespace(
            state=SimpleNamespace(sessao={"perfil": "SUBSTITUTO", "deve_trocar_senha": False})
        )

        self.assertEqual(dependencia(requisicao_admin, usuario="administrador"), "administrador")
        with self.assertRaises(HTTPException) as contexto:
            dependencia(requisicao_substituto, usuario="substituto")
        self.assertEqual(contexto.exception.status_code, 403)

    @patch("backend.app.rotas.analisador.registrar_auditoria")
    @patch("backend.app.rotas.analisador._regras_aprovadas", return_value=[])
    def test_texto_manual_aceita_numero_opcional_sem_persistir_texto(self, _regras, auditoria):
        resultado = analisar(
            {
                "numero_matricula": "29.774",
                "texto": "IMÓVEL: Lote 1. PROPRIETÁRIO: Fulano de Tal.",
            },
            request=Mock(),
            usuario="administrador",
        )

        self.assertEqual(resultado["numero_matricula"], "29774")
        self.assertEqual(resultado["origem"], "ENTRADA MANUAL")
        auditoria.assert_called_once()

    @patch("backend.app.rotas.analisador.registrar_auditoria")
    @patch("backend.app.rotas.analisador._regras_aprovadas", return_value=[])
    @patch("backend.app.rotas.analisador._executar_agente_na_matricula")
    @patch("backend.app.rotas.analisador.cliente_tri7")
    def test_busca_executa_agente_juridico_automaticamente(
        self, obter_cliente, executar_agente, _regras, auditoria,
    ):
        obter_cliente.return_value.buscar_texto_matricula.return_value = {
            "numero_matricula": "10148",
            "texto": "MATRÍCULA 10.148.\nR.01 - COMPRA E VENDA.",
        }
        executar_agente.return_value = {"estado": "CONCLUIDA", "parecer": {"conclusao": "ANALISE_CONCLUIDA"}}
        resultado = analisar_por_numero(
            {"numero_matricula": "10.148"},
            request=Mock(),
            usuario="operador",
        )
        self.assertEqual(resultado["numero_matricula"], "10148")
        self.assertEqual(resultado["origem"], "TRI7")
        self.assertIn("resultado", resultado)
        self.assertEqual("CONCLUIDA", resultado["agente_juridico"]["estado"])
        obter_cliente.return_value.buscar_texto_matricula.assert_called_once_with("10148")
        executar_agente.assert_called_once()
        auditoria.assert_called_once()

    @patch("backend.app.rotas.analisador.cliente_tri7")
    def test_matricula_ausente_retorna_404(self, obter_cliente):
        obter_cliente.return_value.buscar_texto_matricula.side_effect = MatriculaTri7NaoEncontrada(
            "Matrícula 999999 não encontrada na Tri7."
        )
        with self.assertRaises(HTTPException) as contexto:
            analisar_por_numero({"numero_matricula": "999999"}, request=Mock(), usuario="operador")
        self.assertEqual(contexto.exception.status_code, 404)

    def test_numero_invalido_retorna_422_sem_consultar_api(self):
        with self.assertRaises(HTTPException) as contexto:
            analisar_por_numero({"numero_matricula": "12-A"}, request=Mock(), usuario="operador")
        self.assertEqual(contexto.exception.status_code, 422)

if __name__ == "__main__":
    unittest.main()
