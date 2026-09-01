"""Inclui na suite Python/CI a regressao JS da acao em lote de pendencias."""
import shutil
import subprocess
import unittest
from pathlib import Path


class TesteAcaoEmLoteDePendencias(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node.js necessário para testar o painel")
    def test_marcar_todas_libera_a_exportacao(self):
        raiz = Path(__file__).resolve().parents[1]
        resultado = subprocess.run(
            [shutil.which("node"), str(raiz / "tests/test_mapa_onr_pendencias_lote.js")],
            cwd=raiz, capture_output=True, text=True, encoding="utf-8", timeout=30,
        )
        self.assertEqual(resultado.returncode, 0, resultado.stdout + resultado.stderr)


if __name__ == "__main__":
    unittest.main()
