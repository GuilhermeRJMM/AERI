"""Toda aba do menu precisa estar registrada no controle de permissão.

O index.html esconde por CSS todo ``.nav-item`` que não tenha
``data-autorizado="true"``, e quem define esse atributo é somente
``aplicarPermissoesSidebar``, em autenticacao.js. Uma aba que exista no
HTML mas não apareça naquela função fica invisível para todo mundo --
inclusive para o ADMIN -- e o sintoma não é erro nenhum no console, é
simplesmente um módulo que ninguém encontra.

Foi exatamente o que aconteceu com a aba Polígonos ao ser criada.
"""
import re
import unittest
from pathlib import Path


RAIZ = Path(__file__).resolve().parent.parent
INDEX = RAIZ / "backend" / "templates" / "index.html"
AUTENTICACAO = RAIZ / "backend" / "static" / "js" / "autenticacao.js"


def _abas_declaradas() -> set:
    html = INDEX.read_text(encoding="utf-8")
    return set(re.findall(r'class="nav-item[^"]*"\s+(?:id="[^"]*"\s+)?data-page="([^"]+)"', html))


def _abas_controladas() -> set:
    js = AUTENTICACAO.read_text(encoding="utf-8")
    return set(re.findall(r"definirModuloVisivel\(\s*'([^']+)'", js))


class TesteMenuLateral(unittest.TestCase):
    def test_o_html_declara_abas(self):
        # Sanidade da própria extração: se as expressões pararem de casar,
        # os testes abaixo passariam por vacuidade.
        abas = _abas_declaradas()
        self.assertGreaterEqual(len(abas), 8, f"extração falhou, achei {abas}")
        self.assertIn("poligonos", abas)

    def test_toda_aba_do_html_tem_controle_de_permissao(self):
        faltando = _abas_declaradas() - _abas_controladas()
        self.assertFalse(
            faltando,
            f"abas sem definirModuloVisivel em autenticacao.js: {sorted(faltando)}. "
            "Sem isso o CSS as mantém escondidas para todos os perfis.",
        )

    def test_nao_controla_aba_que_nao_existe(self):
        # O contrário também é defeito: controlar uma aba removida esconde
        # um erro de digitação no nome da página.
        sobrando = _abas_controladas() - _abas_declaradas()
        self.assertFalse(sobrando, f"definirModuloVisivel para aba inexistente: {sorted(sobrando)}")

    def test_toda_aba_tem_a_pagina_correspondente(self):
        html = INDEX.read_text(encoding="utf-8")
        paginas = set(re.findall(r'id="page-([^"]+)"', html))
        sem_pagina = _abas_declaradas() - paginas
        self.assertFalse(sem_pagina, f"abas sem <div id=\"page-...\">: {sorted(sem_pagina)}")

    def test_poligonos_usa_a_permissao_certa(self):
        js = AUTENTICACAO.read_text(encoding="utf-8")
        linha = next(
            (l for l in js.splitlines() if "definirModuloVisivel('poligonos'" in l), "")
        self.assertIn("acessar_poligonos", linha)
        # Cargo administrativo entra sem depender da coluna do banco.
        self.assertIn("admin", linha)


if __name__ == "__main__":
    unittest.main()
