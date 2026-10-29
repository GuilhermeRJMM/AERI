"""Contrato visual e semântico do lote institucional, sem dados de produção."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class TestDesignSystem(unittest.TestCase):
    def test_folhas_em_ordem_estavel(self):
        html = (ROOT / "backend/templates/index.html").read_text(encoding="utf-8")
        self.assertLess(html.index("tokens.css"), html.index("design-system.css"))
        self.assertLess(html.index("sync-theme.css"), html.index("design-system.css"))
        self.assertLess(html.index("design-system.css"), html.index("intimacoes-mesa.css"))
        js = (ROOT / "backend/static/js/intimacoes.js").read_text(encoding="utf-8")
        self.assertIn("document.head.insertBefore(css,", js)
        self.assertNotIn("document.head.appendChild(temaGlobal)", js)

    def test_modulos_sao_botoes_nativos_com_nome(self):
        html = (ROOT / "backend/templates/index.html").read_text(encoding="utf-8")
        botoes = re.findall(r'<button class="nav-item[^"]*"([^>]*)>(.*?)</button>', html, re.S)
        self.assertGreaterEqual(len(botoes), 18)
        for attrs, conteudo in botoes:
            self.assertIn('type="button"', attrs)
            self.assertTrue(re.sub(r"<[^>]+>", "", conteudo).strip())
        self.assertIn('id="main-content" tabindex="-1"', html)

    def test_tokens_e_acessibilidade_compartilhados(self):
        css = (ROOT / "backend/static/design-system.css").read_text(encoding="utf-8")
        tokens = (ROOT / "backend/static/tokens.css").read_text(encoding="utf-8")
        for token in ["white", "navy", "green", "border", "muted", "warning", "error"]:
            self.assertIn(f"--aeri-{token}:", tokens)
        self.assertIn("prefers-reduced-motion", css)
        self.assertIn(":focus-visible", css)
        nav = (ROOT / "backend/static/js/navegacao.js").read_text(encoding="utf-8")
        self.assertIn("itemAlvo.setAttribute('aria-current', 'page')", nav)
        self.assertIn("history.pushState", nav)
        self.assertIn("'popstate'", nav)

    def test_interfaces_independentes_reutilizam_fundacao_clara(self):
        for nome in ['mapa_onr.html', 'gerador_notas/index.html',
                     'gerador_notas/revisar.html', 'gerador_notas/legislacao.html']:
            html = (ROOT / 'backend/private' / nome).read_text(encoding='utf-8')
            self.assertIn('/static/tokens.css', html)
        mapa = (ROOT / 'backend/private/mapa_onr.html').read_text(encoding='utf-8')
        self.assertNotIn('color-scheme: dark', mapa)
        self.assertNotIn('prefers-color-scheme: dark', mapa)

    def test_sem_cores_semanticas_indefinidas(self):
        arquivos = [ROOT / 'backend/static' / n for n in
                    ['tokens.css', 'design-system.css', 'intimacoes-mesa.css']]
        css = '\n'.join(p.read_text(encoding='utf-8') for p in arquivos)
        definidos = set(re.findall(r'(--aeri-[\w-]+)\s*:', css))
        usados = set(re.findall(r'var\((--aeri-[\w-]+)', css))
        self.assertEqual(usados - definidos, set())


if __name__ == "__main__":
    unittest.main()
