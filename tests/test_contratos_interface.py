"""Inclui na suite Python/CI a regressao JS da interface de Contratos.

O arquivo .mjs existia mas nao era executado por ninguem: passava despercebido
em toda mudanca da tela.
"""
import shutil
import subprocess
import unittest
from pathlib import Path


class TesteInterfaceDeContratos(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node.js necessário para testar a interface")
    def test_regressoes_da_tela_de_contratos(self):
        raiz = Path(__file__).resolve().parents[1]
        resultado = subprocess.run(
            [shutil.which("node"), str(raiz / "tests/test_contratos_interface.mjs")],
            cwd=raiz, capture_output=True, text=True, encoding="utf-8", timeout=60,
        )
        self.assertEqual(resultado.returncode, 0, resultado.stdout + resultado.stderr)


if __name__ == "__main__":
    unittest.main()
