"""Rotas do módulo Polígonos, com atenção ao desvio do PostGIS.

O módulo tem de funcionar nos dois bancos: com a extensão, respondendo
quanta área foi invadida; sem ela, respondendo apenas quem se sobrepõe.
Errar esse desvio é grave nas duas direções -- chamar função inexistente
derruba a rota, e ignorar o PostGIS existente esconde do conferente o
número que ele foi buscar.
"""
import unittest
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

from fastapi import HTTPException

from backend.app.rotas import poligonos as R


ALVO = UUID("11111111-1111-4111-8111-111111111111")
VIZINHO = UUID("22222222-2222-4222-8222-222222222222")


def _conexao(cursor):
    conexao = MagicMock()
    conexao.__enter__.return_value = conexao
    conexao.cursor.return_value.__enter__.return_value = cursor
    return conexao


def _quadrado(x0, y0, lado=0.01):
    return [[x0, y0], [x0 + lado, y0], [x0 + lado, y0 + lado], [x0, y0 + lado]]


class TesteDeteccaoDoRecorte(unittest.TestCase):
    def test_reconhece_pela_funcao_e_nao_pela_extensao(self):
        cursor = MagicMock()
        cursor.fetchone.return_value = {"tem": True}

        self.assertTrue(R._tem_recorte(cursor))
        sql, parametros = cursor.execute.call_args.args
        # Checar pg_proc, e não pg_extension: é a função que as consultas
        # chamam, e ela só existe depois da migração 033 rodar.
        self.assertIn("pg_proc", sql)
        self.assertEqual(parametros, ("aeri_anel_para_geometria",))

    def test_banco_sem_a_funcao(self):
        cursor = MagicMock()
        cursor.fetchone.return_value = {"tem": False}
        self.assertFalse(R._tem_recorte(cursor))


class TesteSemPostgis(unittest.TestCase):
    """Sem a extensão, responde quem se sobrepõe, sem medir."""

    def _executar(self, linhas):
        cursor = MagicMock()
        cursor.fetchone.side_effect = [{"tem": False}, {"total": len(linhas)}]
        cursor.fetchall.return_value = linhas
        with patch.object(R, "conectar", return_value=_conexao(cursor)):
            return R.listar_sobreposicoes(ALVO, _usuario="TESTE")

    def test_vizinho_que_invade_aparece_sem_medida(self):
        achados = self._executar([
            {"id": ALVO, "nome": "Gleba A", "matricula": 1, "cor": "#f97316",
             "anel": _quadrado(0, 0), "tipo": "POLIGONO"},
            {"id": VIZINHO, "nome": "Gleba B", "matricula": 2, "cor": "#2563eb",
             "anel": _quadrado(0.005, 0.005), "tipo": "POLIGONO"},
        ])

        self.assertEqual(len(achados), 1)
        self.assertEqual(achados[0]["nome"], "Gleba B")
        # None, e não zero: zero significaria "não invadiu nada", e o que
        # este banco sabe dizer é "não sei quanto".
        self.assertIsNone(achados[0]["areaInvadidaM2"])
        self.assertIsNone(achados[0]["apenasEncosta"])

    def test_desenho_distante_nao_entra(self):
        achados = self._executar([
            {"id": ALVO, "nome": "Gleba A", "matricula": None, "cor": "#f97316",
             "anel": _quadrado(0, 0), "tipo": "POLIGONO"},
            {"id": VIZINHO, "nome": "Longe", "matricula": None, "cor": "#2563eb",
             "anel": _quadrado(50, 50), "tipo": "POLIGONO"},
        ])
        self.assertEqual(achados, [])

    def test_id_inexistente_da_404(self):
        with self.assertRaises(HTTPException) as erro:
            self._executar([])
        self.assertEqual(erro.exception.status_code, 404)


