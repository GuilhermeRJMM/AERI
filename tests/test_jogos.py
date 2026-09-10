import unittest
from pathlib import Path
from unittest.mock import patch

from backend.app.main import app
from backend.app.rotas import jogos


RAIZ = Path(__file__).resolve().parents[1]


class TesteSalaoJogos(unittest.TestCase):
    def test_codigo_compartilhado_confere_no_servidor(self):
        codigo = "".join(chr(valor) for valor in (54, 55, 54, 55))
        with patch.dict("os.environ", {"AERI_JOGOS_SENHA": codigo}):
            self.assertTrue(jogos._codigo_acesso_valido(codigo))
            self.assertFalse(jogos._codigo_acesso_valido(codigo[::-1]))

    def test_acesso_falha_fechado_sem_segredo_no_ambiente(self):
        with patch.dict("os.environ", {"AERI_JOGOS_SENHA": ""}):
            with self.assertRaisesRegex(Exception, "indisponível"):
                jogos._codigo_acesso_valido("qualquer")

    def test_vitoria_horizontal(self):
        self.assertEqual("X", jogos._resultado_tabuleiro(["X", "X", "X", "", "O", "", "O", "", ""]))

    def test_vitoria_diagonal(self):
        self.assertEqual("O", jogos._resultado_tabuleiro(["O", "X", "", "", "O", "X", "", "", "O"]))

    def test_empate(self):
        self.assertEqual("EMPATE", jogos._resultado_tabuleiro(["X", "O", "X", "X", "O", "O", "O", "X", "X"]))

    def test_partida_em_aberto(self):
        self.assertIsNone(jogos._resultado_tabuleiro(["X", "", "", "", "O", "", "", "", ""]))

    def test_codigo_nao_e_embarcado_no_javascript(self):
        javascript = (RAIZ / "backend" / "static" / "js" / "jogos.js").read_text(encoding="utf-8")
        self.assertNotIn(str(67) * 2, javascript)
        self.assertNotIn("AERI_JOGOS_SENHA", javascript)

    def test_rotas_nao_ficam_expostas_na_navegacao(self):
        template = (RAIZ / "backend" / "templates" / "index.html").read_text(encoding="utf-8")
        self.assertNotIn('data-page="jogos"', template)
        self.assertTrue(any(getattr(rota, "original_router", None) is jogos.router for rota in app.routes))
        caminhos = {rota.path for rota in jogos.router.routes}
        self.assertIn("/api/jogos/entrar", caminhos)
        self.assertIn("/api/jogos/presenca", caminhos)
        self.assertIn("/api/jogos/salas/{sala_id}/jogar", caminhos)
        self.assertNotIn("/api/jogos/entrar", app.openapi()["paths"])

    def test_atualizacao_da_presenca_e_curta(self):
        migracao = (RAIZ / "backend" / "app" / "migrations" / "045_salao_jogos.sql").read_text(encoding="utf-8")
        rota = (RAIZ / "backend" / "app" / "rotas" / "jogos.py").read_text(encoding="utf-8")
        self.assertIn("presente_ate", migracao)
        self.assertIn("INTERVAL '30 seconds'", rota)
        self.assertIn("destinatario", migracao)


if __name__ == "__main__":
    unittest.main()
