"""O KML exportado tem de atender ao padrão do Mapa do Registro de Imóveis.

Duas exigências vêm do Manual Técnico Operacional do Mapa, item 3.4.3:
o polígono precisa estar fechado, e as coordenadas precisam ser
geográficas em SAD69 ou SIRGAS 2000. A terceira vem do Manual da API de
Envio de Polígonos, item 6: a tabela de 34 atributos do imóvel.

Um arquivo que desrespeite qualquer uma delas não é recusado com erro
claro -- costuma ser aceito e ficar errado no mapa, ou ser devolvido dias
depois pelo administrador. Daí valer o teste.
"""
import json
import shutil
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


RAIZ = Path(__file__).resolve().parent.parent
MODULO_KML = RAIZ / "backend" / "static" / "js" / "mapa" / "kml.js"
KML_NS = {"k": "http://www.opengis.net/kml/2.2"}

# Item 6 do Manual da API, na ordem e grafia publicadas.
CAMPOS_DO_MANUAL = [
    "MATRICULA", "DAT_MAT", "LIV_MAT", "FOL_MAT", "TRANSCRI", "CNM", "CNS",
    "ENDERECO", "NUMERO", "CEP", "MUNICIPIO", "UF", "NOME_PROP", "CPF_CNPJ",
    "CONF_MAT", "CONF_NOM", "REL_JUR", "DAT_INI", "DAT_FIM", "PER_REL",
    "NOME_IMO", "AREA_HA", "AREA_M2", "PERIM_M", "PERIM_KM", "CCIR_SNCR",
    "SIGEF", "SNCI", "CIB_NIRF", "ITBI", "CAR", "RIP", "CIF", "CLASSIFICA",
]

# Lote urbano em Morrinhos. Conferido: esta sequência é ANTI-HORÁRIA,
# que já é o sentido que o KML pede para o contorno externo.
ANEL_ANTI_HORARIO = [
    [-49.1003, -17.7305],
    [-49.1003, -17.7308],
    [-49.0999, -17.7308],
    [-49.0999, -17.7305],
]
# O mesmo lote percorrido ao contrário -- é o caso que exercita a
# inversão. Desenhar no sentido horário é tão provável quanto no outro:
# depende de para que lado a pessoa clicou.
ANEL_HORARIO = list(reversed(ANEL_ANTI_HORARIO))


def _gerar(dados: dict) -> str:
    script = f"""
    import {{montarKml}} from {json.dumps(MODULO_KML.as_uri())};
    process.stdout.write(montarKml(JSON.parse(process.argv[2])));
    """
    with tempfile.TemporaryDirectory() as pasta:
        arquivo = Path(pasta) / "gerar.mjs"
        arquivo.write_text(script, encoding="utf-8")
        saida = subprocess.run(
            ["node", str(arquivo), json.dumps(dados)],
            capture_output=True, text=True, encoding="utf-8", timeout=60, check=True,
        )
    return saida.stdout


