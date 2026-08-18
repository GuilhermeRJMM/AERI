import unittest
from unittest.mock import MagicMock, patch

from backend.app.rotas.registros_auxiliares import pesquisar_registros_auxiliares


def _conexao_falsa():
    conexao = MagicMock()
    cursor = MagicMock()
    cursor.fetchall.return_value = []
    conexao.__enter__.return_value = conexao
    conexao.cursor.return_value.__enter__.return_value = cursor
    return conexao, cursor


def _sql_e_parametros(cursor):
    chamada = cursor.execute.call_args
    return chamada.args[0], chamada.args[1]


class TestePesquisaRegistroAuxiliar(unittest.TestCase):
    @patch("backend.app.rotas.registros_auxiliares.conectar")
    def test_digito_solto_no_nome_nao_vira_filtro_de_documento(self, conectar_mock):
        # Regressão: o filtro de documento nascia de qualquer dígito presente
        # no texto digitado. Pesquisar "Ls3 Saran Agropecuária Ltda" extraía o
        # "3" do nome e virava documentos_busca LIKE '%3%', que casa com quase
        # todo CPF do acervo -- a busca devolvia dezenas de registros de
        # outras pessoas como se fossem dessa empresa.
        conexao, cursor = _conexao_falsa()
        conectar_mock.return_value = conexao

        pesquisar_registros_auxiliares(
            busca="Ls3 Saran Agropecuaria Ltda", produto="Soja",
            safra="2025/2026", _usuario="TESTE",
        )

        sql, parametros = _sql_e_parametros(cursor)
        self.assertIn("nomes_busca LIKE", sql)
        self.assertNotIn("documentos_busca LIKE", sql)
        self.assertNotIn("%3%", parametros)

    @patch("backend.app.rotas.registros_auxiliares.conectar")
    def test_cpf_completo_continua_filtrando_por_documento(self, conectar_mock):
        conexao, cursor = _conexao_falsa()
        conectar_mock.return_value = conexao

        pesquisar_registros_auxiliares(
            busca="280.225.806-00", produto="Soja",
            safra="2026/2027", _usuario="TESTE",
        )

        sql, parametros = _sql_e_parametros(cursor)
        self.assertIn("documentos_busca LIKE", sql)
        self.assertIn("%28022580600%", parametros)

    @patch("backend.app.rotas.registros_auxiliares.conectar")
    def test_cnpj_completo_tambem_filtra_por_documento(self, conectar_mock):
        conexao, cursor = _conexao_falsa()
        conectar_mock.return_value = conexao

        pesquisar_registros_auxiliares(
            busca="12.345.678/0001-90", produto="Soja",
            safra="2026/2027", _usuario="TESTE",
        )

        sql, parametros = _sql_e_parametros(cursor)
        self.assertIn("documentos_busca LIKE", sql)
        self.assertIn("%12345678000190%", parametros)


if __name__ == "__main__":
    unittest.main()
