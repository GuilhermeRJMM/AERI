import shutil
import subprocess
import unittest
from pathlib import Path


class TesteBuscaTextoFrontend(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Node necessário para os handlers do frontend')
    def test_fluxo_de_geracao_e_copia(self):
        script = Path(__file__).with_name('test_buscas_texto.js')
        resultado = subprocess.run(['node', '--test', str(script)], capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(0, resultado.returncode, resultado.stdout + resultado.stderr)
