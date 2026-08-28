import unittest

from backend.app.servicos.mapa_onr import validar_json_mapa_onr


class ValidacaoBackendMapaOnrTests(unittest.TestCase):
    def test_rejeita_arquivo_sem_campos_obrigatorios(self):
        resultado = validar_json_mapa_onr("urbano", {})
        self.assertFalse(resultado["valido"])
        self.assertGreater(resultado["errosTotal"], 0)

    def test_rejeita_tipo_desconhecido(self):
        with self.assertRaises(ValueError):
            validar_json_mapa_onr("outro", {})


if __name__ == "__main__":
    unittest.main()
