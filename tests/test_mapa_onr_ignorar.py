"""Regressões da liberação excepcional do JSON, executadas também no CI."""
import shutil
import subprocess
import unittest
from pathlib import Path


class TesteIgnorarPendenciasMapaOnr(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node.js necessário")
    def test_exportacao_com_ressalvas(self):
        raiz = Path(__file__).resolve().parents[1]
        resultado = subprocess.run(
            [shutil.which("node"), str(raiz / "tests/test_mapa_onr_ignorar.js")],
            cwd=raiz, capture_output=True, text=True, encoding="utf-8", timeout=30,
        )
        self.assertEqual(resultado.returncode, 0, resultado.stdout + resultado.stderr)


if __name__ == "__main__":
    unittest.main()
