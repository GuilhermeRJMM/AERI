import unittest
from datetime import date
from pathlib import Path

from backend.app.servicos.livro_protocolos import (
    _regra_data_um_dia_antes,
    classificar_status,
    conferir_protocolo,
    extrair_protocolos_pdf,
    inferir_data_esperada,
    janelas_livro_protocolos,
    montar_protocolos_do_dia,
    normalizar_tema,
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


def _protocolo_185569(total_no_texto: str) -> dict:
    grupo = "00032608195900425430003"

    def item(natureza, total, ato_tipo=None, ato_numero=None, data_selo=None):
        return {
            "natureza_formal_descricao": natureza,
            "dados_imovel": (
                {"tipo_registro": "M", "numero_registro": 5292}
                if ato_tipo else {}
            ),
            "atos_registrados": {
                "ato_tipo": ato_tipo,
                "ato_numero": ato_numero,
                "texto": "",
            },
            "detalhes_emolumentos": {"total_do_item": total},
            "selos": [{"selo_agrupador": grupo, "data": data_selo}],
        }

    return {
        "protocolo": {
            "protocolo_numero": 185569,
            "descricao_titulo": "ESCRITURA PÚBLICA DE VENDA E COMPRA",
        },
        "itens_do_pedido": [
            item("Venda e Compra Imóvel Urbano (Simples)", 4447.53, "R", 11, "2026-08-25T15:32:51"),
            item("Prenotação", 35.01, data_selo="2026-08-20T09:12:04"),
            item("Busca", 23.99, data_selo="2026-08-25T15:32:52"),
            item("Código de Endereçamento Postal - CEP", 0.0, "A", 10, "2026-08-25T15:32:45"),
        ],
        "_texto_matricula": (
            "AV.10-5.292 CEP. Total: R$0.\n"
            f"R.11-5.292 VENDA E COMPRA. Total: R${total_no_texto}."
        ),
    }


def _protocolo_185546() -> dict:
    grupo = "00032608195500000000001"

    def item(natureza, tipo, numero, total, ato_tipo=None, ato_numero=None):
        return {
            "natureza_formal_descricao": natureza,
            "dados_imovel": {"tipo_registro": tipo, "numero_registro": numero},
            "atos_registrados": {"ato_tipo": ato_tipo, "ato_numero": ato_numero, "texto": ""},
            "detalhes_emolumentos": {"total_do_item": total},
            "selos": [{"selo_agrupador": grupo}],
        }

    return {
        "protocolo": {"protocolo_numero": 185546, "descricao_titulo": "CÉDULA DE CRÉDITO BANCÁRIO"},
        "itens_do_pedido": [
            item("Prenotação de Cédula", None, None, 35.01),
            item("Busca de Cédula", None, None, 23.99),
            item("Cédula de Crédito Bancário - Crédito Rural (Alienação)", "M", 32463, 1016.29, "R", 17),
            item("Cédula de Crédito Bancário - Crédito Rural (Penhor)", "A", 29569, 455.73, "S", 0),
            item("Penhor Rural/Imóvel de Localização", "M", 32463, 0, "A", 16),
        ],
    }


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


class TesteInferirDataEsperada(unittest.TestCase):
    def test_usa_a_data_mais_frequente_entre_os_registrados(self):
        linhas = [
            {"status": "REGISTRADO", "data": "2026-08-05"},
            {"status": "REGISTRADO", "data": "2026-08-05"},
            {"status": "REGISTRADO", "data": "2026-08-04"},
            {"status": "PRENOTADO", "data": None},
        ]
        self.assertEqual(inferir_data_esperada(linhas), date(2026, 8, 5))

    def test_ignora_prenotados_e_sem_efeito_na_inferencia(self):
        linhas = [
            {"status": "REGISTRADO", "data": "2026-08-05"},
            {"status": "PRENOTADO", "data": "2026-08-06"},
            {"status": "SEM_EFEITO", "data": "2026-08-06"},
        ]
        self.assertEqual(inferir_data_esperada(linhas), date(2026, 8, 5))

    def test_retorna_none_sem_nenhum_registrado_com_data(self):
        linhas = [{"status": "PRENOTADO", "data": None}]
        self.assertIsNone(inferir_data_esperada(linhas))

    def test_funciona_apos_fim_de_semana_quando_ontem_seria_domingo(self):
        # Caso que quebrava antes: folha de sexta-feira conferida na
        # segunda. "Hoje - 1 dia" cairia num domingo (sem expediente) e
        # todo REGISTRADO seria sinalizado como DATA_DIVERGENTE à toa.
        linhas = [
            {"status": "REGISTRADO", "data": "2026-08-07"},  # sexta-feira
            {"status": "REGISTRADO", "data": "2026-08-07"},
        ]
        self.assertEqual(inferir_data_esperada(linhas), date(2026, 8, 7))


class TesteLivroProtocolosPorData(unittest.TestCase):
    def test_divide_noventa_dias_em_tres_consultas_sem_sobreposicao(self):
        janelas = janelas_livro_protocolos(date(2026, 8, 25))

        self.assertEqual(janelas, [
            (date(2026, 7, 27), date(2026, 8, 25)),
            (date(2026, 6, 27), date(2026, 7, 26)),
            (date(2026, 5, 28), date(2026, 6, 26)),
        ])

    def test_reune_apresentados_e_registrados_com_registro_prevalecendo(self):
        respostas = [{"protocolos": [
            {
                "protocolo": 185646,
                "data_apresentacao": "2026-08-25T08:00:00",
                "data_registro": None,
                "apresentante": "DAVI SILVA VELOSO",
                "itens": [{"natureza": "VENDA E COMPRA"}],
            },
            {
                "protocolo": 185659,
                "data_apresentacao": "2026-08-25T09:00:00",
                "data_registro": "2026-08-25T16:00:00",
                "apresentante": "LAZARO ROBERTO DA SILVA",
                "itens": [{"natureza": "CEP"}],
            },
            {
                "protocolo": 185569,
                "data_apresentacao": "2026-08-20T09:12:03.825000",
                "data_registro": "2026-08-25T15:32:53.134000",
                "apresentante": "RODRIGO FERREIRA BORGES",
                "itens": [{"natureza": "VENDA E COMPRA"}],
            },
            {
                "protocolo": 185647,
                "data_apresentacao": "2026-08-24T09:00:00",
                "data_registro": "2026-08-26T09:00:00",
                "apresentante": "FORA DO DIA",
                "itens": [],
            },
        ]}]

        itens = montar_protocolos_do_dia(respostas, date(2026, 8, 25))

        self.assertEqual([item["numero"] for item in itens], ["185646", "185659", "185569"])
        self.assertEqual([item["status"] for item in itens], ["PRENOTADO", "REGISTRADO", "REGISTRADO"])
        self.assertEqual(itens[1]["origemDia"], "APRESENTADO_E_REGISTRADO")
        self.assertEqual(itens[2]["origemDia"], "REGISTRADO")

    def test_remove_protocolo_repetido_entre_as_janelas(self):
        item = {
            "protocolo": 185569,
            "data_apresentacao": "2026-08-20T09:12:03",
            "data_registro": "2026-08-25T15:32:53",
            "apresentante": "RODRIGO",
            "itens": [],
        }
        resultado = montar_protocolos_do_dia(
            [{"protocolos": [item]}, {"protocolos": [dict(item)]}],
            date(2026, 8, 25),
        )
        self.assertEqual(len(resultado), 1)


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

    def test_total_do_ato_principal_considera_itens_do_mesmo_agrupamento(self):
        protocolo = _protocolo_185569("4.506,53")
        texto = protocolo.pop("_texto_matricula")
        ocorrencias = conferir_protocolo(
            self._item_registrado(), protocolo, date(2026, 8, 25),
            textos_registros={("M", 5292): texto},
        )
        self.assertFalse(any(o["regra"] == "TOTAL_CUSTAS_DIVERGENTE" for o in ocorrencias))
        self.assertFalse(any(o["regra"] == "ORDEM_OPERACIONAL" for o in ocorrencias))

    def test_total_que_ignora_prenotacao_e_busca_e_divergente(self):
        protocolo = _protocolo_185569("4.447,53")
        texto = protocolo.pop("_texto_matricula")
        ocorrencias = conferir_protocolo(
            self._item_registrado(), protocolo, date(2026, 8, 25),
            textos_registros={("M", 5292): texto},
        )
        relevantes = [o for o in ocorrencias if o["regra"] == "TOTAL_CUSTAS_DIVERGENTE"]
        self.assertEqual(len(relevantes), 1)
        self.assertEqual(relevantes[0]["gravidade"], "GRAVE")
        self.assertIn("4.447,53", relevantes[0]["descricao"])
        self.assertIn("4.506,53", relevantes[0]["descricao"])

    def test_dois_atos_onerosos_no_mesmo_grupo_nao_geram_falso_positivo(self):
        protocolo = _protocolo_185569("4.506,53")
        texto = protocolo.pop("_texto_matricula")
        protocolo["itens_do_pedido"][3]["detalhes_emolumentos"]["total_do_item"] = 10.0
        ocorrencias = conferir_protocolo(
            self._item_registrado(), protocolo, date(2026, 8, 25),
            textos_registros={("M", 5292): texto},
        )
        self.assertFalse(any(o["regra"] == "TOTAL_CUSTAS_DIVERGENTE" for o in ocorrencias))

    def test_total_soma_matricula_e_registro_auxiliar_do_mesmo_protocolo(self):
        protocolo = _protocolo_185546()
        textos = {
            ("M", 32463): "AV.16-32.463 PENHOR. Total: R$0.\nR.17-32.463 CÉDULA. Total: R$1.075,29.",
            ("A", 29569): "REGISTRO AUXILIAR 29.569. CÉDULA. Total: R$455,73.",
        }

        ocorrencias = conferir_protocolo(
            self._item_registrado(), protocolo, date(2026, 8, 19), textos_registros=textos,
        )

        self.assertFalse(any(o["regra"] == "TOTAL_CUSTAS_DIVERGENTE" for o in ocorrencias))

    def test_total_alerta_quando_soma_das_duas_saidas_realmente_diverge(self):
        protocolo = _protocolo_185546()
        textos = {
            ("M", 32463): "R.17-32.463 CÉDULA. Total: R$1.075,29.",
            ("A", 29569): "REGISTRO AUXILIAR 29.569. CÉDULA. Total: R$455,72.",
        }

        ocorrencias = conferir_protocolo(
            self._item_registrado(), protocolo, date(2026, 8, 19), textos_registros=textos,
        )
        relevantes = [o for o in ocorrencias if o["regra"] == "TOTAL_CUSTAS_DIVERGENTE"]

        self.assertEqual(len(relevantes), 1)
        self.assertIn("R.17 e Registro Auxiliar 29.569", relevantes[0]["descricao"])
        self.assertIn("1.531,01", relevantes[0]["descricao"])
        self.assertIn("1.531,02", relevantes[0]["descricao"])

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

    def test_preposicao_diferente_nao_gera_ocorrencia(self):
        # Caso relatado: "Dados do Título" = "Designação Cadastral DO
        # Imóvel" e "Natureza Formal" = "Designação Cadastral DE Imóvel" —
        # mesmo ato, só a preposição muda entre as duas fontes (texto livre
        # do protocolo vs. catálogo padronizado da Tri7). Antes, a
        # comparação por substring exato não considerava isso relacionado.
        protocolo = _protocolo_base(
            protocolo={"protocolo_numero": 185300, "descricao_titulo": "Designação Cadastral do Imóvel"},
            itens_do_pedido=[{
                "natureza_formal_descricao": "Designação Cadastral de Imóvel",
                "dados_imovel": {}, "atos_registrados": {"ato_tipo": "A", "ato_numero": 5, "texto": ""},
            }],
        )
        ocorrencias = conferir_protocolo(self._item_registrado(), protocolo, date(2026, 8, 6))
        self.assertFalse(any(o["regra"] == "NATUREZA_TITULO" for o in ocorrencias))

    def test_prenotacao_como_primeiro_item_do_array_e_ignorada(self):
        # Caso relatado: protocolo 185.203, título "CASAMENTO". Visualmente
        # Casamento é o item 1 do pedido, mas a API devolve Prenotação
        # primeiro no array (ela acontece antes, cronologicamente).
        # itens_do_pedido[0] literal seria Prenotação -- que nunca bate com
        # nenhum título -- gerando ocorrência a toa num protocolo correto.
        protocolo = _protocolo_base(
            protocolo={"protocolo_numero": 185203, "descricao_titulo": "CASAMENTO"},
            itens_do_pedido=[
                {"natureza_formal_descricao": "Prenotação", "dados_imovel": {},
                 "atos_registrados": {"ato_tipo": None, "ato_numero": None, "texto": ""}},
                {"natureza_formal_descricao": "Busca", "dados_imovel": {},
                 "atos_registrados": {"ato_tipo": None, "ato_numero": None, "texto": ""}},
                {"natureza_formal_descricao": "Casamento", "dados_imovel": {},
                 "atos_registrados": {"ato_tipo": "A", "ato_numero": 1, "texto": ""}},
            ],
        )
        ocorrencias = conferir_protocolo(self._item_registrado(), protocolo, date(2026, 8, 6))
        self.assertFalse(any(o["regra"] == "NATUREZA_TITULO" for o in ocorrencias))

    def test_ordem_das_palavras_diferente_nao_gera_ocorrencia(self):
        # As mesmas palavras em ordem diferente entre as duas fontes (título
        # em texto livre vs. natureza do catálogo padronizado) descrevem o
        # mesmo ato — comparação por substring exato não reconhecia isso
        # porque exige a mesma sequência, não só as mesmas palavras.
        protocolo = _protocolo_base(
            protocolo={
                "protocolo_numero": 185400,
                "descricao_titulo": "Retificação de Área e Confrontações",
            },
            itens_do_pedido=[{
                "natureza_formal_descricao": "Confrontações e Área - Retificação",
                "dados_imovel": {}, "atos_registrados": {"ato_tipo": "A", "ato_numero": 7, "texto": ""},
            }],
        )
        ocorrencias = conferir_protocolo(self._item_registrado(), protocolo, date(2026, 8, 6))
        self.assertFalse(any(o["regra"] == "NATUREZA_TITULO" for o in ocorrencias))

    def test_natureza_contida_no_titulo_completo_nao_gera_ocorrencia(self):
        # Caso real: o instrumento (Dados do Título) é o nome completo da
        # escritura, que contém a natureza formal do 1º item como parte do
        # texto.
        protocolo = _protocolo_base(
            protocolo={
                "protocolo_numero": 185110,
                "descricao_titulo": (
                    "ESCRITURA PÚBLICA DE CONFISSÃO DE DÍVIDA, TRANSAÇÃO E DAÇÃO EM PAGAMENTO"
                ),
            },
            itens_do_pedido=[
                {
                    "natureza_formal_descricao": "Dação em Pagamento",
                    "dados_imovel": {}, "atos_registrados": {"ato_tipo": "R", "ato_numero": 19, "texto": ""},
                },
            ],
        )
        ocorrencias = conferir_protocolo(self._item_registrado(), protocolo, date(2026, 8, 6))
        self.assertFalse(any(o["regra"] == "NATUREZA_TITULO" for o in ocorrencias))

    def test_natureza_sem_relacao_com_o_titulo_e_ocorrencia_de_atencao(self):
        # Caso relatado: protocolo com "Dados do Título" = Georreferenciamento
        # mas a Natureza Formal registrada no item foi Código de
        # Endereçamento Postal (CEP) -- não têm nada a ver um com o outro.
        # Gravidade ATENCAO (não GRAVE): essa regra é julgamento por texto
        # com falso positivo conhecido (PMCMV/SFH), não tão confiável quanto
        # uma checagem objetiva de campo em branco.
        protocolo = _protocolo_base(
            protocolo={"protocolo_numero": 185021, "descricao_titulo": "GEORREFERENCIAMENTO"},
            itens_do_pedido=[
                {
                    "natureza_formal_descricao": "Código de Endereçamento Postal - CEP",
                    "dados_imovel": {}, "atos_registrados": {"ato_tipo": "A", "ato_numero": 31, "texto": ""},
                },
            ],
        )
        ocorrencias = conferir_protocolo(self._item_registrado(), protocolo, date(2026, 8, 6))
        relevantes = [o for o in ocorrencias if o["regra"] == "NATUREZA_TITULO"]
        self.assertEqual(len(relevantes), 1)
        self.assertEqual(relevantes[0]["gravidade"], "ATENCAO")
        self.assertIn("GEORREFERENCIAMENTO", relevantes[0]["descricao"])
        self.assertIn("Código de Endereçamento Postal", relevantes[0]["descricao"])
        self.assertEqual(relevantes[0]["tituloOriginal"], "GEORREFERENCIAMENTO")
        self.assertEqual(relevantes[0]["naturezaOriginal"], "Código de Endereçamento Postal - CEP")

    def test_protocolo_185366_sugere_venda_e_compra_em_vez_de_cep(self):
        protocolo = _protocolo_base(
            protocolo={"protocolo_numero": 185366, "descricao_titulo": "INSCRIÇÃO NO CAR"},
            itens_do_pedido=[
                {
                    "natureza_formal_descricao": "Código de Endereçamento Postal - CEP",
                    "dados_imovel": {"tipo_registro": "M", "numero_registro": 38687},
                    "atos_registrados": {"ato_tipo": "A", "ato_numero": 8, "texto": ""},
                },
                {
                    "natureza_formal_descricao": "Venda e Compra Imóvel Urbano (Simples)",
                    "dados_imovel": {"tipo_registro": "M", "numero_registro": 38687},
                    "atos_registrados": {"ato_tipo": "R", "ato_numero": 9, "texto": ""},
                },
            ],
        )

        ocorrencias = conferir_protocolo(self._item_registrado(), protocolo, date(2026, 8, 24))
        relevantes = [o for o in ocorrencias if o["regra"] == "NATUREZA_TITULO"]

        self.assertEqual(len(relevantes), 1)
        self.assertEqual(relevantes[0]["naturezaOriginal"], "Venda e Compra Imóvel Urbano (Simples)")
        self.assertNotIn("Código de Endereçamento Postal", relevantes[0]["descricao"])

    def test_cancelamento_nao_e_confundido_com_constituicao_do_mesmo_direito(self):
        protocolo = _protocolo_base(
            protocolo={"protocolo_numero": 185500, "descricao_titulo": "ALIENAÇÃO FIDUCIÁRIA"},
            itens_do_pedido=[{
                "natureza_formal_descricao": "Cancelamento de Alienação Fiduciária",
                "dados_imovel": {}, "atos_registrados": {"ato_tipo": "A", "ato_numero": 7, "texto": ""},
            }],
        )
        ocorrencias = conferir_protocolo(self._item_registrado(), protocolo, date(2026, 8, 6))
        self.assertTrue(any(o["regra"] == "NATUREZA_TITULO" for o in ocorrencias))

    def test_retificacao_de_area_nao_bate_com_retificacao_de_cpf(self):
        protocolo = _protocolo_base(
            protocolo={"protocolo_numero": 185501, "descricao_titulo": "RETIFICAÇÃO DE ÁREA"},
            itens_do_pedido=[{
                "natureza_formal_descricao": "Retificação de CPF",
                "dados_imovel": {}, "atos_registrados": {"ato_tipo": "A", "ato_numero": 7, "texto": ""},
            }],
        )
        ocorrencias = conferir_protocolo(self._item_registrado(), protocolo, date(2026, 8, 6))
        self.assertTrue(any(o["regra"] == "NATUREZA_TITULO" for o in ocorrencias))

    def test_excecao_confirmada_suprime_a_ocorrencia(self):
        # Quando dois nomes realmente não compartilham tema textual, somente
        # uma equivalência exata confirmada por administrador pode suprimir.
        protocolo = _protocolo_base(
            protocolo={
                "protocolo_numero": 184840,
                "descricao_titulo": "ESCRITURA PÚBLICA DE CONFISSÃO DE DÍVIDA",
            },
            itens_do_pedido=[{
                "natureza_formal_descricao": "Dação em Pagamento",
                "dados_imovel": {}, "atos_registrados": {"ato_tipo": "R", "ato_numero": 13, "texto": ""},
            }],
        )
        titulo_tema = normalizar_tema("ESCRITURA PÚBLICA DE CONFISSÃO DE DÍVIDA")
        natureza_tema = normalizar_tema("Dação em Pagamento")

        sem_excecao = conferir_protocolo(self._item_registrado(), protocolo, date(2026, 8, 6))
        self.assertTrue(any(o["regra"] == "NATUREZA_TITULO" for o in sem_excecao))

        com_excecao = conferir_protocolo(
            self._item_registrado(), protocolo, date(2026, 8, 6),
            excecoes_natureza_titulo=frozenset({(titulo_tema, natureza_tema)}),
        )
        self.assertFalse(any(o["regra"] == "NATUREZA_TITULO" for o in com_excecao))

    def test_excecao_de_outro_par_nao_suprime_ocorrencia_diferente(self):
        protocolo = _protocolo_base(
            protocolo={"protocolo_numero": 185021, "descricao_titulo": "GEORREFERENCIAMENTO"},
            itens_do_pedido=[{
                "natureza_formal_descricao": "Código de Endereçamento Postal - CEP",
                "dados_imovel": {}, "atos_registrados": {"ato_tipo": "A", "ato_numero": 31, "texto": ""},
            }],
        )
        excecao_de_outro_caso = frozenset({(normalizar_tema("OUTRO TITULO"), normalizar_tema("OUTRA NATUREZA"))})
        ocorrencias = conferir_protocolo(
            self._item_registrado(), protocolo, date(2026, 8, 6),
            excecoes_natureza_titulo=excecao_de_outro_caso,
        )
        self.assertTrue(any(o["regra"] == "NATUREZA_TITULO" for o in ocorrencias))

    def test_excecao_antiga_de_cep_nao_suprime_ocorrencia(self):
        titulo = "GEORREFERENCIAMENTO"
        natureza = "Código de Endereçamento Postal - CEP"
        protocolo = _protocolo_base(
            protocolo={"protocolo_numero": 185021, "descricao_titulo": titulo},
            itens_do_pedido=[{
                "natureza_formal_descricao": natureza,
                "dados_imovel": {}, "atos_registrados": {"ato_tipo": "A", "ato_numero": 31, "texto": ""},
            }],
        )
        ocorrencias = conferir_protocolo(
            self._item_registrado(), protocolo, date(2026, 8, 6),
            excecoes_natureza_titulo=frozenset({(normalizar_tema(titulo), normalizar_tema(natureza))}),
        )
        self.assertTrue(any(o["regra"] == "NATUREZA_TITULO" for o in ocorrencias))

    def test_so_o_primeiro_item_e_conferido_contra_o_titulo(self):
        # Regressão: um protocolo real tinha 3 itens com ato de verdade (CEP,
        # Dação em Pagamento, Cancelamento de Alienação Fiduciária) sob a
        # mesma escritura -- checar todos os itens gerava ocorrência à toa
        # nos itens que legitimamente não precisam bater com o título (CEP,
        # cancelamentos etc. que acompanham o ato principal). Só o item em 1ª
        # posição é conferido.
        protocolo = _protocolo_base(
            protocolo={
                "protocolo_numero": 185256,
                "descricao_titulo": (
                    "ESCRITURA PÚBLICA DE CONFISSÃO DE DÍVIDA, TRANSAÇÃO E DAÇÃO EM PAGAMENTO"
                ),
            },
            itens_do_pedido=[
                {"natureza_formal_descricao": "Dação em Pagamento", "dados_imovel": {},
                 "atos_registrados": {"ato_tipo": "R", "ato_numero": 19, "texto": ""}},
                {"natureza_formal_descricao": "Código de Endereçamento Postal - CEP", "dados_imovel": {},
                 "atos_registrados": {"ato_tipo": "A", "ato_numero": 18, "texto": ""}},
                {"natureza_formal_descricao": "Cancelamento de Alienação Fiduciária", "dados_imovel": {},
                 "atos_registrados": {"ato_tipo": "A", "ato_numero": 20, "texto": ""}},
            ],
        )
        ocorrencias = conferir_protocolo(self._item_registrado(), protocolo, date(2026, 8, 6))
        self.assertFalse(any(o["regra"] == "NATUREZA_TITULO" for o in ocorrencias))

    def test_protocolo_184994_encontra_venda_e_compra_mesmo_com_cep_antes_na_api(self):
        protocolo = _protocolo_base(
            protocolo={"protocolo_numero": 184994, "descricao_titulo": "ESCRITURA PÚBLICA DE VENDA E COMPRA"},
            itens_do_pedido=[
                {"natureza_formal_descricao": "Código de Endereçamento Postal - CEP",
                 "dados_imovel": {"tipo_registro": "M", "numero_registro": 34712},
                 "atos_registrados": {"ato_tipo": "A", "ato_numero": 6, "texto": ""}},
                {"natureza_formal_descricao": "Cancelamento de Alienação Fiduciária",
                 "dados_imovel": {"tipo_registro": "M", "numero_registro": 34712},
                 "atos_registrados": {"ato_tipo": "A", "ato_numero": 7, "texto": ""}},
                {"natureza_formal_descricao": "Venda e Compra Imóvel Urbano (Simples)",
                 "dados_imovel": {"tipo_registro": "M", "numero_registro": 34712},
                 "atos_registrados": {"ato_tipo": "R", "ato_numero": 8, "texto": ""}},
            ],
        )
        texto = "AV.06-34.712 CEP\nAV.07-34.712 CANCELAMENTO\nR.08-34.712 VENDA E COMPRA"
        ocorrencias = conferir_protocolo(
            self._item_registrado(), protocolo, date(2026, 8, 6),
            textos_registros={("M", 34712): texto},
        )
        self.assertFalse(any(o["regra"] == "NATUREZA_TITULO" for o in ocorrencias))
        self.assertFalse(any(o["regra"] == "ORDEM_OPERACIONAL" for o in ocorrencias))

    def _itens_com_busca(self, numero_registro):
        return [
            {
                "natureza_formal_descricao": "Cédula de Produto Rural",
                "dados_imovel": {}, "atos_registrados": {"ato_tipo": "R", "ato_numero": 1, "texto": ""},
            },
            {
                "natureza_formal_descricao": "Busca",
                "dados_imovel": {"tipo_registro": "M", "numero_registro": numero_registro},
                "atos_registrados": {"ato_tipo": None, "ato_numero": None, "texto": ""},
            },
        ]

    def test_busca_com_matricula_vinculada_e_ocorrencia_grave(self):
        protocolo = _protocolo_base(itens_do_pedido=self._itens_com_busca(152))
        ocorrencias = conferir_protocolo(self._item_registrado(), protocolo, date(2026, 8, 6))
        self.assertEqual(len(ocorrencias), 1)
        self.assertEqual(ocorrencias[0]["regra"], "BUSCA_COM_MATRICULA")

    def test_busca_sem_matricula_nao_gera_ocorrencia(self):
        protocolo = _protocolo_base(itens_do_pedido=self._itens_com_busca(None))
        ocorrencias = conferir_protocolo(self._item_registrado(), protocolo, date(2026, 8, 6))
        self.assertEqual(ocorrencias, [])

    def test_variante_de_busca_com_matricula_tambem_e_detectada(self):
        # "Busca Simples"/"Busca de Bens" etc. escapavam da checagem antes,
        # que exigia o texto exato "Busca" (igualdade, não substring).
        itens = self._itens_com_busca(152)
        itens[1]["natureza_formal_descricao"] = "Busca Simples"
        protocolo = _protocolo_base(itens_do_pedido=itens)
        ocorrencias = conferir_protocolo(self._item_registrado(), protocolo, date(2026, 8, 6))
        self.assertTrue(any(o["regra"] == "BUSCA_COM_MATRICULA" for o in ocorrencias))

    def test_ordem_do_array_nao_e_usada_como_ordem_registral(self):
        imovel = {"tipo_registro": "M", "numero_registro": 152}
        protocolo = _protocolo_base(itens_do_pedido=[
            {"natureza_formal_descricao": "Registro", "dados_imovel": imovel,
             "atos_registrados": {"ato_tipo": "R", "ato_numero": 1, "texto": ""}},
            {"natureza_formal_descricao": "Averbação", "dados_imovel": imovel,
             "atos_registrados": {"ato_tipo": "A", "ato_numero": 3, "texto": ""}},
            {"natureza_formal_descricao": "Registro", "dados_imovel": imovel,
             "atos_registrados": {"ato_tipo": "R", "ato_numero": 2, "texto": ""}},
        ])
        ocorrencias = conferir_protocolo(
            self._item_registrado(), protocolo, date(2026, 8, 6),
            textos_registros={("M", 152): "R.01-152 texto\nAV.03-152 texto\nR.02-152 texto"},
        )
        self.assertFalse(any(o["regra"] == "ORDEM_OPERACIONAL" for o in ocorrencias))

    def test_atualizacoes_anteriores_ao_ato_principal_nao_dependem_da_ordem_do_json(self):
        imovel = {"tipo_registro": "M", "numero_registro": 34712}
        protocolo = _protocolo_base(
            protocolo={
                "protocolo_numero": 184994,
                "descricao_titulo": "ESCRITURA PÚBLICA DE VENDA E COMPRA",
            },
            itens_do_pedido=[
                {"natureza_formal_descricao": "Código de Endereçamento Postal - CEP",
                 "dados_imovel": imovel,
                 "atos_registrados": {"ato_tipo": "A", "ato_numero": 6, "texto": ""}},
                {"natureza_formal_descricao": "Venda e Compra Imóvel Urbano (Simples)",
                 "dados_imovel": imovel,
                 "atos_registrados": {"ato_tipo": "R", "ato_numero": 8, "texto": ""}},
                {"natureza_formal_descricao": "Cancelamento de Alienação Fiduciária",
                 "dados_imovel": imovel,
                 "atos_registrados": {"ato_tipo": "A", "ato_numero": 7, "texto": ""}},
            ],
        )
        ocorrencias = conferir_protocolo(
            self._item_registrado(), protocolo, date(2026, 8, 6),
            textos_registros={("M", 34712): (
                "AV.06-34.712 CEP\nAV.07-34.712 CANCELAMENTO\nR.08-34.712 VENDA E COMPRA"
            )},
        )
        ordem = [o for o in ocorrencias if o["regra"] == "ORDEM_OPERACIONAL"]
        self.assertEqual(ordem, [])

    def test_abertura_m0_nao_e_comparada_pela_posicao_no_array(self):
        imovel = {"tipo_registro": "M", "numero_registro": 39834}
        protocolo = _protocolo_base(itens_do_pedido=[
            {"natureza_formal_descricao": "Traslado", "dados_imovel": imovel,
             "atos_registrados": {"ato_tipo": "A", "ato_numero": 1, "texto": ""}},
            {"natureza_formal_descricao": "Abertura de Matrícula", "dados_imovel": imovel,
             "atos_registrados": {"ato_tipo": "M", "ato_numero": 0, "texto": ""}},
        ])
        ocorrencias = conferir_protocolo(self._item_registrado(), protocolo, date(2026, 8, 6))
        self.assertFalse(any(o["regra"] == "ORDEM_OPERACIONAL" for o in ocorrencias))

    def test_ordem_numerica_nao_compara_matriculas_novas_distintas_sem_numero(self):
        # Regressão: protocolo que abre duas matrículas novas de uma vez
        # (ex.: desmembramento) — nenhuma das duas tem numero_registro
        # ainda, mas são imóveis diferentes, cada um com sua própria
        # numeração começando do zero. Antes, ambas caíam no mesmo grupo
        # "sem número" e a comparação entre elas acusava ordem errada à toa.
        protocolo = _protocolo_base(itens_do_pedido=[
            {"natureza_formal_descricao": "Desmembramento",
             "dados_imovel": {"tipo_registro": "M", "numero_registro": None},
             "atos_registrados": {"ato_tipo": "M", "ato_numero": 30, "texto": ""}},
            {"natureza_formal_descricao": "Desmembramento",
             "dados_imovel": {"tipo_registro": "M", "numero_registro": None},
             "atos_registrados": {"ato_tipo": "M", "ato_numero": 5, "texto": ""}},
        ])
        ocorrencias = conferir_protocolo(self._item_registrado(), protocolo, date(2026, 8, 6))
        self.assertFalse(any(o["regra"] == "ORDEM_OPERACIONAL" for o in ocorrencias))

    def test_ordem_numerica_crescente_nao_gera_ocorrencia(self):
        # As três naturezas batem com o título (por conteúdo) para isolar
        # a checagem de ordem numérica, sem ruído da regra de natureza.
        protocolo = _protocolo_base(itens_do_pedido=[
            {"natureza_formal_descricao": "Cédula de Produto Rural", "dados_imovel": {},
             "atos_registrados": {"ato_tipo": "R", "ato_numero": 1, "texto": ""}},
            {"natureza_formal_descricao": "Cédula de Produto Rural", "dados_imovel": {},
             "atos_registrados": {"ato_tipo": "R", "ato_numero": 2, "texto": ""}},
            {"natureza_formal_descricao": "Cédula de Produto Rural", "dados_imovel": {},
             "atos_registrados": {"ato_tipo": "A", "ato_numero": 3, "texto": ""}},
        ])
        ocorrencias = conferir_protocolo(self._item_registrado(), protocolo, date(2026, 8, 6))
        self.assertEqual(ocorrencias, [])

    def test_ordem_numerica_ignora_sequencias_de_imoveis_diferentes(self):
        # Regressão relatada: "AV.31 seguido de AV.11" e "AV.24 seguido de
        # AV.15" foram sinalizados como fora de ordem, mas eram imóveis
        # diferentes dentro do mesmo protocolo -- cada matrícula tem sua
        # própria sequência de R./Av., não faz sentido compará-las entre si.
        protocolo = _protocolo_base(itens_do_pedido=[
            {"natureza_formal_descricao": "Cédula de Produto Rural",
             "dados_imovel": {"tipo_registro": "M", "numero_registro": 152},
             "atos_registrados": {"ato_tipo": "A", "ato_numero": 31, "texto": ""}},
            {"natureza_formal_descricao": "Cédula de Produto Rural",
             "dados_imovel": {"tipo_registro": "M", "numero_registro": 200},
             "atos_registrados": {"ato_tipo": "A", "ato_numero": 11, "texto": ""}},
            {"natureza_formal_descricao": "Cédula de Produto Rural",
             "dados_imovel": {"tipo_registro": "M", "numero_registro": 152},
             "atos_registrados": {"ato_tipo": "A", "ato_numero": 32, "texto": ""}},
        ])
        ocorrencias = conferir_protocolo(self._item_registrado(), protocolo, date(2026, 8, 6))
        self.assertFalse(any(o["regra"] == "ORDEM_OPERACIONAL" for o in ocorrencias))

    def test_detecta_atualizacao_do_imovel_numerada_depois_do_ato_principal(self):
        protocolo = _protocolo_base(itens_do_pedido=[
            {"natureza_formal_descricao": "Venda e Compra Imóvel Urbano (Simples)",
             "dados_imovel": {"tipo_registro": "M", "numero_registro": 152},
             "atos_registrados": {"ato_tipo": "R", "ato_numero": 1, "texto": ""}},
            {"natureza_formal_descricao": "Código de Endereçamento Postal - CEP",
             "dados_imovel": {"tipo_registro": "M", "numero_registro": 152},
             "atos_registrados": {"ato_tipo": "A", "ato_numero": 2, "texto": ""}},
        ])
        ocorrencias = conferir_protocolo(
            self._item_registrado(), protocolo, date(2026, 8, 6),
            textos_registros={("M", 152): "R.01-152 VENDA E COMPRA\nAV.02-152 CEP"},
        )
        self.assertTrue(any(o["regra"] == "ORDEM_OPERACIONAL" for o in ocorrencias))

    def test_api_pode_retornar_ato_principal_antes_das_duas_fases_preparatorias(self):
        imovel = {"tipo_registro": "M", "numero_registro": 27090}
        protocolo = _protocolo_base(itens_do_pedido=[
            {"natureza_formal_descricao": "Venda e Compra Imóvel Urbano (Simples)",
             "dados_imovel": imovel,
             "atos_registrados": {"ato_tipo": "R", "ato_numero": 3, "texto": ""}},
            {"natureza_formal_descricao": "Inserção de Dados Pessoais",
             "dados_imovel": imovel,
             "atos_registrados": {"ato_tipo": "A", "ato_numero": 2, "texto": ""}},
            {"natureza_formal_descricao": "Código de Endereçamento Postal - CEP",
             "dados_imovel": imovel,
             "atos_registrados": {"ato_tipo": "A", "ato_numero": 1, "texto": ""}},
        ])
        ocorrencias = conferir_protocolo(
            self._item_registrado(), protocolo, date(2026, 8, 6),
            textos_registros={("M", 27090): (
                "AV.01-27.090 CEP\nAV.02-27.090 INSERÇÃO DE DADOS\n"
                "R.03-27.090 VENDA E COMPRA"
            )},
        )
        self.assertFalse(any(o["regra"] == "ORDEM_OPERACIONAL" for o in ocorrencias))

    def test_desmembramento_184896_nao_gera_falso_alerta_de_ordem(self):
        imovel = {"tipo_registro": "M", "numero_registro": 30506}
        protocolo = _protocolo_base(itens_do_pedido=[
            {"natureza_formal_descricao": "Desmembramento de Imóvel Urbano",
             "dados_imovel": imovel,
             "atos_registrados": {"ato_tipo": "A", "ato_numero": 5, "texto": ""}},
            {"natureza_formal_descricao": "Encerramento de Matrícula",
             "dados_imovel": imovel,
             "atos_registrados": {"ato_tipo": "A", "ato_numero": 6, "texto": ""}},
            {"natureza_formal_descricao": "Atualização de Designação Cadastral do Imóvel",
             "dados_imovel": imovel,
             "atos_registrados": {"ato_tipo": "A", "ato_numero": 4, "texto": ""}},
        ])
        ocorrencias = conferir_protocolo(
            self._item_registrado(), protocolo, date(2026, 8, 25),
            textos_registros={("M", 30506): (
                "AV.04-30.506 DESIGNAÇÃO CADASTRAL\nAV.05-30.506 DESMEMBRAMENTO\n"
                "AV.06-30.506 ENCERRAMENTO"
            )},
        )
        self.assertFalse(any(o["regra"] == "ORDEM_OPERACIONAL" for o in ocorrencias))

    def test_data_placeholder_xx_e_ignorado_por_enquanto(self):
        protocolo = _protocolo_base()
        protocolo["itens_do_pedido"][0]["dados_imovel"] = {"tipo_registro": "M", "numero_registro": 152}
        ocorrencias = conferir_protocolo(
            self._item_registrado(), protocolo, date(2026, 8, 6),
            textos_registros={("M", 152): "R.01-152 - Data: xx.07.2026. Texto do ato."},
        )
        self.assertFalse(any(o["regra"] == "CAMPO_EM_BRANCO" and "xx" in o["descricao"] for o in ocorrencias))

    def test_data_do_fecho_em_branco_e_ignorada_por_enquanto(self):
        protocolo = _protocolo_base()
        protocolo["itens_do_pedido"][0]["dados_imovel"] = {"tipo_registro": "M", "numero_registro": 152}
        texto = (
            "R.01-152 Texto do ato. DOU FÉ. Morrinhos-GO, de de. Oficial: /mws/"
        )
        ocorrencias = conferir_protocolo(
            self._item_registrado(), protocolo, date(2026, 8, 6),
            textos_registros={("M", 152): texto},
        )
        self.assertFalse(any(o["regra"] == "CAMPO_EM_BRANCO" for o in ocorrencias))

    def test_valores_em_branco_geram_ocorrencia_de_atencao(self):
        protocolo = _protocolo_base()
        protocolo["itens_do_pedido"][0]["dados_imovel"] = {"tipo_registro": "M", "numero_registro": 152}
        texto = (
            "R.01-152 Texto do ato. Selo: . Cotação do ato: emolumentos: R$; ISSQN: R$; Total: R$."
        )
        ocorrencias = conferir_protocolo(
            self._item_registrado(), protocolo, date(2026, 8, 6),
            textos_registros={("M", 152): texto},
        )
        relevantes = [o for o in ocorrencias if o["regra"] == "CAMPO_EM_BRANCO"]
        self.assertTrue(relevantes)
        self.assertTrue(all(o["gravidade"] == "ATENCAO" for o in relevantes))

    def test_valores_em_branco_de_ato_isento_nao_geram_ocorrencia(self):
        protocolo = _protocolo_base()
        item = protocolo["itens_do_pedido"][0]
        item["dados_imovel"] = {"tipo_registro": "M", "numero_registro": 39834}
        item["detalhes_emolumentos"] = {
            "emolumentos": 0.0,
            "fundos": 0.0,
            "iss": 0.0,
            "total_do_item": 0.0,
            "tx_jud": 0.0,
            "valor_base_calculo": 0.0,
        }
        texto = (
            "R.01-39.834 Texto do ato isento. Selo: . Cotação do ato: "
            "emolumentos: R$; ISSQN: R$; taxa judiciária: R$; Total: R$."
        )
        ocorrencias = conferir_protocolo(
            self._item_registrado(), protocolo, date(2026, 8, 6),
            textos_registros={("M", 39834): texto},
        )
        self.assertFalse(any(o["regra"] == "CAMPO_EM_BRANCO" for o in ocorrencias))

    def test_total_zero_isolado_nao_disfarca_custas_em_branco(self):
        protocolo = _protocolo_base()
        item = protocolo["itens_do_pedido"][0]
        item["dados_imovel"] = {"tipo_registro": "M", "numero_registro": 152}
        item["detalhes_emolumentos"] = {"total_do_item": 0.0}
        texto = "R.01-152 Texto. Selo: . Cotação: emolumentos: R$; Total: R$."
        ocorrencias = conferir_protocolo(
            self._item_registrado(), protocolo, date(2026, 8, 6),
            textos_registros={("M", 152): texto},
        )
        self.assertTrue(any(o["regra"] == "CAMPO_EM_BRANCO" for o in ocorrencias))

    def test_regra_de_data_esta_desativada_em_conferir_protocolo(self):
        # Desativada a pedido: mesmo inferindo a data esperada a partir da
        # própria folha (em vez de "hoje - 1 dia" fixo), ainda gerava
        # ocorrência em casos legítimos. _regra_data_um_dia_antes continua
        # definida e testada isoladamente abaixo, pronta pra ser religada.
        ocorrencias = conferir_protocolo(
            self._item_registrado(data="2026-08-05"), _protocolo_base(), data_esperada=date(2026, 8, 6),
        )
        self.assertFalse(any(o["regra"] == "DATA_DIVERGENTE" for o in ocorrencias))

    def test_funcao_de_data_isolada_ainda_detecta_divergencia(self):
        ocorrencias = _regra_data_um_dia_antes(
            self._item_registrado(data="2026-08-05"), data_esperada=date(2026, 8, 6),
        )
        self.assertTrue(any(o["regra"] == "DATA_DIVERGENTE" for o in ocorrencias))

    def test_funcao_de_data_isolada_ignora_protocolo_prenotado(self):
        item = self._item_registrado(status="PRENOTADO", data="2026-08-01")
        ocorrencias = _regra_data_um_dia_antes(item, data_esperada=date(2026, 8, 6))
        self.assertEqual(ocorrencias, [])


if __name__ == "__main__":
    unittest.main()