@unittest.skipIf(shutil.which("node") is None, "node não disponível")
class TesteKmlDoMapa(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kml = _gerar({
            "nome": "Fazenda Boa Vista & Cia <teste>",
            "matricula": "10.151",
            "observacao": "conferência",
            "anel": ANEL_HORARIO,
            "tipo": "POLIGONO",
        })
        cls.arvore = ET.fromstring(cls.kml)

    def test_e_xml_valido_no_namespace_do_kml(self):
        self.assertTrue(self.arvore.tag.endswith("}kml"))
        self.assertIn("opengis.net/kml/2.2", self.arvore.tag)

    def _anel(self):
        texto = self.arvore.find(
            ".//k:Polygon/k:outerBoundaryIs/k:LinearRing/k:coordinates", KML_NS).text
        return [tuple(map(float, t.split(",")))[:2] for t in texto.split()]

    def test_o_poligono_esta_fechado(self):
        # Manual Técnico 3.4.3: "o sistema aceita apenas polígonos
        # fechados". O desenho na tela não repete o primeiro vértice.
        anel = self._anel()
        self.assertEqual(anel[0], anel[-1])
        self.assertEqual(len(anel), len(ANEL_HORARIO) + 1)

    def test_contorno_externo_sai_em_sentido_anti_horario(self):
        anel = self._anel()[:-1]
        area = sum(
            anel[i][0] * anel[(i + 1) % len(anel)][1]
            - anel[(i + 1) % len(anel)][0] * anel[i][1]
            for i in range(len(anel))
        ) / 2
        self.assertGreater(area, 0, "o anel externo do KML deve ser anti-horário")

    def test_coordenadas_em_longitude_latitude_altitude(self):
        texto = self.arvore.find(".//k:coordinates", KML_NS).text
        primeiro = texto.split()[0].split(",")
        self.assertEqual(len(primeiro), 3, "KML exige lon,lat,alt")
        longitude, latitude = float(primeiro[0]), float(primeiro[1])
        # Em Morrinhos a longitude é ~-49 e a latitude ~-17. Trocar a
        # ordem jogaria o imóvel para o oceano Índico sem nenhum erro.
        self.assertAlmostEqual(longitude, -49.1003, places=4)
        self.assertAlmostEqual(latitude, -17.7305, places=4)

    def test_precisao_das_coordenadas_atende_a_exigida(self):
        # O manual exige precisão posicional de 8 cm para vértice urbano;
        # 8 casas decimais dão ~1 mm.
        texto = self.arvore.find(".//k:coordinates", KML_NS).text
        for termo in texto.split():
            lon, lat, _alt = termo.split(",")
            self.assertEqual(len(lon.split(".")[1]), 8)
            self.assertEqual(len(lat.split(".")[1]), 8)

    def test_traz_os_34_atributos_do_manual_na_ordem(self):
        nomes = [
            d.get("name")
            for d in self.arvore.findall(".//k:ExtendedData/k:Data", KML_NS)
        ]
        self.assertEqual(nomes, CAMPOS_DO_MANUAL)

    def _valor(self, campo):
        for d in self.arvore.findall(".//k:ExtendedData/k:Data", KML_NS):
            if d.get("name") == campo:
                return (d.find("k:value", KML_NS).text or "").strip()
        return None

    def test_classificacao_e_categoria_c(self):
        # Categoria C do manual: "desenho em imagem de satélite ou google
        # earth". Declarar A ou B afirmaria certificação ou levantamento
        # topográfico que este módulo não faz.
        self.assertEqual(self._valor("CLASSIFICA"), "3")

    def test_matricula_vai_so_com_digitos(self):
        self.assertEqual(self._valor("MATRICULA"), "10151")

    def test_area_e_perimetro_vao_preenchidos_e_coerentes(self):
        area_m2 = float(self._valor("AREA_M2"))
        area_ha = float(self._valor("AREA_HA"))
        perim_m = float(self._valor("PERIM_M"))
        perim_km = float(self._valor("PERIM_KM"))

        self.assertAlmostEqual(area_ha, area_m2 / 10000, places=3)
        self.assertAlmostEqual(perim_km, perim_m / 1000, places=3)
        # Lote de ~42 x 33 m: ordem de grandeza de mil e poucos metros²
        self.assertGreater(area_m2, 500)
        self.assertLess(area_m2, 5000)

    def test_campos_que_o_aeri_nao_conhece_vao_vazios_e_nao_ausentes(self):
        # Vazio e presente é diferente de ausente: quem recebe o arquivo
        # enxerga a estrutura inteira e sabe o que falta completar.
        for campo in ("CNS", "MUNICIPIO", "UF", "NOME_PROP", "CAR", "SIGEF"):
            with self.subTest(campo=campo):
                self.assertEqual(self._valor(campo), "")

    def test_caractere_especial_do_nome_nao_quebra_o_xml(self):
        # "&" e "<" no nome do imóvel produziriam XML inválido sem escape.
        nome = self.arvore.find(".//k:Placemark/k:name", KML_NS).text
        self.assertEqual(nome, "Fazenda Boa Vista & Cia <teste>")

    def test_o_datum_vai_escrito_no_arquivo(self):
        # O Mapa aceita SAD69 ou SIRGAS 2000, que diferem em dezenas de
        # metros entre si. Deixar subentendido convida ao erro.
        descricao = self.arvore.find(".//k:Placemark/k:description", KML_NS).text
        self.assertIn("SIRGAS 2000", descricao)

    def test_anel_desenhado_ao_contrario_e_invertido(self):
        # Este é o teste que de fato exercita a inversão: a entrada é
        # horária e a saída tem de sair na ordem oposta à digitada.
        anel_saida = self._anel()[:-1]
        entrada = [tuple(p) for p in ANEL_HORARIO]
        self.assertNotEqual(
            anel_saida, entrada,
            "o anel horário deveria ter sido invertido, e saiu como entrou")
        self.assertEqual(anel_saida, list(reversed(entrada)))

    def test_anel_ja_anti_horario_atravessa_sem_mudar(self):
        kml = _gerar({"nome": "Já anti-horário", "anel": ANEL_ANTI_HORARIO,
                      "tipo": "POLIGONO"})
        texto = ET.fromstring(kml).find(".//k:coordinates", KML_NS).text
        saida = [tuple(map(float, t.split(",")))[:2] for t in texto.split()][:-1]
        self.assertEqual(saida, [tuple(p) for p in ANEL_ANTI_HORARIO])

    def test_anel_ja_fechado_na_entrada_nao_duplica_vertice(self):
        kml = _gerar({
            "nome": "Já fechado", "anel": ANEL_HORARIO + [ANEL_HORARIO[0]],
            "tipo": "POLIGONO",
        })
        texto = ET.fromstring(kml).find(".//k:coordinates", KML_NS).text
        self.assertEqual(len(texto.split()), len(ANEL_HORARIO) + 1)


if __name__ == "__main__":
    unittest.main()
