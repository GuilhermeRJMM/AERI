import unittest

from backend.app.incra import classificar_ato


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


if __name__ == "__main__":
    unittest.main()
