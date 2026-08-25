"""A tela de usuários deve consumir o catálogo central do servidor.

Não há mais uma cópia manual das permissões no HTML ou no JavaScript. Cada
caixa altera somente uma relação usuário-permissão, evitando a corrida que
apagava acessos do Eduardo quando duas opções eram marcadas em sequência.
"""
import unittest
from pathlib import Path

from backend.app.autenticacao import PERMISSOES
from backend.app.permissoes import catalogo_publico


RAIZ = Path(__file__).resolve().parent.parent
USUARIOS_JS = RAIZ / "backend" / "static" / "js" / "usuarios.js"
INDEX = RAIZ / "backend" / "templates" / "index.html"

class TesteCatalogoDinamico(unittest.TestCase):
    def test_catalogo_cobre_todas_as_permissoes(self):
        self.assertEqual({item["chave"] for item in catalogo_publico()}, set(PERMISSOES))

    def test_formulario_tem_apenas_o_ponto_de_montagem(self):
        html = INDEX.read_text(encoding="utf-8")
        self.assertIn('id="usuario-permissoes-catalogo"', html)
        self.assertNotIn('data-permissao-form="', html)

    def test_tela_busca_catalogo_e_grava_uma_permissao_por_vez(self):
        fonte = USUARIOS_JS.read_text(encoding="utf-8")
        self.assertIn("/api/usuarios/permissoes/catalogo", fonte)
        self.assertIn("/permissoes/${alvo.dataset.permissao}", fonte)
        self.assertIn("method:'PATCH'", fonte)

    def test_regras_do_auditor_chegam_pelo_catalogo(self):
        itens = catalogo_publico()
        fixas = {item["chave"] for item in itens if item["auditorFixa"]}
        opcionais = {item["chave"] for item in itens if item["auditorOpcional"]}
        self.assertFalse(fixas & opcionais)

    def test_modal_exibe_a_senha_temporaria_gerada(self):
        fonte = USUARIOS_JS.read_text(encoding="utf-8")
        inicio = fonte.index("function revelarSenha")
        fim = fonte.index("async function copiarSenhaRevelada", inicio)
        revelar = fonte[inicio:fim]
        self.assertIn("modal.hidden = false", revelar)
        self.assertIn("modal.classList.add('aberta')", revelar)

        inicio = fonte.index("'btn-fechar-senha-gerada'")
        fechar = fonte[inicio:]
        self.assertIn("modal.classList.remove('aberta')", fechar)
        self.assertIn("modal.hidden = true", fechar)


if __name__ == "__main__":
    unittest.main()
