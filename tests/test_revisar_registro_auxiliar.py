import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, Mock, patch

from fastapi import HTTPException

from backend.app.rotas.registros_auxiliares import revisar_registro_auxiliar
from backend.app.servicos.tri7 import ErroTri7, RegistroAuxiliarTri7NaoEncontrado


def _conexao_falsa():
    conexao = MagicMock()
    cursor = MagicMock()
    conexao.__enter__.return_value = conexao
    conexao.cursor.return_value.__enter__.return_value = cursor
    return conexao, cursor


class TesteRevisarRegistroAuxiliar(unittest.TestCase):
    def test_numero_invalido_retorna_422_sem_consultar_tri7(self):
        with patch("backend.app.rotas.registros_auxiliares.cliente_tri7") as obter_cliente:
            with self.assertRaises(HTTPException) as contexto:
                revisar_registro_auxiliar(0, request=Mock(), usuario="ADM")
            self.assertEqual(contexto.exception.status_code, 422)
            obter_cliente.assert_not_called()

    @patch("backend.app.rotas.registros_auxiliares.registrar_auditoria_cursor")
    @patch("backend.app.rotas.registros_auxiliares.conectar")
    @patch("backend.app.rotas.registros_auxiliares.cliente_tri7")
    def test_registro_ausente_retorna_404(self, obter_cliente, conectar_mock, _auditoria):
        obter_cliente.return_value.buscar_texto_registro_auxiliar.side_effect = (
            RegistroAuxiliarTri7NaoEncontrado("Registro Auxiliar 999999 não encontrado.")
        )
        conexao, _cursor = _conexao_falsa()
        conectar_mock.return_value = conexao

        with self.assertRaises(HTTPException) as contexto:
            revisar_registro_auxiliar(999999, request=Mock(), usuario="ADM")

        self.assertEqual(contexto.exception.status_code, 404)

    @patch("backend.app.rotas.registros_auxiliares.registrar_auditoria_cursor")
    @patch("backend.app.rotas.registros_auxiliares.conectar")
    @patch("backend.app.rotas.registros_auxiliares.cliente_tri7")
    def test_falha_na_tri7_retorna_502_e_registra_erro(self, obter_cliente, conectar_mock, _auditoria):
        obter_cliente.return_value.buscar_texto_registro_auxiliar.side_effect = ErroTri7("Tri7 indisponível.")
        conexao, cursor = _conexao_falsa()
        conectar_mock.return_value = conexao

        with self.assertRaises(HTTPException) as contexto:
            revisar_registro_auxiliar(29461, request=Mock(), usuario="ADM")

        self.assertEqual(contexto.exception.status_code, 502)
        self.assertTrue(any("registros_auxiliares_erros_aeri" in str(chamada) for chamada in cursor.execute.call_args_list))

    @patch("backend.app.rotas.registros_auxiliares.registrar_auditoria_cursor")
    @patch("backend.app.rotas.registros_auxiliares._estado_json", return_value={"limiteInicial": 29461})
    @patch("backend.app.rotas.registros_auxiliares._salvar_indice")
    @patch("backend.app.rotas.registros_auxiliares.conectar")
    @patch("backend.app.rotas.registros_auxiliares.cliente_tri7")
    def test_regrava_indice_com_texto_atualizado_da_tri7(
        self, obter_cliente, conectar_mock, salvar_indice, _estado, _auditoria
    ):
        obter_cliente.return_value.buscar_texto_registro_auxiliar.return_value = {
            "texto": "R.01 - ALIENAÇÃO DE SOJA... AV.02 - RETIFICAÇÃO: onde se lê SOJA, leia-se MILHO."
        }
        conexao, _cursor = _conexao_falsa()
        conectar_mock.return_value = conexao
        salvar_indice.return_value = (
            {
                "numero": 29461, "modalidade": "ALIENAÇÃO", "situacao": "ATIVO",
                "pessoas": [], "produtos": ["MILHO", "SOJA"], "safras": ["2025/2026"],
                "consultado_em": datetime.now(timezone.utc), "alterado": True,
            },
            False,
        )

        resultado = revisar_registro_auxiliar(29461, request=Mock(), usuario="ADM")

        self.assertEqual(resultado["status"], "OK")
        self.assertFalse(resultado["novo"])
        self.assertEqual(resultado["item"]["numero"], 29461)
        self.assertTrue(resultado["item"]["alterado"])
        self.assertEqual(resultado["estado"]["limiteInicial"], 29461)
        salvar_indice.assert_called_once()
        self.assertEqual(salvar_indice.call_args.args[1], 29461)
        self.assertTrue(any(
            "limite_inicial=GREATEST" in str(chamada)
            for chamada in _cursor.execute.call_args_list
        ))


if __name__ == "__main__":
    unittest.main()
