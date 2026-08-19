"""Regras do Mapa do Registro de Imóveis aplicadas aos dados do imóvel.

O item 5.12.1 do Manual Técnico Operacional é explícito: "acentos e
caracteres especiais não devem ser usados no cadastro de parcelas", o
endereço vai sem abreviações e a UF sempre em duas letras. O item 3.4.5.3
fecha a lista de motivos de envio.

A normalização existe duas vezes: em Python, que grava, e em JavaScript,
que monta o KML de um rascunho sem passar pelo servidor. As duas têm de
dar exatamente o mesmo resultado, senão o arquivo baixado sai diferente
do que ficou no banco.
"""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from backend.app.servicos import poligonos as P


RAIZ = Path(__file__).resolve().parent.parent
MODULO_KML = RAIZ / "backend" / "static" / "js" / "mapa" / "kml.js"

CASOS = [
    {"cns": "12.345-6", "municipio": "Morrinhos", "uf": "go",
     "proprietarios": "João da Silva , Maria Souza,",
     "documentos": "123.456.789-01, 98.765.432/0001-10",
     "endereco": "R. São Paulo", "numero": "123", "cep": "75.650-000",
     "motivo": "Desmembramento"},
    {"uf": "XX", "motivo": "Qualquer coisa", "endereco": "Av. Brasil"},
    {"municipio": "São José do Açaí", "endereco": "Rod. BR-153, km 10"},
    {"proprietarios": "  ,  ,  ", "documentos": "abc, 111"},
    {"endereco": "Pç. da Matriz, Cj. 4"},
    {"endereco": "Estr. do Cerrado / Trav. São Pedro"},
    {"endereco": "Rua Av Maria", "cns": "abc"},
    {},
]


class TesteRegrasDoManual(unittest.TestCase):
    def test_acentos_sao_removidos(self):
        self.assertEqual(
            P.sem_acentos("São José do Açaí — Fazenda Nº 3"),
            "Sao Jose do Acai Fazenda N 3")

    def test_abreviacoes_de_logradouro_viram_por_extenso(self):
        self.assertEqual(
            P.expandir_abreviacoes("R. das Flores"), "Rua das Flores")
        self.assertEqual(
            P.expandir_abreviacoes("Rod. BR-153"), "Rodovia BR-153")
        self.assertEqual(
            P.expandir_abreviacoes("Av. Brasil"), "Avenida Brasil")

    def test_expansao_nao_reintroduz_acento(self):
        # A expansão roda depois da remoção de acentos. Se a substituição
        # fosse "Praça", o acento voltaria justamente no campo em que o
        # manual proíbe.
        saida = P.validar_dados_mapa({"endereco": "Pç. da Matriz"})["endereco"]
        self.assertEqual(saida, "Praca da Matriz")

    def test_abreviacao_sem_ponto_nao_e_expandida(self):
        # "Av" pode ser parte de nome próprio; só a forma abreviada com
        # ponto é trocada.
        self.assertEqual(
            P.expandir_abreviacoes("Rua Av Maria"), "Rua Av Maria")

    def test_uf_fora_da_lista_e_descartada(self):
        # Duas letras conforme ABNT/NBR ISO 3166-2:BR. Inventar sigla é
        # pior do que deixar em branco: o Mapa recusaria depois.
        self.assertEqual(P.validar_dados_mapa({"uf": "go"})["uf"], "GO")
        self.assertEqual(P.validar_dados_mapa({"uf": "XX"})["uf"], "")

    def test_motivo_fora_da_lista_do_manual_e_descartado(self):
        self.assertEqual(
            P.validar_dados_mapa({"motivo": "Unificação"})["motivo"], "Unificação")
        self.assertEqual(P.validar_dados_mapa({"motivo": "Outro"})["motivo"], "")

    def test_documentos_ficam_so_com_digitos(self):
        saida = P.validar_dados_mapa(
            {"documentos": "123.456.789-01, 98.765.432/0001-10"})
        self.assertEqual(saida["documentos"], "12345678901, 98765432000110")

    def test_lista_vazia_nao_vira_virgulas_soltas(self):
        self.assertEqual(P.validar_dados_mapa({"proprietarios": " , , "})["proprietarios"], "")

    def test_devolve_sempre_a_estrutura_completa(self):
        # Campo ausente e campo vazio precisam sair iguais, para o KML ter
        # sempre a mesma forma.
        vazio = P.validar_dados_mapa({})
        self.assertEqual(set(vazio), {
            "cns", "municipio", "uf", "proprietarios", "documentos",
            "endereco", "numero", "cep", "motivo"})
        self.assertTrue(all(v == "" for v in vazio.values()))

    def test_entrada_invalida_nao_derruba(self):
        for entrada in (None, "texto", 42, []):
            with self.subTest(entrada=entrada):
                self.assertEqual(P.validar_dados_mapa(entrada)["uf"], "")


class TestePontoCentral(unittest.TestCase):
    def test_centroide_de_quadrado_cai_exatamente_no_meio(self):
        # Sem tratar o cancelamento de ponto flutuante, este caso errava
        # mais de um metro.
        quad = [[-49.1003, -17.7305], [-49.0999, -17.7305],
                [-49.0999, -17.7308], [-49.1003, -17.7308]]
        lon, lat = P.centroide(quad)
        self.assertAlmostEqual(lon, -49.1001, places=10)
        self.assertAlmostEqual(lat, -17.73065, places=10)

    def test_centroide_de_area_difere_da_media_dos_vertices(self):
        # Numa forma em L a média dos vértices cai fora do centro real.
        ele = [[0, 0], [3, 0], [3, 1], [1, 1], [1, 3], [0, 3]]
        lon, lat = P.centroide(ele)
        media_lon = sum(p[0] for p in ele) / len(ele)
        self.assertAlmostEqual(lon, 1.1, places=9)
        self.assertNotAlmostEqual(lon, media_lon, places=2)

    def test_poligono_degenerado_nao_estoura(self):
        # Três pontos colineares têm área zero; cair na média é melhor do
        # que dividir por zero.
        lon, lat = P.centroide([[0, 0], [1, 1], [2, 2]])
        self.assertAlmostEqual(lon, 1.0, places=9)


@unittest.skipIf(shutil.which("node") is None, "node não disponível")
class TesteJavaScriptBateComPython(unittest.TestCase):
    def test_normalizacao_coincide_nos_dois_lados(self):
        script = f"""
        import {{normalizarDadosMapa}} from {json.dumps(MODULO_KML.as_uri())};
        const casos = JSON.parse(process.argv[2]);
        console.log(JSON.stringify(casos.map(normalizarDadosMapa)));
        """
        with tempfile.TemporaryDirectory() as pasta:
            arquivo = Path(pasta) / "n.mjs"
            arquivo.write_text(script, encoding="utf-8")
            saida = subprocess.run(
                ["node", str(arquivo), json.dumps(CASOS)],
                capture_output=True, text=True, encoding="utf-8",
                timeout=60, check=True,
            )
        do_js = json.loads(saida.stdout)

        for indice, (entrada, js) in enumerate(zip(CASOS, do_js)):
            with self.subTest(caso=indice, entrada=entrada):
                self.assertEqual(js, P.validar_dados_mapa(entrada))


if __name__ == "__main__":
    unittest.main()
