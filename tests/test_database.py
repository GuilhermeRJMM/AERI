import os
import unittest
from unittest.mock import MagicMock, patch

from backend.app.database import _garantir_usuario_administrador


class TesteBootstrapAdministrador(unittest.TestCase):
    def _ambiente(self):
        return patch.dict(
            os.environ,
            {
                "AERI_ADMIN_USER": "ADMIN_TESTE",
                "AERI_ADMIN_PASSWORD": "Senha-Temporaria-2026!",
            },
        )

    def test_conta_existente_nunca_e_reativada_ou_promovida(self):
        cursor = MagicMock()
        cursor.fetchone.return_value = {"perfil": "CONFERENTE", "ativo": False}

        with self._ambiente():
            _garantir_usuario_administrador(cursor)

        comandos = "\n".join(chamada.args[0] for chamada in cursor.execute.call_args_list)
        self.assertNotIn("UPDATE usuarios_aeri", comandos)
        self.assertNotIn("INSERT INTO usuarios_aeri", comandos)

    def test_primeira_instalacao_cria_conta_e_registra_auditoria(self):
        cursor = MagicMock()
        cursor.fetchone.return_value = None

        with self._ambiente():
            _garantir_usuario_administrador(cursor)

        comandos = "\n".join(chamada.args[0] for chamada in cursor.execute.call_args_list)
        self.assertIn("INSERT INTO usuarios_aeri", comandos)
        self.assertIn("bootstrap_admin_criado", comandos)


if __name__ == "__main__":
    unittest.main()
