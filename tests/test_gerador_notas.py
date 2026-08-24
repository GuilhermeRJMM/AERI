import unittest
from pathlib import Path

from backend.app.gerador_notas.servico import (
    catalogo_para_tela,
    gerar_documento,
    legislacao,
    previa,
    procurar_artigos,
)


class GeradorNotasTest(unittest.TestCase):
    def test_importa_catalogo_completo_do_repositorio_fonte(self):
        catalogo = catalogo_para_tela()
        self.assertEqual(len(catalogo["exigencias"]), 65)
        self.assertEqual(len(catalogo["especies"]), 4)
        self.assertTrue(catalogo["somente_leitura"])

    def test_importa_base_legislativa_e_pesquisa_artigos(self):
        self.assertEqual(len(legislacao()), 30)
        resultados = procurar_artigos("LRP", "176")
        self.assertTrue(resultados)
        self.assertTrue(any("176" in item["artigo"] for item in resultados))

    def test_previa_escapa_texto_informado_pelo_operador(self):
        resultado = previa({
            "especie": "devolutiva",
            "titulo": "<img src=x onerror=alert(1)>",
            "itens": [{"exigencia": "casamento-data-nao-comprovada", "valores": {}}],
        })
        self.assertNotIn("<img", resultado["html"])
        self.assertIn("&lt;img", resultado["html"])

    def test_gera_docx_em_memoria_com_nome_saneado(self):
        nome, conteudo, nao_revisadas = gerar_documento({
            "especie": "devolutiva",
            "titulo": "Certidão de casamento apresentada",
            "protocolo": "185.100/../../indevido",
            "itens": [{"exigencia": "casamento-data-nao-comprovada", "valores": {}}],
        })
        self.assertEqual(nome, "185.100-..-..-indevido - Devolutiva.docx")
        self.assertTrue(conteudo.startswith(b"PK"))
        self.assertIn("casamento-data-nao-comprovada", nao_revisadas)

    def test_interface_principal_e_nativa_e_carregada_sob_demanda(self):
        raiz = Path(__file__).resolve().parent.parent
        html = (raiz / "backend/templates/index.html").read_text(encoding="utf-8")
        javascript = (raiz / "backend/static/js/gerador_notas.js").read_text(encoding="utf-8")
        inicio = html.index('id="page-geradornotas"')
        fim = html.index('id="page-buscas"', inicio)
        pagina = html[inicio:fim]
        self.assertNotIn("<iframe", pagina)
        self.assertIn('id="gn-editor"', pagina)
        self.assertIn('id="gn-legislacao"', pagina)
        self.assertIn('id="gn-base"', pagina)
        self.assertIn("function carregarSeNecessario()", javascript)
        self.assertIn("aeri:pagina-alterada", javascript)


if __name__ == "__main__":
    unittest.main()
