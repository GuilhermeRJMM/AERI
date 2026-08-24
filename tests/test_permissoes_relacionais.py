import unittest
from pathlib import Path

from backend.app.permissoes import (
    CATALOGO_PERMISSOES,
    PERMISSOES,
    selecionar_usuarios_com_permissoes,
)


class TestePermissoesRelacionais(unittest.TestCase):
    def test_migracao_cria_as_tres_relacoes_e_preserva_legado(self):
        raiz = Path(__file__).resolve().parent.parent
        sql = (raiz / "backend/app/migrations/038_permissoes_relacionais.sql").read_text(encoding="utf-8")
        self.assertIn("CREATE TABLE IF NOT EXISTS permissoes_aeri", sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS usuarios_permissoes_aeri", sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS perfis_permissoes_aeri", sql)
        self.assertIn("CROSS JOIN LATERAL", sql)
        self.assertNotIn("DROP COLUMN", sql.upper())

    def test_sessao_agrega_perfil_e_usuario_sem_enumerar_chaves(self):
        consulta = selecionar_usuarios_com_permissoes()
        self.assertIn("perfis_permissoes_aeri", consulta)
        self.assertIn("usuarios_permissoes_aeri", consulta)
        for item in CATALOGO_PERMISSOES:
            self.assertNotIn(f"'{item['chave']}'", consulta)

    def test_catalogo_e_a_fonte_das_chaves(self):
        self.assertEqual({item["chave"] for item in CATALOGO_PERMISSOES}, set(PERMISSOES))


if __name__ == "__main__":
    unittest.main()
