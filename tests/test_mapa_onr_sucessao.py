"""Inclui a regressão JavaScript do MAPA-ONR na suíte Python/CI."""
import shutil
import subprocess
import unittest
from pathlib import Path


class TesteSucessaoECibMapaOnr(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node.js necessário para testar o conversor")
    def test_fluxo_real_de_fichas_e_validacao_json(self):
        raiz = Path(__file__).resolve().parents[1]
        resultado = subprocess.run(
            [shutil.which("node"), str(raiz / "tests/test_mapa_onr_sucessao.js")],
            cwd=raiz, capture_output=True, text=True, encoding="utf-8", timeout=30,
        )
        self.assertEqual(resultado.returncode, 0, resultado.stdout + resultado.stderr)


if __name__ == "__main__":
    unittest.main()
