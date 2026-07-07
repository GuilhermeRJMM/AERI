import unittest

from backend.app.autenticacao import hash_senha, permissoes_sessao, senha_forte, verificar_senha


class TesteSeguranca(unittest.TestCase):
    def test_argon2_valida_senha_sem_armazenar_texto(self):
        senha = "Senha-Forte-AERI-2026!"
        armazenada = hash_senha(senha)
        self.assertTrue(armazenada.startswith("$argon2id$"))
        self.assertNotIn(senha, armazenada)
        self.assertTrue(verificar_senha(senha, armazenada))
        self.assertFalse(verificar_senha("senha-errada", armazenada))

    def test_politica_recusa_senhas_fracas(self):
        self.assertTrue(senha_forte("Senha-Forte-AERI-2026!"))
        self.assertFalse(senha_forte("adm123"))
        self.assertFalse(senha_forte("somente-minusculas-2026"))

    def test_admin_tem_todas_as_permissoes(self):
        permissoes = permissoes_sessao({"perfil": "ADMIN"})

        self.assertTrue(all(permissoes.values()))

    def test_substituto_tem_permissoes_administrativas(self):
        permissoes = permissoes_sessao({"perfil": "SUBSTITUTO"})

        self.assertTrue(all(permissoes.values()))

    def test_operador_respeita_atribuicoes(self):
        permissoes = permissoes_sessao(
            {
                "perfil": "CONFERENTE",
                "pode_processar_matricula": True,
                "pode_processar_incra": False,
                "pode_ver_intimacoes": True,
                "pode_criar_intimacoes": False,
                "pode_alterar_intimacoes": False,
                "pode_conferir_intimacoes": True,
            }
        )

        self.assertTrue(permissoes["processar_matricula"])
        self.assertFalse(permissoes["processar_incra"])
        self.assertFalse(permissoes["criar_intimacoes"])
        self.assertTrue(permissoes["conferir_intimacoes"])


if __name__ == "__main__":
    unittest.main()
