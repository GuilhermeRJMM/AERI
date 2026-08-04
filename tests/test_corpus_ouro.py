import json
import unittest
from pathlib import Path

from backend.app.servicos.analise_matricula import analisar_matricula


CASOS = json.loads(
    (Path(__file__).parent / "corpus_ouro" / "manifest.json").read_text(encoding="utf-8")
)


class TesteCorpusOuro(unittest.TestCase):
    def test_casos_de_referencia(self):
        for caso in CASOS:
            with self.subTest(caso=caso["id"]):
                resultado = analisar_matricula(caso["texto"])
                esperado = caso["esperado"]
                if "resultado" in esperado:
                    self.assertEqual(esperado["resultado"], resultado["resultado"])
                if "tipo" in esperado:
                    self.assertEqual(esperado["tipo"], resultado["imovel"]["tipo"])
                if "ato" in esperado:
                    ato = next(item for item in resultado["atos"] if item["codigo"] == esperado["ato"]["codigo"])
                    for chave, valor in esperado["ato"].items():
                        self.assertEqual(valor, ato[chave])
                grupos = resultado["imovel"]["campos_aplicaveis"]
                itens = [item for grupo in grupos.values() for item in grupo]
                campos = {item["rotulo"]: item["valor"] for item in itens}
                for rotulo, valor in esperado.get("campos", {}).items():
                    self.assertEqual(valor, campos[rotulo])
                rotulos = set(campos)
                self.assertFalse(rotulos & set(esperado.get("rotulos_ausentes", [])))
                self.assertTrue(set(esperado.get("campos_presentes", [])).issubset(rotulos))


if __name__ == "__main__":
    unittest.main()
