import re
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException

from backend.app.rotas.intimacoes import _analisar_versao_esperada
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
                "fase": "EDITAL",
                "protocolo_rtd": "20260708155369985",
                "numero_os_tri7": "12345",
                "protocolo_tri7": "TRI7-123",
                "certidao_decurso_prazo": None,
                "data_intimacao": date(2026, 7, 8),
                "data_certificacao": None,
                "valor_pago_onr": Decimal("530.07"),
                "valor_usado": Decimal("100.00"),
                "atualizado_em": datetime(2026, 7, 8, 12, 0, 0),
            }
        )

        self.assertEqual("Prenotado", item["nomeAndamento"])
        self.assertEqual("2026-07-01", item["ultimoAndamento"])
        self.assertEqual("EDITAL", item["fase"])
        self.assertEqual("20260708155369985", item["protocoloRtd"])
        self.assertEqual("2026-07-08", item["dataIntimacao"])
        self.assertEqual(430.07, item["saldoOs"])

    def test_valida_campos_financeiros_e_protocolo_rtd(self):
        campos = servico.validar_campos_fase_inicial(
            {
                "protocoloRtd": "20260708155369985",
                "numeroOsTri7": "OS 500",
                "valorPagoOnr": "530.07",
                "valorUsado": "159.76",
                "dataIntimacao": "2026-07-08",
            }
        )

        self.assertEqual("20260708155369985", campos["protocolo_rtd"])
        self.assertEqual(date(2026, 7, 8), campos["data_intimacao"])
        self.assertEqual(Decimal("530.07"), campos["valor_pago_onr"])
        self.assertEqual(Decimal("159.76"), campos["valor_usado"])

    def test_campos_novos_usam_valores_iniciais_provisorios(self):
        campos = servico.validar_campos_fase_inicial({})

        self.assertEqual(Decimal("530.07"), campos["valor_pago_onr"])
        self.assertEqual(Decimal("0.00"), campos["valor_usado"])
        self.assertIsNone(campos["protocolo_rtd"])

    def test_migracao_cria_colunas_da_fase_inicial(self):
        caminho = Path(__file__).parents[1] / "backend/app/migrations/011_campos_fase_inicial_intimacoes.sql"
        sql = caminho.read_text(encoding="utf-8")

        for coluna in (
            "protocolo_rtd", "numero_os_tri7", "protocolo_tri7",
            "certidao_decurso_prazo", "data_intimacao", "data_certificacao",
            "valor_pago_onr", "valor_usado",
        ):
            self.assertIn(coluna, sql)

    def test_classifica_fase_pelo_andamento(self):
        self.assertEqual(
            servico.FASE_EDITAL,
            servico.fase_por_andamento("Aguardando pedido de Edital", servico.FASE_INICIAL),
        )
        self.assertEqual(
            servico.FASE_CONSOLIDACAO,
            servico.fase_por_andamento("Aguardando pedido de Consolidação", servico.FASE_INICIAL),
        )
        self.assertEqual(
            servico.FASE_CONSOLIDACAO,
            servico.fase_por_andamento("Intimação Positiva", servico.FASE_INICIAL),
        )

    def test_andamento_generico_preserva_fase_manual(self):
        self.assertEqual(
            servico.FASE_EDITAL,
            servico.fase_por_andamento("Aguardando diligências RTD", servico.FASE_EDITAL),
        )

    def test_fase_de_consolidacao_nao_regride_por_edital(self):
        self.assertEqual(
            servico.FASE_CONSOLIDACAO,
            servico.fase_por_andamento("Aguardando pedido de Edital", servico.FASE_CONSOLIDACAO),
        )

    def test_validacao_aceita_fase_manual_e_automatiza_avanco(self):
        resultado = servico.validar_intimacao(
            {
                "protocolo": "IN01625306C",
                "credor": "Credor",
                "devedor": "Devedor",
                "nomeAndamento": "Aguardando pedido de Edital",
                "ultimoAndamento": "2026-07-27",
                "fase": "INTIMACAO",
            }
        )

        self.assertEqual(servico.FASE_EDITAL, resultado[5])

    def test_migracao_classifica_protocolos_informados(self):
        caminho = Path(__file__).parents[1] / "backend/app/migrations/010_fases_intimacoes.sql"
        sql = caminho.read_text(encoding="utf-8")

        protocolos = set(re.findall(r"'(IN\d{8}C)'", sql))
        self.assertEqual(31, len(protocolos))
        self.assertIn("IN01650919C", protocolos)
        self.assertIn("IN01345616C", protocolos)

    def test_migracao_preenche_fase_nula_com_fase_inicial(self):
        # Regressão: a migração 010 só classificou uma lista fixa de
        # protocolos que existiam naquele momento; qualquer intimação fora
        # dela (anterior à migração, ou reimportada depois) ficou com
        # fase=NULL, valor aceito pela CHECK constraint mas que não bate com
        # nenhuma das 3 abas do frontend (comparação por igualdade exata) --
        # a intimação sumia dos filtros mesmo continuando cadastrada.
        caminho = Path(__file__).parents[1] / "backend/app/migrations/022_backfill_fase_intimacoes_nula.sql"
        sql = caminho.read_text(encoding="utf-8")

        self.assertIn("SET fase = 'INTIMACAO'", sql)
        self.assertIn("WHERE fase IS NULL", sql)

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

    def test_versao_esperada_aceita_iso_valido(self):
        versao = _analisar_versao_esperada(
            {"atualizadoEm": "2026-08-06T21:23:45.123456+00:00"}
        )

        self.assertEqual(
            versao,
            datetime(2026, 8, 6, 21, 23, 45, 123456, tzinfo=timezone.utc),
        )

    def test_versao_esperada_rejeita_valor_ausente_ou_invalido(self):
        for dados in ({}, {"atualizadoEm": "nao-e-uma-data"}, {"atualizadoEm": None}):
            with self.subTest(dados=dados):
                with self.assertRaises(HTTPException) as erro:
                    _analisar_versao_esperada(dados)
                self.assertEqual(erro.exception.status_code, 422)

    def test_detalhes_ficam_disponiveis_em_todas_as_fases(self):
        javascript = (Path(__file__).parents[1] / "backend/static/js/intimacoes.js").read_text(
            encoding="utf-8"
        )

        self.assertIn("acoesIntimacao(item, true)", javascript)
        self.assertNotIn("if (!inicial || !detalhesAbertos.has(item.id))", javascript)


if __name__ == "__main__":
    unittest.main()
