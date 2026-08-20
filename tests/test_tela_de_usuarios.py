"""A tela de usuários precisa conhecer as mesmas regras do servidor.

Salvar um usuário reenvia TODAS as permissões de uma vez. Então, se o
formulário desmarca uma permissão que o servidor considera concedível,
abrir o cadastro por qualquer motivo e salvar apaga o acesso -- sem erro,
sem aviso, e a caixa some do menu na próxima entrada da pessoa.

Foi o que aconteceu: a tela tratava MAPA-ONR como a única opcional de
AUDITOR, e Livro de Protocolos, Buscas e Polígonos, criadas depois,
ficavam travadas e desmarcadas.
"""
import re
import unittest
from pathlib import Path

from backend.app.autenticacao import (
    PERMISSOES,
    PERMISSOES_AUDITOR,
    PERMISSOES_OPCIONAIS_AUDITOR,
)


RAIZ = Path(__file__).resolve().parent.parent
USUARIOS_JS = RAIZ / "backend" / "static" / "js" / "usuarios.js"
INDEX = RAIZ / "backend" / "templates" / "index.html"


def _lista_do_js(nome: str) -> set:
    fonte = USUARIOS_JS.read_text(encoding="utf-8")
    achado = re.search(rf"const {nome} = \[(.*?)\];", fonte, re.S)
    assert achado, f"não achei {nome} em usuarios.js"
    return set(re.findall(r"'([^']+)'", achado.group(1)))


class TesteRegrasDoAuditor(unittest.TestCase):
    def test_permissoes_fixas_batem_com_o_servidor(self):
        self.assertEqual(
            _lista_do_js("PERMISSOES_FIXAS_DO_AUDITOR"), set(PERMISSOES_AUDITOR))

    def test_permissoes_opcionais_batem_com_o_servidor(self):
        self.assertEqual(
            _lista_do_js("PERMISSOES_OPCIONAIS_DO_AUDITOR"),
            set(PERMISSOES_OPCIONAIS_AUDITOR),
            "o formulário desmarcaria uma permissão que o servidor concede, "
            "e salvar o cadastro apagaria o acesso",
        )

    def test_opcional_e_fixa_nao_se_sobrepoem(self):
        self.assertEqual(
            set(PERMISSOES_AUDITOR) & set(PERMISSOES_OPCIONAIS_AUDITOR), set())


class TesteCaixasDaTela(unittest.TestCase):
    def test_toda_permissao_tem_caixa_no_formulario(self):
        html = INDEX.read_text(encoding="utf-8")
        no_formulario = set(re.findall(r'data-permissao-form="([^"]+)"', html))
        faltando = set(PERMISSOES) - no_formulario
        self.assertEqual(
            faltando, set(),
            f"permissões sem caixa no formulário de usuário: {sorted(faltando)}")

    def test_toda_permissao_tem_caixa_na_linha_da_tabela(self):
        # A lista ATRIBUICOES alimenta a linha de cada usuário comum.
        fonte = USUARIOS_JS.read_text(encoding="utf-8")
        achado = re.search(r"const ATRIBUICOES = \[(.*?)\];", fonte, re.S)
        self.assertIsNotNone(achado, "não achei ATRIBUICOES em usuarios.js")
        na_tabela = set(re.findall(r"\['([^']+)'", achado.group(1)))
        faltando = set(PERMISSOES) - na_tabela
        self.assertEqual(
            faltando, set(),
            f"permissões sem caixa na tabela de usuários: {sorted(faltando)}")

    def test_o_formulario_nao_oferece_permissao_inexistente(self):
        html = INDEX.read_text(encoding="utf-8")
        no_formulario = set(re.findall(r'data-permissao-form="([^"]+)"', html))
        sobrando = no_formulario - set(PERMISSOES)
        self.assertEqual(sobrando, set(), f"caixas órfãs: {sorted(sobrando)}")


if __name__ == "__main__":
    unittest.main()
