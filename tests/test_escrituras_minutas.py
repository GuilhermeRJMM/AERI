import io
import unittest
import zipfile

from backend.app.servicos import escrituras


ESCRITURA = """
LIVRO DE ESCRITURA n.º 501, Folha n.º 33F/35F
ESCRITURA PÚBLICA DE VENDA E COMPRA QUE OUTORGA JOÃO
COMO VENDEDOR: JOÃO DA SILVA; E, COMO COMPRADORA: MARIA DE SOUZA, NA FORMA ABAIXO.
SAIBAM quantos este público instrumento virem que, aos dez dias (10/08/2026),
comparecem, como VENDEDOR: JOÃO DA SILVA, brasileiro, inscrito no CPF/MF sob o
n.º 040.125.571-90, residente em Morrinhos-GO; e, como COMPRADORA: MARIA DE
SOUZA, brasileira, inscrita no CPF/MF sob o n.º 655.979.151-34, residente em
Morrinhos-GO. Reconheço a identidade dos comparecentes.
Então, o VENDEDOR me declara: I)-OBJETO: que é proprietário do Lote n.º 11 da
Quadra 04, com área de 200,00m², situado na Rua Teste, CEP n.º 75.652-408;
II)-PROCEDÊNCIA/ORIGEM: que o imóvel é objeto da matrícula número 9.790, Livro 02.
4)- PREÇO E PAGAMENTO: R$ 160.000,00.
IMPOSTO SOBRE A TRANSMISSÃO DE BENS IMÓVEIS - ITBI: Base de Cálculo: R$ 160.000,00;
Recolhimento: 03/08/2026; Guia n.º 826/2026; Valor Recolhido: R$ 4.800,00.
"""


