import shutil
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from ferramentas import abrir_pasta_intimacao as rotina_pastas


class TesteAberturaPastaIntimacao(unittest.TestCase):
    def test_copia_caminho_se_pasta_nao_estiver_disponivel(self):
        caminho = Path("T:/Processos/IN99999999C")
        with (
            patch.object(rotina_pastas, "localizar_pasta_existente", return_value=None),
            patch.object(rotina_pastas, "caminho_pasta", return_value=caminho),
            patch.object(rotina_pastas, "copiar_caminho") as copiar,
            patch.object(rotina_pastas, "notificar") as notificar,
        ):
            resultado = rotina_pastas.abrir_pasta("IN99999999C")

        self.assertEqual(caminho, resultado)
        copiar.assert_called_once_with(caminho)
        notificar.assert_called_once()
        self.assertFalse(caminho.exists())

    def test_copia_caminho_se_o_explorer_nao_abrir(self):
        raiz = Path(__file__).parent / f".tmp_pasta_intimacao_{uuid4().hex}"
        raiz.mkdir()
        try:
            with (
                patch.object(rotina_pastas, "localizar_pasta_existente", return_value=raiz),
                patch.object(rotina_pastas.os, "startfile", side_effect=OSError("falha"), create=True),
                patch.object(rotina_pastas, "copiar_caminho") as copiar,
                patch.object(rotina_pastas, "notificar") as notificar,
            ):
                resultado = rotina_pastas.abrir_pasta("IN99999999C")

            self.assertEqual(raiz, resultado)
            copiar.assert_called_once_with(raiz)
            notificar.assert_called_once()
        finally:
            shutil.rmtree(raiz, ignore_errors=True)

    def test_instalador_nao_exige_pypdf_para_abrir_pastas(self):
        instalador = Path(__file__).parents[1] / "instalar_protocolo_aeri_intimacao.bat"
        conteudo = instalador.read_text(encoding="utf-8")

        self.assertIn("reg add", conteudo)
        self.assertNotIn("import pypdf", conteudo)


if __name__ == "__main__":
    unittest.main()