class TesteComPostgis(unittest.TestCase):
    """Com a extensão, a área invadida vem do banco."""

    def _executar(self, linhas, existe_alvo=True):
        cursor = MagicMock()
        cursor.fetchone.side_effect = [{"tem": True}, {"?column?": 1} if existe_alvo else None]
        cursor.fetchall.return_value = linhas
        with patch.object(R, "conectar", return_value=_conexao(cursor)):
            return R.listar_sobreposicoes(ALVO, _usuario="TESTE"), cursor

    def test_area_invadida_vem_do_banco(self):
        achados, _ = self._executar([
            {"id": VIZINHO, "nome": "Gleba B", "matricula": 2,
             "cor": "#2563eb", "area_invadida": 1234.5},
        ])

        self.assertEqual(achados[0]["areaInvadidaM2"], 1234.5)
        self.assertFalse(achados[0]["apenasEncosta"])

    def test_area_zero_e_apenas_divisa_comum(self):
        # Dois vizinhos que dividem cerca se cruzam numa linha, que não
        # tem área. Isso é o normal do acervo, não é invasão.
        achados, _ = self._executar([
            {"id": VIZINHO, "nome": "Vizinho", "matricula": None,
             "cor": "#16a34a", "area_invadida": 0.0},
        ])

        self.assertTrue(achados[0]["apenasEncosta"])

    def test_area_desprezivel_tambem_conta_como_divisa(self):
        # Meio centímetro quadrado é ruído de arredondamento do recorte,
        # não invasão que alguém vá alegar.
        achados, _ = self._executar([
            {"id": VIZINHO, "nome": "Vizinho", "matricula": None,
             "cor": "#16a34a", "area_invadida": 0.004},
        ])
        self.assertTrue(achados[0]["apenasEncosta"])

    def test_sem_sobreposicao_confere_se_o_alvo_existe(self):
        # A consulta com CROSS JOIN devolve vazio tanto quando não há
        # invasão quanto quando o id não existe; a rota precisa separar.
        achados, cursor = self._executar([], existe_alvo=True)
        self.assertEqual(achados, [])
        self.assertEqual(cursor.fetchone.call_count, 2)

    def test_sem_sobreposicao_e_sem_alvo_da_404(self):
        with self.assertRaises(HTTPException) as erro:
            self._executar([], existe_alvo=False)
        self.assertEqual(erro.exception.status_code, 404)

    def test_consulta_usa_a_funcao_da_migracao(self):
        _, cursor = self._executar([
            {"id": VIZINHO, "nome": "B", "matricula": None,
             "cor": "#2563eb", "area_invadida": 10.0},
        ])
        sql = cursor.execute.call_args_list[1].args[0]
        self.assertIn("aeri_anel_para_geometria", sql)
        self.assertIn("ST_Intersects", sql)
        # Sem CollectionExtract, uma interseção que devolve linha ou
        # coleção quebraria a medição de área.
        self.assertIn("ST_CollectionExtract", sql)


class TesteValidacaoDeEntrada(unittest.TestCase):
    def test_cor_fora_da_lista_vira_a_padrao(self):
        campos = R._validar_entrada({
            "nome": "Teste", "tipo": "POLIGONO", "anel": _quadrado(0, 0),
            "cor": "#000000; background:url(x)",
        })
        # Lista fechada, e não validação de formato: a cor vai para dentro
        # de um atributo style no desenho.
        self.assertEqual(campos["cor"], "#f97316")

    def test_matricula_com_ponto_e_aceita(self):
        campos = R._validar_entrada({
            "nome": "Teste", "anel": _quadrado(0, 0), "matricula": "10.151"})
        self.assertEqual(campos["matricula"], 10151)

    def test_nome_vazio_e_recusado(self):
        with self.assertRaises(HTTPException) as erro:
            R._validar_entrada({"nome": "  ", "anel": _quadrado(0, 0)})
        self.assertEqual(erro.exception.status_code, 422)

    def test_area_e_perimetro_saem_calculados(self):
        campos = R._validar_entrada({"nome": "T", "anel": _quadrado(0, 0)})
        self.assertGreater(campos["area_m2"], 0)
        self.assertGreater(campos["perimetro_m"], 0)

    def test_linha_nao_tem_area(self):
        campos = R._validar_entrada(
            {"nome": "T", "tipo": "LINHA", "anel": [[0, 0], [0.01, 0]]})
        self.assertEqual(campos["area_m2"], 0.0)
        self.assertGreater(campos["perimetro_m"], 0)


if __name__ == "__main__":
    unittest.main()
