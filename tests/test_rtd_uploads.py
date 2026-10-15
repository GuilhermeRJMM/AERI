import io
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from backend.app.servicos.rtd_uploads import (
    ErroUploadRTD,
    MAX_UPLOAD_RTD,
    baixar_pdf_assinado,
)


class RespostaFake(io.BytesIO):
    def __init__(self, conteudo, headers=None):
        super().__init__(conteudo)
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


class TestLeituraUploadRTD(unittest.TestCase):
    URL = (
        "https://store_abc.private.blob.vercel-storage.com/"
        "rtd-intimacoes/temporarios/abc.pdf?token=temporario"
    )
    CAMINHO = "rtd-intimacoes/temporarios/abc.pdf"

    def test_baixa_pdf_assinado_do_caminho_autorizado(self):
        with patch("backend.app.servicos.rtd_uploads.build_opener") as criar_cliente:
            criar_cliente.return_value.open.return_value = RespostaFake(
                b"%PDF-documento",
                {"Content-Type": "application/pdf", "Content-Length": str(len(b"%PDF-documento"))},
            )
            self.assertEqual(baixar_pdf_assinado(self.URL, self.CAMINHO), b"%PDF-documento")

    def test_recusa_host_caminho_e_esquema_diferentes(self):
        urls_invalidas = (
            "http://store_abc.private.blob.vercel-storage.com/"
            "rtd-intimacoes/temporarios/abc.pdf?token=temporario",
            "https://evil.example/rtd-intimacoes/temporarios/abc.pdf?token=temporario",
            "https://store_abc.private.blob.vercel-storage.com/"
            "outro/arquivo.pdf?token=temporario",
            "https://usuario@store_abc.private.blob.vercel-storage.com/"
            "rtd-intimacoes/temporarios/abc.pdf?token=temporario",
        )
        for url in urls_invalidas:
            with self.subTest(url=url), self.assertRaises(ErroUploadRTD):
                baixar_pdf_assinado(url, self.CAMINHO)

    def test_recusa_conteudo_que_nao_e_pdf(self):
        with patch("backend.app.servicos.rtd_uploads.build_opener") as criar_cliente:
            criar_cliente.return_value.open.return_value = RespostaFake(
                b"<html>not pdf</html>", {"Content-Type": "text/html"}
            )
            with self.assertRaisesRegex(ErroUploadRTD, "não foi reconhecido como PDF"):
                baixar_pdf_assinado(self.URL, self.CAMINHO)

    def test_recusa_pdf_acima_de_25_mb_pelo_tamanho_declarado(self):
        with patch("backend.app.servicos.rtd_uploads.build_opener") as criar_cliente:
            criar_cliente.return_value.open.return_value = RespostaFake(
                b"%PDF-", {"Content-Type": "application/pdf", "Content-Length": str(MAX_UPLOAD_RTD + 1)}
            )
            with self.assertRaisesRegex(ErroUploadRTD, "25 MB"):
                baixar_pdf_assinado(self.URL, self.CAMINHO)

    def test_recusa_pdf_acima_de_25_mb_sem_content_length(self):
        with patch("backend.app.servicos.rtd_uploads.build_opener") as criar_cliente:
            criar_cliente.return_value.open.return_value = RespostaFake(
                b"%PDF" + b"x" * MAX_UPLOAD_RTD,
                {"Content-Type": "application/pdf"},
            )
            with self.assertRaisesRegex(ErroUploadRTD, "25 MB"):
                baixar_pdf_assinado(self.URL, self.CAMINHO)

    def test_nao_segue_redirecionamento_do_blob(self):
        erro = HTTPError(self.URL, 302, "redir", {}, None)
        with patch("backend.app.servicos.rtd_uploads.build_opener") as criar_cliente:
            criar_cliente.return_value.open.side_effect = erro
            with self.assertRaisesRegex(ErroUploadRTD, "possível acessar"):
                baixar_pdf_assinado(self.URL, self.CAMINHO)


if __name__ == "__main__":
    unittest.main()
