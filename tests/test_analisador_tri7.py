import unittest
from unittest.mock import Mock, patch

from fastapi import HTTPException

from backend.app.rotas.analisador import analisar_por_numero
from backend.app.servicos.tri7 import MatriculaTri7NaoEncontrada


class TesteRotaAnalisadorTri7(unittest.TestCase):
    @patch("backend.app.rotas.analisador.registrar_auditoria")
    @patch("backend.app.rotas.analisador._regras_aprovadas", return_value=[])
    @patch("backend.app.rotas.analisador.cliente_tri7")
    def test_busca_texto_e_reaproveita_processamento_atual(self, obter_cliente, _regras, auditoria):
        obter_cliente.return_value.buscar_texto_matricula.return_value = {
            "numero_matricula": "10148",
            "texto": "MATRÍCULA 10.148.\nR.01 - COMPRA E VENDA.",
        }
        resultado = analisar_por_numero(
            {"numero_matricula": "10.148"},
            request=Mock(),
            usuario="operador",
        )
        self.assertEqual(resultado["numero_matricula"], "10148")
        self.assertEqual(resultado["origem"], "TRI7")
        self.assertIn("resultado", resultado)
        obter_cliente.return_value.buscar_texto_matricula.assert_called_once_with("10148")
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
