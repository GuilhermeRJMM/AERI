import unittest

from fastapi import HTTPException

from backend.app.rotas.analisador import _validar_feedback


class TesteDivergenciasAnalise(unittest.TestCase):
    def test_feedback_correto_nao_exige_dominio(self):
        dados = _validar_feedback({
            "numero_matricula": "39.802",
            "avaliacao": "CORRETO",
            "resultado_hash": "a" * 64,
            "motor_versao": "2.0.0",
        })
        self.assertEqual("39802", dados["numero"])
        self.assertEqual([], dados["dominios"])

    def test_revisao_exige_dominio(self):
        with self.assertRaises(HTTPException) as contexto:
            _validar_feedback({
                "numero_matricula": "67",
                "avaliacao": "REVISAR",
                "resultado_hash": "b" * 64,
                "dominios": [],
            })
        self.assertEqual(422, contexto.exception.status_code)

    def test_rejeita_hash_e_dominio_invalidos(self):
        with self.assertRaises(HTTPException):
            _validar_feedback({
                "numero_matricula": "67",
                "avaliacao": "REVISAR",
                "resultado_hash": "texto",
                "dominios": ["OUTRO"],
            })


if __name__ == "__main__":
    unittest.main()
