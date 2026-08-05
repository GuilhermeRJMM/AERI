import json
import unittest
from pathlib import Path

from scripts.indexar_registros_auxiliares import (
    LimitadorTaxa,
    compactar_checkpoint,
    ler_checkpoint,
    processar,
)


class ClienteRegistroAuxiliarFalso:
    def buscar_texto_registro_auxiliar(self, numero):
        return {
            "numero_registro": str(numero),
            "texto": """
                R.01 - PENHOR. EMITENTE/DEVEDOR: João da Silva, inscrito no CPF
                sob o n.º 123.456.789-01. OBJETO DA GARANTIA: SOJA, safra 2025/2026.
            """,
        }


class TesteIndexacaoRegistrosAuxiliares(unittest.TestCase):
    def test_processamento_persiste_indice_e_hash_sem_texto_integral(self):
        item = processar(10, ClienteRegistroAuxiliarFalso(), LimitadorTaxa(1000), 1)

        self.assertEqual(item["status"], "OK")
        self.assertEqual(item["numero"], 10)
        self.assertEqual(len(item["texto_hash"]), 64)
        self.assertNotIn("texto", item)
        self.assertEqual(item["produtos"], ["SOJA"])
        self.assertEqual(item["safras"], ["2025/2026"])
        self.assertEqual(len(item["pessoas"]), 1)

    def test_checkpoint_e_compactado_em_ordem_e_sem_duplicatas(self):
        resultados = {
            2: {"numero": 2, "status": "NAO_ENCONTRADO"},
            1: {"numero": 1, "status": "OK", "texto_hash": "a" * 64},
        }
        caminho = Path.cwd() / "output" / "registros_auxiliares" / ".teste-checkpoint.jsonl"
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.unlink(missing_ok=True)
        caminho.with_suffix(".jsonl.tmp").unlink(missing_ok=True)
        self.addCleanup(caminho.unlink, missing_ok=True)
        compactar_checkpoint(caminho, resultados)
        linhas = [json.loads(linha) for linha in caminho.read_text(encoding="utf-8").splitlines()]

        self.assertEqual([item["numero"] for item in linhas], [1, 2])
        self.assertEqual(ler_checkpoint(caminho), resultados)


if __name__ == "__main__":
    unittest.main()
