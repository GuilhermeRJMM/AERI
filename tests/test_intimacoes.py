import unittest
from datetime import date
from pathlib import Path
from uuid import uuid4


from backend.app.servicos import intimacoes as servico
from ferramentas.abrir_pasta_intimacao import caminho_pasta


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

    def test_novo_andamento_e_opcional_na_conferencia(self):
        self.assertIsNone(servico.validar_novo_andamento(None))
        self.assertIsNone(servico.validar_novo_andamento({}))
        self.assertEqual(
            "Intimação por edital",
            servico.validar_novo_andamento({"nomeAndamento": " Intimação por edital "}),
        )

    def test_migracao_importa_somente_os_39_ativos(self):
        caminho = Path(__file__).parents[1] / "backend/app/migrations/003_nome_ultimo_andamento.sql"
        sql = caminho.read_text(encoding="utf-8")

        self.assertEqual(39, sql.count("('IN"))
        self.assertNotIn("Desistência Concluída", sql)
        self.assertIn("backup_intimacoes_20260702_antes_importacao", sql)


    def test_resolve_pasta_especifica_de_protocolo_2025(self):
        caminho = caminho_pasta("IN01430613C")

        self.assertEqual("IN01430613C", caminho.name)
        self.assertIn("06 - 2025", str(caminho))
        self.assertIn("03 - Intimacao por Edital", str(caminho))

    def test_resolve_pasta_padrao_para_protocolos_2026(self):
        caminho = caminho_pasta("in01625306c")

        self.assertEqual("IN01625306C", caminho.name)
        self.assertIn("07 - 2026", str(caminho))
        self.assertIn("02 - Agua. pagamento (emolu informados)", str(caminho))


if __name__ == "__main__":
    unittest.main()
