import unittest

from backend.app.autenticacao import hash_senha, senha_forte, verificar_senha


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


if __name__ == "__main__":
    unittest.main()
