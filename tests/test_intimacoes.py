import importlib
import sys
import types
import unittest
from datetime import date
from pathlib import Path
from uuid import uuid4


class HTTPException(Exception):
    def __init__(self, status_code, detail):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


sys.modules.setdefault("fastapi", types.SimpleNamespace(HTTPException=HTTPException))
servico = importlib.import_module("backend.app.servicos.intimacoes")


class TesteIntimacoes(unittest.TestCase):
    def test_valida_nome_e_data_do_andamento(self):
        resultado = servico.validar_intimacao(
            {
                "protocolo": "in01625306c",
                "credor": "CAIXA ECONÔMICA FEDERAL",
                "devedor": "Pessoa devedora",
                "nomeAndamento": "Expedição de Intimação - RI",
                "ultimoAndamento": "2026-06-30",
            }
        )

        self.assertEqual("IN01625306C", resultado[0])
        self.assertEqual("Expedição de Intimação - RI", resultado[3])
        self.assertEqual(date(2026, 6, 30), resultado[4])

    def test_serializa_nome_do_andamento(self):
        item = servico.intimacao_json(
            {
                "id": uuid4(),
                "protocolo": "IN01625306C",
                "credor": "Credor",
                "devedor": "Devedor",
                "nome_andamento": "Prenotado",
                "ultimo_andamento": date(2026, 7, 1),
                "ultima_conferencia": None,
                "historico": [],
            }
        )

        self.assertEqual("Prenotado", item["nomeAndamento"])
        self.assertEqual("2026-07-01", item["ultimoAndamento"])

    def test_migracao_importa_somente_os_39_ativos(self):
        caminho = Path(__file__).parents[1] / "backend/app/migrations/003_nome_ultimo_andamento.sql"
        sql = caminho.read_text(encoding="utf-8")

        self.assertEqual(39, sql.count("('IN"))
        self.assertNotIn("Desistência Concluída", sql)
        self.assertIn("backup_intimacoes_20260702_antes_importacao", sql)


if __name__ == "__main__":
    unittest.main()
