import os
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from backend.app.seguranca_mfa import (
    cifrar_segredo,
    codigo_totp,
    decifrar_segredo,
    novo_segredo,
    validar_totp,
)
from backend.app.servicos.intimacoes import andamento_indica_intimacao_positiva, somar_dias_uteis


RAIZ = Path(__file__).resolve().parents[1]


class TesteOperacaoAprovada(unittest.TestCase):
    def test_decimo_sexto_dia_util_respeita_fim_de_semana_e_feriado(self):
        inicio = date(2026, 8, 3)  # segunda-feira
        feriados = {date(2026, 8, 10)}
        self.assertEqual(somar_dias_uteis(inicio, 16, feriados), date(2026, 8, 26))

    def test_andamento_positivo_aceita_acentos(self):
        self.assertTrue(andamento_indica_intimacao_positiva("Aguardando - Intimação Positiva"))
        self.assertFalse(andamento_indica_intimacao_positiva("Intimação Negativa"))

    def test_mfa_cifra_segredo_e_valida_totp(self):
        with patch.dict(os.environ, {"AERI_MFA_ENCRYPTION_KEY": "x" * 40}):
            segredo = novo_segredo()
            cifrado = cifrar_segredo(segredo)
            self.assertNotIn(segredo, cifrado)
            self.assertEqual(decifrar_segredo(cifrado), segredo)
            self.assertTrue(validar_totp(segredo, codigo_totp(segredo)))

    def test_novo_usuario_nao_nasce_com_todas_as_permissoes_marcadas(self):
        javascript = (RAIZ / "backend/static/js/usuarios.js").read_text(encoding="utf-8")
        self.assertIn("marcadas[permissao.chave] === true", javascript)
        self.assertNotIn("marcadas[permissao.chave] !== false", javascript)


if __name__ == "__main__":
    unittest.main()
