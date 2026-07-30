import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.consolidar_auditoria_registral import consolidar


class TesteConsolidarAuditoriaRegistral(unittest.TestCase):
    def test_separa_dominios_e_usa_ultima_tentativa(self):
        resultados = {
            1: {
                "numero_matricula": "1",
                "status": "OK",
                "prioridade_revisao": "P2-VALIDADA",
                "estado_auditoria": "VALIDADA_AUTOMATICAMENTE",
            },
            2: {
                "numero_matricula": "2",
                "status": "OK",
                "prioridade_revisao": "P0-CRITICA",
                "estado_auditoria": "REVISAR",
                "confianca_cadeia": "BAIXA",
                "veredito_cadeia": "REVISAR",
                "alertas_cadeia": "TITULARIDADE_FORA_DE_100",
                "evidencias_cadeia": "R.03",
            },
            3: {
                "numero_matricula": "3",
                "status": "OK",
                "prioridade_revisao": "P1-CONFERIR",
                "estado_auditoria": "REVISAR",
                "confianca_imovel": "MEDIA",
                "veredito_imovel": "REVISAR",
                "alertas_imovel": "CCI_NAO_EXTRAIDO",
                "evidencias_imovel": "CCI@AV.02",
            },
        }

        with (
            patch(
                "scripts.consolidar_auditoria_registral.ler_ultima_tentativa",
                return_value=resultados,
            ),
            patch("scripts.consolidar_auditoria_registral.gravar_csv") as gravar,
            patch("pathlib.Path.write_text"),
        ):
            resumo = consolidar(Path("entrada.csv"), Path("saida"), 1, 3)

        self.assertEqual(resumo["matriculas_consolidadas"], 3)
        self.assertEqual(resumo["dominios"]["onus"]["matriculas_para_revisao"], 0)
        self.assertEqual(resumo["dominios"]["cadeia"]["matriculas_para_revisao"], 1)
        self.assertEqual(resumo["dominios"]["imovel"]["matriculas_para_revisao"], 1)
        self.assertEqual(gravar.call_count, 4)


if __name__ == "__main__":
    unittest.main()