class TesteEscriturasMinutas(unittest.TestCase):
    def test_lista_somente_guias_itbi_do_protocolo(self):
        documentos = [
            {"ged_documento_id": 10, "tipo_documento": "Traslado", "descricao": "Escritura"},
            {"ged_documento_id": 11, "tipo_documento": "Guia", "descricao": "Guia de ITBI digital"},
            {"ged_documento_id": 12, "categoria": "ITBI", "descricao": "Documento fiscal"},
        ]
        itens = escrituras.documentos_itbi_disponiveis(documentos, exceto=12)
        self.assertEqual([i["ged_documento_id"] for i in itens], ["11"])

    def test_guia_itbi_incompleta_nao_inventa_dados_fiscais(self):
        documento = {"texto": """
            GUIA DE INFORMAÇÃO DO ITBI
            Matrícula n.º 39.547
            Valor do Negócio Jurídico: R$ 400.000,00
            Área total (ha/m²): 7,8183 ha
            Parte Ideal: 100%
        """, "sha256": "abc", "ocr": False}
        resultado = escrituras.extrair_guia_itbi(documento)
        self.assertEqual(resultado["conferencia"]["matricula"], "39.547")
        self.assertEqual(resultado["conferencia"]["valor_negocio"], "400.000,00")
        self.assertTrue(all(not valor for valor in resultado["campos"].values()))
        self.assertIn("base de cálculo", resultado["alertas"][0])

    def test_guia_itbi_completa_preenche_somente_campos_comprovados(self):
        documento = {"texto": """
            GUIA DE LANÇAMENTO E PAGAMENTO DO ITBI
            Matrícula n.º 39.547
            Guia n.º 458/2026
            Base de Cálculo: R$ 1.164.000,00
            DUAM n.º 1557714/0
            Valor Recolhido: R$ 34.920,00
            Data de Pagamento: 29/04/2026
        """, "sha256": "def", "ocr": False}
        resultado = escrituras.extrair_guia_itbi(documento)
        self.assertEqual(resultado["campos"], {
            "guia": "458/2026", "base_calculo": "1.164.000,00",
            "duam": "1557714/0", "valor_recolhido": "34.920,00",
            "data_quitacao": "29.04.2026",
        })
        payload = {
            "tipoDocumento": "ESCRITURA_PUBLICA",
            "ficha": {"matriculas": ["39547"], "valores": {"operacao": "1.164.000,00", "itbi": {}}},
        }
        escrituras.anexar_guia_itbi(payload, resultado, {
            "ged_documento_id": "88", "descricao": "Guia ITBI",
        })
        self.assertEqual(payload["ficha"]["valores"]["itbi"]["guia"], "458/2026")
        self.assertEqual(len(payload["documentosComplementares"]["itbiSelecionado"]["camposAplicados"]), 5)

    def test_guia_de_outra_matricula_e_recusada(self):
        payload = {
            "tipoDocumento": "ESCRITURA_PUBLICA",
            "ficha": {"matriculas": ["39547"], "valores": {"itbi": {}}},
        }
        resultado = {"campos": {}, "conferencia": {"matricula": "39.546"}}
        with self.assertRaisesRegex(ValueError, "não corresponde"):
            escrituras.anexar_guia_itbi(payload, resultado, {})

    def test_extrai_escritura_sem_misturar_documentos_das_partes(self):
        payload = escrituras.extrair({"texto": ESCRITURA, "ocr": False, "paginas": []})
        self.assertEqual(payload["tipoDocumento"], "ESCRITURA_PUBLICA")
        self.assertEqual(payload["especie"], "VENDA_COMPRA")
        self.assertEqual(payload["ficha"]["matriculas"], ["9790"])
        self.assertEqual(payload["ficha"]["transmitentes"]["documentos"], ["040.125.571-90"])
        self.assertEqual(payload["ficha"]["adquirentes"]["documentos"], ["655.979.151-34"])
        self.assertEqual(payload["ficha"]["imovel"]["cep"], "75.652-408")
        self.assertEqual(payload["ficha"]["titulo"]["livro"], "501")

    def test_modelo_tri7_e_enriquecimento_sao_separados_do_traslado(self):
        payload = escrituras.extrair({"texto": ESCRITURA, "ocr": False, "paginas": []})

        class Tri7:
            def buscar_minutas(self, **_):
                return [{"minuta_id": 505, "descricao": "VENDA E COMPRA - ESCRITURA 1º OFÍCIO"}]

            def buscar_texto_minuta(self, minuta_id):
                return {"minuta_id": minuta_id, "texto": "MODELO INSTITUCIONAL"}

        escrituras.enriquecer_modelo_tri7(payload, Tri7())
        self.assertEqual(payload["modeloTri7"]["minutaId"], 505)
        self.assertEqual(payload["modeloTri7"]["texto"], "MODELO INSTITUCIONAL")

    def test_minuta_de_venda_segue_padrao_e_nao_leva_email_da_escritura(self):
        payload = escrituras.extrair({
            "texto": ESCRITURA + " E-mail: pessoa@example.com", "ocr": False, "paginas": [],
        })
        payload["confronto"] = {"numero": "9790", "contexto": {}, "auxiliares": {}}
        texto = escrituras.gerar_minutas(payload)["principal"]["texto"]
        self.assertIn("Qualificacao•vendedor•i«a»", texto)
        self.assertIn("Qualificacao•proprietario•i«a»", texto)
        self.assertIn("Numero•ordem•prot«a»", texto)
        self.assertNotIn("@", texto)
        self.assertNotIn("E-mail", texto)

    def test_requerimento_combinado_e_docx_editavel(self):
        payload = escrituras.extrair({"texto": ESCRITURA, "ocr": False, "paginas": []})
        payload["ficha"]["imovel"]["cci"] = "123.456"
        payload["confronto"] = {"auxiliares": {"cep": True, "cci": True}}
        self.assertEqual(
            escrituras.requerimentos_disponiveis(payload),
            [{"tipo": "cep-cci", "rotulo": "Baixar requerimento de CEP e CCI"}],
        )
        nome, conteudo = escrituras.gerar_requerimento_docx(payload, "cep-cci")
        self.assertIn("CEP e CCI", nome)
        self.assertTrue(zipfile.is_zipfile(io.BytesIO(conteudo)))
        with zipfile.ZipFile(io.BytesIO(conteudo)) as pacote:
            xml = pacote.read("word/document.xml").decode("utf-8")
        self.assertIn("75.652-408", xml)
        self.assertIn("123.456", xml)

    def test_contrato_so_cancela_alienacao_com_autorizacao_e_onus_ativo(self):
        payload = {
            "documento": {"texto": "A credora AUTORIZA O CANCELAMENTO DA ALIENAÇÃO FIDUCIÁRIA."},
            "ficha": {"brutos": {"imovel": "Lote 1, CEP n.º 75.650-100"}},
            "confronto": {
                "exigencias": [{"titulo": "CEP não averbado"}],
                "analise": {"atos": [{"codigo": "R.05", "status": "ATIVO", "categoria": "ÔNUS", "tipo_onus": "ALIENAÇÃO FIDUCIÁRIA"}]},
            },
        }
        escrituras.preparar_auxiliares_contrato(payload)
        self.assertTrue(payload["confronto"]["auxiliares"]["cancelamento_alienacao"])
        self.assertTrue(payload["confronto"]["auxiliares"]["cep"])
        self.assertIn("cancelamento_alienacao", escrituras.gerar_minutas_auxiliares(payload))


if __name__ == "__main__":
    unittest.main()
