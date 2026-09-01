"""Inclui na suite Python/CI a regressao de data e cadastro do acervo antigo."""
import shutil
import subprocess
import unittest
from pathlib import Path


class TesteExtracaoAcervoMapaOnr(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node.js necessário para testar o extrator")
    def test_data_do_ato_e_cadastro_rural(self):
        raiz = Path(__file__).resolve().parents[1]
        resultado = subprocess.run(
            [shutil.which("node"), str(raiz / "tests/test_mapa_onr_extracao_acervo.js")],
            cwd=raiz, capture_output=True, text=True, encoding="utf-8", timeout=30,
        )
        self.assertEqual(resultado.returncode, 0, resultado.stdout + resultado.stderr)


if __name__ == "__main__":
    unittest.main()
