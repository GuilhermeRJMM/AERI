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
        self.assertEqual(len(catalogo["exigencias"]), 72)
        self.assertEqual(len(catalogo["especies"]), 4)
        self.assertTrue(catalogo["somente_leitura"])
        ids = {item["id"] for item in catalogo["exigencias"]}
        self.assertIn("construcao-sem-habite-se", ids)
        self.assertIn("alienacao-fiduciaria-ativa", ids)
        self.assertIn("indisponibilidade-ativa", ids)

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

    def test_nova_exigencia_de_construcao_sem_habite_se_entra_na_previa(self):
        resultado = previa({
            "especie": "devolutiva",
            "titulo": "Averbação de construção",
            "itens": [{
                "exigencia": "construcao-sem-habite-se",
                "valores": {"matricula": "18.552"},
            }],
        })
        self.assertIn("habite-se", resultado["html"].lower())
        self.assertIn("18.552", resultado["html"])

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

    def test_modal_nativo_recebe_classe_visivel(self):
        raiz = Path(__file__).resolve().parent.parent
        javascript = (raiz / "backend/static/js/gerador_notas.js").read_text(encoding="utf-8")
        self.assertIn("modal.classList.add('aberta')", javascript)
        self.assertIn("modal.classList.remove('aberta')", javascript)

    def test_legislacao_abre_uma_norma_e_pesquisa_artigos_nela(self):
        raiz = Path(__file__).resolve().parent.parent
        html = (raiz / "backend/templates/index.html").read_text(encoding="utf-8")
        javascript = (raiz / "backend/static/js/gerador_notas.js").read_text(encoding="utf-8")
        self.assertIn('id="gn-artigo-filtro"', html)
        self.assertIn('id="gn-artigo-lista"', html)
        self.assertIn('data-gn-norma=', javascript)
        self.assertIn("function selecionarNorma(id)", javascript)
        self.assertIn("`${API}/artigos?norma=${encodeURIComponent(legislacaoAtual)}", javascript)

    def test_geracao_docx_explica_campos_ausentes_antes_da_requisicao(self):
        raiz = Path(__file__).resolve().parent.parent
        javascript = (raiz / "backend/static/js/gerador_notas.js").read_text(encoding="utf-8")
        self.assertIn("Selecione ao menos uma pendência para gerar o DOCX.", javascript)
        self.assertIn("Informe o título apresentado para gerar o DOCX.", javascript)
        self.assertIn("O texto exibido em cinza é apenas um exemplo.", javascript)


if __name__ == "__main__":
    unittest.main()
