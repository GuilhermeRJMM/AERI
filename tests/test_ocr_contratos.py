"""O motor de OCR que não se instala precisa estar ao alcance do código.

O script do Windows.Media.Ocr é a dependência de runtime do pacote
contratos_nucleo, não um utilitário de operador: ele mora junto do código que o
executa. Já esteve em scripts/ com outro nome, e o efeito era silencioso --
motor() devolvia None, disponivel() era False e o sistema dizia que precisava
de OCR "não ativado", quando o motor estava no sistema operacional o tempo
todo. Só o Tesseract, que exige instalação, salvaria o caso.
"""
import sys
import unittest
from pathlib import Path

from backend.app.contratos_nucleo import ocr


class TesteMotorDeOcr(unittest.TestCase):
    def test_script_do_windows_esta_onde_o_codigo_procura(self):
        self.assertTrue(
            ocr.SCRIPT_WINDOWS.exists(),
            f"o script do OCR do Windows precisa estar em {ocr.SCRIPT_WINDOWS}",
        )

    def test_script_aceita_os_parametros_que_o_codigo_passa(self):
        fonte = ocr.SCRIPT_WINDOWS.read_text(encoding="utf-8", errors="replace")
        self.assertIn("$Pasta", fonte)
        self.assertIn("$Idioma", fonte)
        # O Python remove estes marcadores da saida; sem eles as paginas se
        # emendam e o rotulo da caixa seguinte gruda no texto da anterior.
        self.assertIn("@@PAGINA", fonte)

    def test_nao_ha_copia_orfa_do_script_em_scripts(self):
        raiz = Path(__file__).resolve().parents[1]
        orfaos = list((raiz / "scripts").glob("ocr_windows*.ps1"))
        self.assertEqual(orfaos, [], "duas cópias divergem; a que vale mora junto do código")

    @unittest.skipUnless(sys.platform == "win32", "o OCR local só existe no Windows")
    def test_no_windows_o_motor_padrao_dispensa_instalacao(self):
        # A ordem e por medicao, nao preferencia: o motor do Windows ganhou do
        # Tesseract em todas as configuracoes testadas (ver docstring de motor()).
        self.assertTrue(ocr.disponivel(), "com PowerShell e o script no lugar, tem de haver motor")
        self.assertEqual(ocr.motor(), "windows")

    def test_fora_do_windows_o_sistema_admite_que_nao_tem_motor(self):
        # Na Vercel nao ha OCR local: dizer que o contrato e digitalizado e
        # correto; fingir que leu seria pior.
        if sys.platform != "win32":
            self.assertIsNone(ocr.motor())
            self.assertFalse(ocr.disponivel())

    def test_correcao_recupera_os_rotulos_das_caixas(self):
        # Erros medidos no motor do Windows: "A1" -> "Al", "B10.1" -> "BIO.I".
        # Sao os mais caros, porque a extracao inteira ancora no rotulo.
        corrigido = ocr.corrige("Al - QUALIFICACAO DAS PARTES\nBIO.I - VALOR DO FINANCIAMENTO")
        self.assertIn("A1 - QUALIFICACAO", corrigido)
        self.assertIn("B10.1 - VALOR", corrigido)


if __name__ == "__main__":
    unittest.main()
