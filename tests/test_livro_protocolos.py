import unittest
from datetime import date
from pathlib import Path

from backend.app.servicos.livro_protocolos import (
    classificar_status,
    conferir_protocolo,
    extrair_protocolos_pdf,
)


def _protocolo_base(**sobrescritas) -> dict:
    base = {
        "protocolo": {"protocolo_numero": 185110, "descricao_titulo": "CÉDULA DE PRODUTO RURAL"},
        "itens_do_pedido": [
            {
                "natureza_formal_descricao": "Cédula de Produto Rural",
                "dados_imovel": {"tipo_registro": "M", "numero_registro": None},
                "atos_registrados": {
                    "ato_tipo": "R", "ato_numero": 1,
                    "texto": "R.01 - texto do ato completo. Selo: 123456. Total: R$100,00.",
                },
            },
        ],
    }
    base.update(sobrescritas)
    return base


class TesteClassificarStatus(unittest.TestCase):
    def test_reconhece_prenotado(self):
        self.assertEqual(classificar_status("185.200 FULANO 05/08/2026 Prenotado CÉDULA"), "PRENOTADO")

    def test_reconhece_registrado_por_referencia_de_ato(self):
        self.assertEqual(classificar_status("184.840 FULANO 20/07/2026 R.13 - 103 CONTRATO"), "REGISTRADO")

    def test_reconhece_sem_efeito(self):
        self.assertEqual(
            classificar_status("184.455 FULANO 26/06/2026 (Sem Efeito) ART.205, LEI 6.015/1973"),
            "SEM_EFEITO",
        )

    def test_referencia_de_ato_tem_prioridade_sobre_prenotado_residual(self):
        # Texto de uma linha vizinha pode vazar para o bloco (ex.: "Certifico
        # haver encerrado..." colado no fim do último Prenotado da seção);
        # uma referência de ato concreta não pode ser ofuscada por isso.
        self.assertEqual(
            classificar_status("184.840 FULANO 20/07/2026 R.13 - 103 CONTRATO Prenotado sobrou de outra linha"),
            "REGISTRADO",
        )

    def test_sem_evidencia_fica_indefinido(self):
        self.assertEqual(classificar_status("184.930 FULANO 23/07/2026 NOTIFICAÇÃO EXTRAJUDICIAL"), "INDEFINIDO")


class TesteExtrairProtocolosPdf(unittest.TestCase):
    def test_extrai_todas_as_linhas_do_livro_real(self):
        caminho_pdf = Path.home() / "Desktop" / "Livro de Protocolos 0508.pdf"
        if not caminho_pdf.exists():
            self.skipTest("PDF de exemplo não está disponível neste ambiente.")

        linhas = extrair_protocolos_pdf(caminho_pdf.read_bytes())

        self.assertEqual(len(linhas), 36)
        contagem = {}
        for item in linhas:
            contagem[item["status"]] = contagem.get(item["status"], 0) + 1
        self.assertEqual(contagem["REGISTRADO"], 22)
        self.assertEqual(contagem["PRENOTADO"], 12)
        self.assertEqual(contagem["SEM_EFEITO"], 1)
        self.assertEqual(contagem["INDEFINIDO"], 1)

    def test_numero_duplicado_mantem_a_ultima_ocorrencia(self):
        texto_prenotado = "185.203 FULANO DE TAL 05/08/2026 Prenotado CASAMENTO"
        texto_registrado = "185.203 FULANO DE TAL 05/08/2026 Av.12 - 103 CASAMENTO"
        # Monta um "PDF" mínimo válido cujo texto extraído contém as duas
        # ocorrências, replicando o padrão real do Livro de Protocolos.
        from pypdf import PdfWriter
        import io

        escritor = PdfWriter()
        pagina = escritor.add_blank_page(width=600, height=800)
        buffer = io.BytesIO()
        escritor.write(buffer)

        import backend.app.servicos.livro_protocolos as modulo

        texto_original = modulo.PdfReader

        class _LeitorFalso:
            def __init__(self, *_args, **_kwargs):
                self.pages = [_PaginaFalsa()]

        class _PaginaFalsa:
            def extract_text(self):
                return f"{texto_prenotado}\n{texto_registrado}"

        modulo.PdfReader = _LeitorFalso
        try:
            linhas = extrair_protocolos_pdf(b"qualquer coisa")
        finally:
            modulo.PdfReader = texto_original

        self.assertEqual(len(linhas), 1)
        self.assertEqual(linhas[0]["status"], "REGISTRADO")

    def test_pdf_sem_protocolos_leva_a_erro(self):
        import backend.app.servicos.livro_protocolos as modulo

        class _LeitorFalso:
            def __init__(self, *_args, **_kwargs):
                self.pages = [self]

            def extract_text(self):
                return "Nada aqui parece um protocolo."

        original = modulo.PdfReader
        modulo.PdfReader = _LeitorFalso
        try:
            with self.assertRaises(ValueError):
                extrair_protocolos_pdf(b"qualquer coisa")
        finally:
            modulo.PdfReader = original


