import shutil
import unittest
import zipfile
from pathlib import Path
from uuid import uuid4

from ferramentas.abrir_pasta_intimacao import extrair_comando, localizar_pasta_existente
from ferramentas.nota_desistencia import (
    ASSINANTE_PENDENTE,
    DocumentoPdf,
    ErroNotaDesistencia,
    _extrair_assinantes_pdf,
    extrair_dados_nota,
    montar_paragrafos,
    preencher_modelo,
)


AUTUACAO = """
PROCESSO N.° 145885/2026
SAEC/ONR - IN01625860C
TÍTULO: Contrato de Aquisição de Terreno e Construção de Imóvel, Mútuo e
Alienação Fiduciária em Garantia - SFH n.º 8.4444.1508217-0, datado de 05/04/2017.
CREDORA FIDUCIÁRIA: CAIXA ECONÔMICA FEDERAL.
DEVEDOR(A)(ES) FIDUCIANTE(S): Micaelly Mariana Silva Rodrigues, (CPF: 041.714.191-23).
ENDEREÇO: RUA BV-01-A, n.º 124, Quadra 01, Lote 19-A, Bela Vista III,
com a área total de 126,75m², Morrinhos-GO, CEP: 75652-622.
AUTUAÇÃO
Aos 24 de junho de 2026, autuo os documentos, protocolado em 23 de junho de 2026
sob o n.º 184.361.
"""

INTIMACAO = """
SAEC/ONR IN01625860C. Venho intimar-lhe para fins de cumprimento das obrigações.
Contrato de financiamento registrado sob o R.02, na Matrícula n.º 30.167, deste Cartório.
"""

DESISTENCIA = """
Ofício nº 8991/2026 CESAV/BU
Bauru, 13 de julho de 2026
Na qualidade de credora do contrato de financiamento imobiliário nº 844441508217
solicitamos o cancelamento do processo de intimação de MICAELLY MARIANA SILVA
RODRIGUES, CPF: 041714191-23 por interesse desta credora CAIXA ECONÔMICA FEDERAL.
Matrícula do Imóvel: 30167
"""


def documentos(desistencia: str = DESISTENCIA) -> list[DocumentoPdf]:
    return [
        DocumentoPdf(Path("Autuação.pdf"), AUTUACAO),
        DocumentoPdf(Path("Intimação.pdf"), INTIMACAO),
        DocumentoPdf(Path("Recebido para Intimacao") / "Pedido de Desistência.pdf", desistencia),
    ]


class TesteNotaDesistencia(unittest.TestCase):
    def test_le_nome_declarado_na_assinatura_embutida(self):
        class LeitorAssinado:
            @staticmethod
            def get_fields():
                return {"assinatura": {"/FT": "/Sig", "/V": {"/Name": "Maria da Silva"}}}

        self.assertEqual(("Maria da Silva",), _extrair_assinantes_pdf(LeitorAssinado()))

    def test_extrai_comando_local_de_geracao(self):
        self.assertEqual(
            ("GERAR-DESISTENCIA", "IN01625860C"),
            extrair_comando("aeri-intimacao://gerar-desistencia/IN01625860C"),
        )

    def test_rejeita_acao_local_nao_autorizada(self):
        with self.assertRaises(ValueError):
            extrair_comando("aeri-intimacao://apagar/IN01625860C")

    def test_localiza_protocolo_movido_para_outra_fase(self):
        raiz = Path(__file__).parent / f".tmp_pasta_intimacao_{uuid4().hex}"
        pasta = raiz / "03 - Intimacao por Edital" / "IN99999999C"
        pasta.mkdir(parents=True)
        try:
            self.assertEqual(pasta.resolve(), localizar_pasta_existente("IN99999999C", [raiz]))
        finally:
            shutil.rmtree(raiz, ignore_errors=True)

    def test_extrai_e_cruza_dados_do_caso_real(self):
        dados = extrair_dados_nota(documentos(), "IN01625860C")

        self.assertEqual("184.361", dados.protocolo_ri)
        self.assertEqual("23.06.2026", dados.data_protocolo)
        self.assertEqual("30.167", dados.matricula)
        self.assertEqual("R.02", dados.ato_registro)
        self.assertEqual("8991/2026 CESAV/BU", dados.oficio_desistencia)
        self.assertEqual("13.07.2026", dados.data_desistencia)
        self.assertEqual("Micaelly Mariana Silva Rodrigues", dados.devedor)
        self.assertIn("CEP: 75.652-622", dados.endereco_imovel)
        self.assertEqual(ASSINANTE_PENDENTE, dados.assinante_desistencia)
        self.assertIn(ASSINANTE_PENDENTE, montar_paragrafos(dados)[1])

    def test_usa_nome_do_signatario_embutido_no_pdf(self):
        docs = documentos()
        docs[-1] = DocumentoPdf(docs[-1].caminho, docs[-1].texto, ("Maria da Silva",))

        dados = extrair_dados_nota(docs, "IN01625860C")

        self.assertEqual("Maria da Silva", dados.assinante_desistencia)
        self.assertIn("assinado eletronicamente por Maria da Silva", montar_paragrafos(dados)[1])

    def test_exige_pedido_nomeado_na_subpasta_correta(self):
        docs = documentos()
        docs[-1] = DocumentoPdf(Path("Pedido aleatório.pdf"), docs[-1].texto)

        with self.assertRaisesRegex(ErroNotaDesistencia, "Recebido para Intimacao"):
            extrair_dados_nota(docs, "IN01625860C")

    def test_clausula_generica_do_pedido_inicial_nao_e_desistencia(self):
        pedido_inicial = """
        Ofício do credor. Solicitamos o cancelamento de eventual procedimento de
        intimação cujo resultado tenha sido anteriormente averbado na matrícula.
        """
        with self.assertRaisesRegex(ErroNotaDesistencia, "pedido expresso"):
            extrair_dados_nota(documentos(pedido_inicial), "IN01625860C")

    def test_rejeita_desistencia_de_matricula_diferente(self):
        divergente = DESISTENCIA.replace("30167", "30168")
        with self.assertRaisesRegex(ErroNotaDesistencia, "diverge"):
            extrair_dados_nota(documentos(divergente), "IN01625860C")

    def test_preenche_somente_o_documento_xml_do_modelo(self):
        dados = extrair_dados_nota(documentos(), "IN01625860C")
        xml = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
        <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:body>
            <w:p><w:r><w:t>Iniciando o procedimento antigo.</w:t></w:r></w:p>
            <w:p><w:r><w:t>Texto da credora fiduciária com desistência do pedido em comento.</w:t></w:r></w:p>
          </w:body>
        </w:document>'''.encode("utf-8")
        raiz = Path(__file__).parent / f".tmp_nota_desistencia_{uuid4().hex}"
        raiz.mkdir()
        try:
            modelo = raiz / "modelo.docx"
            destino = raiz / "nota.docx"
            with zipfile.ZipFile(modelo, "w") as pacote:
                pacote.writestr("word/document.xml", xml)
                pacote.writestr("word/header1.xml", b"cabecalho-preservado")

            preencher_modelo(modelo, destino, dados)

            with zipfile.ZipFile(destino) as pacote:
                documento = pacote.read("word/document.xml").decode("utf-8")
                self.assertIn("IN01625860C", documento)
                self.assertIn("8991/2026 CESAV/BU", documento)
                self.assertEqual(b"cabecalho-preservado", pacote.read("word/header1.xml"))
        finally:
            shutil.rmtree(raiz, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
