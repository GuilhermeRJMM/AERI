"""Inclui na suite Python/CI a regressao da area do imovel no MAPA-ONR."""
import shutil
import subprocess
import unittest
from pathlib import Path


class TesteAreaDoImovelMapaOnr(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node.js necessário para testar o extrator")
    def test_area_em_alqueires_convertidos(self):
        raiz = Path(__file__).resolve().parents[1]
        resultado = subprocess.run(
            [shutil.which("node"), str(raiz / "tests/test_mapa_onr_area.js")],
            cwd=raiz, capture_output=True, text=True, encoding="utf-8", timeout=30,
        )
        self.assertEqual(resultado.returncode, 0, resultado.stdout + resultado.stderr)


if __name__ == "__main__":
    unittest.main()
