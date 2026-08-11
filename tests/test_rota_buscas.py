import os
import unittest
from unittest.mock import patch

from fastapi import HTTPException

from backend.app.rotas import buscas


class _CursorFalso:
    def __init__(self, linhas=None):
        self.linhas = linhas or []
        self.comandos = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, comando, parametros=()):
        self.comandos.append((comando, parametros))

    def fetchall(self):
        return self.linhas


class _ConexaoFalsa:
    def __init__(self, cursor):
        self._cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def cursor(self):
        return self._cursor


class _ClienteTri7Falso:
    def buscar_texto_matricula(self, numero):
        if int(numero) == 2:
            raise buscas.MatriculaTri7NaoEncontrada("ausente")
        return {"texto": f"MATRÍCULA {numero}. IMÓVEL: Lote. PROPRIETÁRIO: JOÃO."}


class TesteRotaBuscas(unittest.TestCase):
    def setUp(self):
        self.ambiente = patch.dict(os.environ, {"AERI_BUSCAS_HMAC_KEY": "segredo-de-teste-com-mais-de-16"})
        self.ambiente.start()

    def tearDown(self):
        self.ambiente.stop()

    def test_lote_preserva_ordem_e_trata_matricula_ausente(self):
        with patch.object(buscas, "cliente_tri7", return_value=_ClienteTri7Falso()), patch.object(
            buscas._LimitadorTaxa, "aguardar", return_value=None
        ):
            resultados, falha = buscas._consultar_lote([1, 2, 3])

        self.assertIsNone(falha)
        self.assertEqual([1, 2, 3], [item["numero"] for item in resultados])
        self.assertEqual(["OK", "NAO_ENCONTRADA", "OK"], [item["status"] for item in resultados])

    def test_nome_com_numero_continua_sendo_pesquisado_como_nome(self):
        cursor = _CursorFalso()
        with patch.object(buscas, "conectar", return_value=_ConexaoFalsa(cursor)):
            resposta = buscas.pesquisar_titularidade("FAZENDA 3 IRMÃOS", 100, "usuario")

        self.assertEqual("NOME", resposta["tipoBusca"])
        self.assertIn("%FAZENDA 3 IRMAOS%", cursor.comandos[0][1])

    def test_cpf_incompleto_e_recusado(self):
        with self.assertRaises(HTTPException) as contexto:
            buscas.pesquisar_titularidade("123.456", 100, "usuario")
        self.assertEqual(422, contexto.exception.status_code)

    def test_documento_exato_usa_hash_e_nao_envia_cpf_ao_banco(self):
        cursor = _CursorFalso()
        with patch.object(buscas, "conectar", return_value=_ConexaoFalsa(cursor)):
            resposta = buscas.pesquisar_titularidade("123.456.789-01", 100, "usuario")

        parametros = cursor.comandos[0][1]
        self.assertEqual("DOCUMENTO_EXATO", resposta["tipoBusca"])
        self.assertNotIn("12345678901", parametros)
        self.assertTrue(any(isinstance(item, str) and len(item) == 64 for item in parametros))


if __name__ == "__main__":
    unittest.main()
