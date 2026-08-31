"""Toda permissão declarada precisa ser lida pela sessão.

A permissão vive em três lugares que têm de andar juntos: a coluna em
usuarios_aeri, o mapeamento em PERMISSOES e o SELECT que monta a sessão.
Esquecer o terceiro não dá erro nenhum -- a permissão grava certo no
banco, a caixa aparece marcada na tela de usuários, e mesmo assim o
módulo não abre, porque permissoes_sessao lê a coluna do dicionário da
sessão e recebe None.

Foi o que aconteceu com Livro de Protocolos, Buscas e Polígonos: as três
foram criadas sem entrar nesse SELECT.
"""
import re
import unittest
from pathlib import Path

from backend.app.autenticacao import (
    PERFIS_ADMINISTRATIVOS,
    PERMISSOES,
    PERMISSOES_AUDITOR,
    PERMISSOES_OPCIONAIS_AUDITOR,
    permissoes_sessao,
)
from backend.app.permissoes import COLUNAS_LEGADAS


RAIZ = Path(__file__).resolve().parent.parent
AUTENTICACAO = RAIZ / "backend" / "app" / "autenticacao.py"
ROTA_AUTENTICACAO = RAIZ / "backend" / "app" / "rotas" / "autenticacao.py"
MIGRACOES = RAIZ / "backend" / "app" / "migrations"


def _consulta_da_sessao() -> str:
    fonte = AUTENTICACAO.read_text(encoding="utf-8")
    achado = re.search(r'"""SELECT s\.\*.*?"""', fonte, re.S)
    assert achado, "não achei o SELECT que monta a sessão"
    return achado.group(0)


def _consulta_do_login() -> str:
    fonte = ROTA_AUTENTICACAO.read_text(encoding="utf-8")
    achado = re.search(r'"""SELECT \* FROM usuarios_aeri.*?"""', fonte, re.S)
    assert achado, "o login voltou a enumerar manualmente as permissões"
    return achado.group(0)


class TesteConsultaDaSessao(unittest.TestCase):
    def test_le_todas_as_colunas_de_permissao(self):
        consulta = _consulta_da_sessao()
        self.assertIn(
            "u.*", consulta,
            "a sessão voltou a enumerar colunas; a próxima permissão nova "
            "poderá ser esquecida e ficar invisível mesmo gravada no banco",
        )

    def test_login_le_todas_as_permissoes_sem_lista_manual(self):
        consulta = _consulta_do_login()
        self.assertIn("SELECT * FROM usuarios_aeri", consulta)

    def test_toda_coluna_tem_migracao_que_a_cria(self):
        # O contrário também quebra: mapear coluna que não existe faz o
        # SELECT falhar e derruba o login inteiro.
        sql = "\n".join(
            arquivo.read_text(encoding="utf-8")
            for arquivo in MIGRACOES.glob("*.sql")
        )
        sem_migracao = [c for c in COLUNAS_LEGADAS.values() if c not in sql]
        self.assertEqual(sem_migracao, [], f"colunas sem migração: {sem_migracao}")


class TestePermissoesDaSessao(unittest.TestCase):
    def _sessao(self, perfil, **colunas):
        return {"perfil": perfil, **colunas}

    def test_cargo_administrativo_recebe_tudo(self):
        for perfil in PERFIS_ADMINISTRATIVOS:
            with self.subTest(perfil=perfil):
                saida = permissoes_sessao(self._sessao(perfil))
                self.assertTrue(all(saida.values()))
                self.assertEqual(set(saida), set(PERMISSOES))

    def test_perfil_comum_recebe_o_que_esta_marcado(self):
        sessao = self._sessao(
            "CONFERENTE",
            pode_acessar_buscas=True,
            pode_acessar_poligonos=False,
        )
        saida = permissoes_sessao(sessao)

        self.assertTrue(saida["acessar_buscas"])
        self.assertFalse(saida["acessar_poligonos"])
        # Coluna ausente do dicionário tem de valer False, e não estourar.
        self.assertFalse(saida["gerenciar_custas"])

    def test_perfil_comum_prefere_relacoes_as_colunas_antigas(self):
        sessao = self._sessao(
            "CONFERENTE",
            permissoes_relacionais={"acessar_certidao": True, "acessar_buscas": True},
            pode_acessar_buscas=False,
            pode_acessar_poligonos=True,
        )
        saida = permissoes_sessao(sessao)
        self.assertTrue(saida["acessar_buscas"])
        self.assertFalse(saida["acessar_poligonos"])

    def test_auditor_recebe_as_fixas_e_as_opcionais_marcadas(self):
        sessao = self._sessao("AUDITOR", pode_acessar_poligonos=True)
        saida = permissoes_sessao(sessao)

        for chave in PERMISSOES_AUDITOR:
            with self.subTest(fixa=chave):
                self.assertTrue(saida[chave])
        self.assertTrue(saida["acessar_poligonos"])
        self.assertFalse(saida["acessar_buscas"])

    def test_auditor_nao_ganha_permissao_fora_da_lista_opcional(self):
        # Marcar no banco algo que não é opcional para AUDITOR não pode
        # conceder acesso: a lista é a autoridade.
        sessao = self._sessao("AUDITOR", pode_gerenciar_custas=True)
        self.assertNotIn("gerenciar_custas", PERMISSOES_OPCIONAIS_AUDITOR)
        self.assertFalse(permissoes_sessao(sessao)["gerenciar_custas"])


if __name__ == "__main__":
    unittest.main()
