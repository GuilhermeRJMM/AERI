import unittest
from unittest.mock import MagicMock, Mock, patch

from fastapi import HTTPException

from backend.app.autenticacao import hash_senha
from backend.app.rotas.usuarios import trocar_minha_senha


def _requisicao(usuario: str = "EDUARDO"):
    requisicao = Mock()
    requisicao.state.sessao = {"usuario": usuario, "id": "sessao-1", "perfil": "CONFERENTE"}
    return requisicao


def _conexao_com_senha(hash_atual: str):
    conexao = MagicMock()
    cursor = MagicMock()
    cursor.fetchone.return_value = {"senha_hash": hash_atual}
    conexao.__enter__.return_value = conexao
    conexao.cursor.return_value.__enter__.return_value = cursor
    return conexao


class TesteTrocaDeSenha(unittest.TestCase):
    def test_senha_atual_errada_nao_derruba_a_sessao(self):
        # Regressão: a rota devolvia 401 quando a senha atual estava errada, e
        # o cliente HTTP trata qualquer 401 como sessão expirada -- jogava o
        # usuário de volta para a tela de login, com a mensagem trocada, em
        # vez de apenas avisar que a senha digitada não confere. Isso pegava
        # justamente quem acabou de ser criado e precisa transcrever uma
        # senha temporária longa.
        conexao = _conexao_com_senha(hash_senha("Senha-Temporaria-2026!"))
        with patch("backend.app.rotas.usuarios.conectar", return_value=conexao), \
                patch("backend.app.rotas.usuarios.registrar_auditoria_cursor"):
            with self.assertRaises(HTTPException) as erro:
                trocar_minha_senha(
                    {"senhaAtual": "errada-mas-forte-A1!", "novaSenha": "Nova-Senha-2026!"},
                    _requisicao(),
                )

        self.assertEqual(erro.exception.status_code, 422)
        self.assertNotEqual(erro.exception.status_code, 401)
        self.assertIn("Senha atual", erro.exception.detail)

    def test_nova_senha_fraca_e_recusada_antes_de_consultar_o_banco(self):
        with patch("backend.app.rotas.usuarios.conectar") as conectar:
            with self.assertRaises(HTTPException) as erro:
                trocar_minha_senha(
                    {"senhaAtual": "qualquer", "novaSenha": "fraca1!"},
                    _requisicao(),
                )

        self.assertEqual(erro.exception.status_code, 422)
        conectar.assert_not_called()

    def test_troca_bem_sucedida_preserva_a_sessao_em_uso(self):
        conexao = _conexao_com_senha(hash_senha("Senha-Temporaria-2026!"))
        with patch("backend.app.rotas.usuarios.conectar", return_value=conexao), \
                patch("backend.app.rotas.usuarios.registrar_auditoria_cursor"):
            resposta = trocar_minha_senha(
                {"senhaAtual": "Senha-Temporaria-2026!", "novaSenha": "Nova-Senha-2026!"},
                _requisicao(),
            )

        self.assertEqual(resposta, {"ok": True})
        cursor = conexao.cursor.return_value.__enter__.return_value
        revogacoes = [
            chamada for chamada in cursor.execute.call_args_list
            if "revogada_em=NOW()" in chamada.args[0]
        ]
        self.assertEqual(len(revogacoes), 1)
        # a sessão que trocou a senha não pode estar entre as revogadas
        self.assertIn("id<>%s", revogacoes[0].args[0])
        self.assertEqual(revogacoes[0].args[1][1], "sessao-1")


if __name__ == "__main__":
    unittest.main()