class TesteConferirProtocolo(unittest.TestCase):
    def _item_registrado(self, **sobrescritas):
        item = {"numero": "185110", "status": "REGISTRADO", "data": "2026-08-06"}
        item.update(sobrescritas)
        return item

    def test_protocolo_correto_nao_gera_ocorrencias(self):
        ocorrencias = conferir_protocolo(
            self._item_registrado(), _protocolo_base(), data_esperada=date(2026, 8, 6),
        )
        self.assertEqual(ocorrencias, [])

    def test_descricao_titulo_em_branco_e_ocorrencia_grave(self):
        protocolo = _protocolo_base()
        protocolo["protocolo"]["descricao_titulo"] = ""
        ocorrencias = conferir_protocolo(self._item_registrado(), protocolo, date(2026, 8, 6))
        self.assertTrue(any(o["regra"] == "NATUREZA_TITULO" for o in ocorrencias))

    def test_primeiro_item_sem_natureza_formal_e_ocorrencia_grave(self):
        protocolo = _protocolo_base()
        protocolo["itens_do_pedido"][0]["natureza_formal_descricao"] = None
        ocorrencias = conferir_protocolo(self._item_registrado(), protocolo, date(2026, 8, 6))
        self.assertTrue(any(o["regra"] == "NATUREZA_TITULO" for o in ocorrencias))

    def test_busca_com_matricula_vinculada_e_ocorrencia_grave(self):
        protocolo = _protocolo_base(itens_do_pedido=[
            {
                "natureza_formal_descricao": "Busca",
                "dados_imovel": {"tipo_registro": "M", "numero_registro": 152},
                "atos_registrados": {"ato_tipo": None, "ato_numero": None, "texto": ""},
            },
        ])
        ocorrencias = conferir_protocolo(self._item_registrado(), protocolo, date(2026, 8, 6))
        self.assertEqual(len(ocorrencias), 1)
        self.assertEqual(ocorrencias[0]["regra"], "BUSCA_COM_MATRICULA")

    def test_busca_sem_matricula_nao_gera_ocorrencia(self):
        protocolo = _protocolo_base(itens_do_pedido=[
            {
                "natureza_formal_descricao": "Busca",
                "dados_imovel": {"tipo_registro": "M", "numero_registro": None},
                "atos_registrados": {"ato_tipo": None, "ato_numero": None, "texto": ""},
            },
        ])
        ocorrencias = conferir_protocolo(self._item_registrado(), protocolo, date(2026, 8, 6))
        self.assertEqual(ocorrencias, [])

    def test_ordem_numerica_fora_de_sequencia_e_ocorrencia_grave(self):
        protocolo = _protocolo_base(itens_do_pedido=[
            {"natureza_formal_descricao": "Registro", "dados_imovel": {},
             "atos_registrados": {"ato_tipo": "R", "ato_numero": 1, "texto": ""}},
            {"natureza_formal_descricao": "Averbação", "dados_imovel": {},
             "atos_registrados": {"ato_tipo": "A", "ato_numero": 3, "texto": ""}},
            {"natureza_formal_descricao": "Registro", "dados_imovel": {},
             "atos_registrados": {"ato_tipo": "R", "ato_numero": 2, "texto": ""}},
        ])
        ocorrencias = conferir_protocolo(self._item_registrado(), protocolo, date(2026, 8, 6))
        self.assertTrue(any(o["regra"] == "ORDEM_NUMERICA" for o in ocorrencias))

    def test_ordem_numerica_crescente_nao_gera_ocorrencia(self):
        protocolo = _protocolo_base(itens_do_pedido=[
            {"natureza_formal_descricao": "Registro", "dados_imovel": {},
             "atos_registrados": {"ato_tipo": "R", "ato_numero": 1, "texto": ""}},
            {"natureza_formal_descricao": "Registro", "dados_imovel": {},
             "atos_registrados": {"ato_tipo": "R", "ato_numero": 2, "texto": ""}},
            {"natureza_formal_descricao": "Averbação", "dados_imovel": {},
             "atos_registrados": {"ato_tipo": "A", "ato_numero": 3, "texto": ""}},
        ])
        ocorrencias = conferir_protocolo(self._item_registrado(), protocolo, date(2026, 8, 6))
        self.assertEqual(ocorrencias, [])

    def test_data_placeholder_xx_e_ocorrencia_grave(self):
        protocolo = _protocolo_base()
        protocolo["itens_do_pedido"][0]["atos_registrados"]["texto"] = "AV. 18-152 - Data: xx.07.2026. Texto do ato."
        ocorrencias = conferir_protocolo(self._item_registrado(), protocolo, date(2026, 8, 6))
        self.assertTrue(any(o["regra"] == "CAMPO_EM_BRANCO" and "xx" in o["descricao"] for o in ocorrencias))

    def test_fecho_em_branco_e_ocorrencia_grave(self):
        protocolo = _protocolo_base()
        protocolo["itens_do_pedido"][0]["atos_registrados"]["texto"] = (
            "Texto do ato. DOU FÉ. Morrinhos-GO, de de. Oficial: /mws/"
        )
        ocorrencias = conferir_protocolo(self._item_registrado(), protocolo, date(2026, 8, 6))
        self.assertTrue(any(o["regra"] == "CAMPO_EM_BRANCO" for o in ocorrencias))

    def test_valores_em_branco_geram_ocorrencia_de_atencao(self):
        protocolo = _protocolo_base()
        protocolo["itens_do_pedido"][0]["atos_registrados"]["texto"] = (
            "Texto do ato. Selo: . Cotação do ato: emolumentos: R$; ISSQN: R$; Total: R$."
        )
        ocorrencias = conferir_protocolo(self._item_registrado(), protocolo, date(2026, 8, 6))
        relevantes = [o for o in ocorrencias if o["regra"] == "CAMPO_EM_BRANCO"]
        self.assertTrue(relevantes)
        self.assertTrue(all(o["gravidade"] == "ATENCAO" for o in relevantes))

    def test_data_diferente_da_esperada_e_ocorrencia_grave(self):
        ocorrencias = conferir_protocolo(
            self._item_registrado(data="2026-08-05"), _protocolo_base(), data_esperada=date(2026, 8, 6),
        )
        self.assertTrue(any(o["regra"] == "DATA_DIVERGENTE" for o in ocorrencias))

    def test_data_nao_e_checada_para_protocolo_prenotado(self):
        item = self._item_registrado(status="PRENOTADO", data="2026-08-01")
        ocorrencias = conferir_protocolo(item, _protocolo_base(), data_esperada=date(2026, 8, 6))
        self.assertFalse(any(o["regra"] == "DATA_DIVERGENTE" for o in ocorrencias))


if __name__ == "__main__":
    unittest.main()
