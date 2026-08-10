import unittest

from backend.app.incra import classificar_ato, resumir_protocolo_tri7


class ClassificacaoIncraTests(unittest.TestCase):
    def test_inscricao_no_car_fica_fora_das_hipoteses(self):
        status, _ = classificar_ato("INSCRIÇÃO NO CAR")

        self.assertEqual(status, "FORA_DAS_HIPOTESES")

    def test_cadastro_ambiental_rural_fica_fora_das_hipoteses(self):
        status, _ = classificar_ato("Cadastro Ambiental Rural")

        self.assertEqual(status, "FORA_DAS_HIPOTESES")

    def test_reserva_legal_continua_sendo_comunicada(self):
        status, _ = classificar_ato("Averbação de Reserva Legal")

        self.assertEqual(status, "COMUNICAR")

    def test_georreferenciamento_continua_sendo_comunicado(self):
        status, _ = classificar_ato("Georreferenciamento")

        self.assertEqual(status, "COMUNICAR")


class ResumoTri7IncraTests(unittest.TestCase):
    def test_finalizado_decurso_de_prazo_identifica_cancelamento(self):
        protocolo = {
            "protocolo": {"protocolo_numero": 185000},
            "andamentos": [{
                "andamento_tipo": "  Finalizado   Decurso de Prazo ",
                "data_hora": "2026-08-10T10:00:00",
            }],
            "itens_do_pedido": [],
        }

        resultado = resumir_protocolo_tri7(protocolo)

        self.assertTrue(resultado["cancelado"])
        self.assertEqual(resultado["situacaoTri7"], "CANCELADO_DECURSO_PRAZO")
        self.assertIsNone(resultado["alertaTri7"])

    def test_finalizado_comum_nao_e_cancelamento(self):
        protocolo = {
            "protocolo": {"protocolo_numero": 185001},
            "andamentos": [{"andamento_tipo": "Finalizado", "data_hora": "2026-08-10T10:00:00"}],
            "itens_do_pedido": [{
                "dados_imovel": {"tipo_registro": "M", "numero_registro": 39834},
                "atos_registrados": {"ato_tipo": "A", "ato_numero": 1},
            }],
        }

        resultado = resumir_protocolo_tri7(
            protocolo,
            textos_matriculas={39834: "AV.01-39.834. Protocolo n.º 185.001. Texto."},
        )

        self.assertFalse(resultado["cancelado"])
        self.assertEqual(resultado["situacaoTri7"], "PRATICADO")

    def test_agrupa_e_deduplica_atos_por_matricula(self):
        protocolo = {"protocolo": {"protocolo_numero": 185002}, "andamentos": [], "itens_do_pedido": [
            {"dados_imovel": {"tipo_registro": "M", "numero_registro": 39834},
             "atos_registrados": {"ato_tipo": "M", "ato_numero": 0}},
            {"dados_imovel": {"tipo_registro": "M", "numero_registro": 39834},
             "atos_registrados": {"ato_tipo": "A", "ato_numero": 1}},
            {"dados_imovel": {"tipo_registro": "M", "numero_registro": 39834},
             "atos_registrados": {"ato_tipo": "AV", "ato_numero": 1}},
            {"dados_imovel": {"tipo_registro": "M", "numero_registro": 39835},
             "atos_registrados": {"ato_tipo": "R", "ato_numero": 2}},
            {"dados_imovel": {"tipo_registro": "RA", "numero_registro": 29538},
             "atos_registrados": {"ato_tipo": "R", "ato_numero": 1}},
        ]}

        resultado = resumir_protocolo_tri7(protocolo, textos_matriculas={
            39834: "MATRÍCULA 39.834. Protocolo n.º 185.002.\nAV.01-39.834. Protocolo 185.002.",
            39835: "MATRÍCULA 39.835. Protocolo n.º 185.002.\nR.02-39.835. Protocolo 185.002.",
        })

        self.assertEqual(resultado["matriculas"], [
            {"numero": "39834", "numeroFormatado": "39.834", "atos": ["M.0", "AV.1"]},
            {"numero": "39835", "numeroFormatado": "39.835", "atos": ["R.2"]},
        ])

    def test_cancelado_com_ato_vinculado_pede_revisao(self):
        protocolo = {
            "protocolo": {"protocolo_numero": 185003},
            "andamentos": [{"andamento_tipo": "Finalizado Decurso de Prazo"}],
            "itens_do_pedido": [{
                "dados_imovel": {"tipo_registro": "M", "numero_registro": 100},
                "atos_registrados": {"ato_tipo": "R", "ato_numero": 1},
            }],
        }

        resultado = resumir_protocolo_tri7(
            protocolo,
            textos_matriculas={100: "R.01-100. Protocolo n.º 185.003. Texto."},
        )

        self.assertEqual(resultado["situacaoTri7"], "CANCELADO_DECURSO_PRAZO")
        self.assertIn("revisar", resultado["alertaTri7"].lower())

    def test_sem_cancelamento_e_sem_ato_fica_sem_ato_identificado(self):
        resultado = resumir_protocolo_tri7({"andamentos": [], "itens_do_pedido": []})

        self.assertEqual(resultado["situacaoTri7"], "SEM_ATO")
        self.assertEqual(resultado["matriculas"], [])

    def test_ato_de_protocolo_cancelado_so_vinculado_na_api_nao_e_praticado(self):
        protocolo = {
            "protocolo": {"protocolo_numero": 183124},
            "andamentos": [{"andamento_tipo": "Finalizado Decurso de Prazo"}],
            "itens_do_pedido": [{
                "dados_imovel": {"tipo_registro": "M", "numero_registro": 37257},
                "atos_registrados": {"ato_tipo": "A", "ato_numero": 23},
            }],
        }

        resultado = resumir_protocolo_tri7(
            protocolo,
            textos_matriculas={37257: "AV.22-37.257. Protocolo n.º 182.999. Texto anterior."},
        )

        self.assertEqual(resultado["situacaoTri7"], "CANCELADO_DECURSO_PRAZO")
        self.assertEqual(resultado["matriculas"], [])
        self.assertEqual(resultado["atosVinculadosNaoConfirmados"], 1)


if __name__ == "__main__":
    unittest.main()
