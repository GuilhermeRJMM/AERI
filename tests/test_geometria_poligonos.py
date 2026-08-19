"""Geometria do módulo Polígonos, aferida contra valores independentes.

Duas coisas são verificadas aqui. A primeira é que as contas batem com
referências externas (integração numérica, ida e volta UTM, constantes
conhecidas do WGS84). A segunda é que a versão em JavaScript, que a
interface usa para mostrar a medida enquanto o usuário arrasta, dá o
mesmo número que a versão em Python, que é a que grava no banco -- se as
duas divergirem, o conferente vê uma área na tela e outra no documento.
"""
import json
import math
import random
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from backend.app.servicos import poligonos as P


RAIZ = Path(__file__).resolve().parent.parent
MODULO_JS = RAIZ / "backend" / "static" / "js" / "mapa" / "geometria.js"


def _poligonos_de_amostra():
    """Casos reais em forma e tamanho: lote urbano, chácara, fazenda."""
    random.seed(20260819)
    amostras = [
        # quadrado de 220 m = 1 alqueire goiano exato
        [[-49.1, -17.73], [-49.09792, -17.73], [-49.09792, -17.72801], [-49.1, -17.72801]],
        # lote urbano de 12 x 30
        [[-49.1003, -17.7305], [-49.10019, -17.7305],
         [-49.10019, -17.73077], [-49.1003, -17.73077]],
        # triângulo
        [[-49.2, -17.8], [-49.1, -17.8], [-49.15, -17.7]],
    ]
    # polígonos irregulares em volta de Morrinhos
    for _ in range(12):
        centro_lon = random.uniform(-49.4, -48.8)
        centro_lat = random.uniform(-17.9, -17.5)
        raio = random.uniform(0.002, 0.05)
        lados = random.randint(3, 14)
        amostras.append([
            [
                centro_lon + raio * math.cos(2 * math.pi * i / lados) * random.uniform(0.6, 1.4),
                centro_lat + raio * math.sin(2 * math.pi * i / lados) * random.uniform(0.6, 1.4),
            ]
            for i in range(lados)
        ])
    return amostras


class TesteAreaContraReferencia(unittest.TestCase):
    def test_area_bate_com_integracao_numerica(self):
        # Integra a área elipsoidal em faixas finas de latitude; é um
        # cálculo independente da fórmula autálica que o serviço usa.
        def por_integracao(lat0, lat1, dlon, faixas=40000):
            total = 0.0
            for i in range(faixas):
                lat = math.radians(lat0 + (lat1 - lat0) * (i + 0.5) / faixas)
                dlat = math.radians((lat1 - lat0) / faixas)
                meridiano = P._A * (1 - P._E2) / (1 - P._E2 * math.sin(lat) ** 2) ** 1.5
                normal = P._A / math.sqrt(1 - P._E2 * math.sin(lat) ** 2)
                total += meridiano * dlat * normal * math.cos(lat) * math.radians(dlon)
            return total

        for lat0, lat1 in ((0, 1), (-18, -17)):
            with self.subTest(faixa=(lat0, lat1)):
                esperado = por_integracao(lat0, lat1, 1)
                obtido = P.area_m2([[0, lat0], [1, lat0], [1, lat1], [0, lat1]])
                self.assertLess(abs(obtido - esperado) / esperado, 1e-9)

    def test_superficie_da_esfera_autalica_e_a_do_elipsoide(self):
        # Área do elipsoide WGS84, valor tabelado: 510.065.621,7 km².
        superficie = 4 * math.pi * P._RAIO_AUTALICO ** 2 / 1e6
        self.assertAlmostEqual(superficie, 510_065_621.7, delta=1.0)

    def test_alqueire_goiano(self):
        # 220 m x 220 m = 48.400 m², a definição do alqueire da região.
        lado = 220.0
        lat0, lon0 = -17.73, -49.10
        dlat = lado / 110574.0
        dlon = lado / (111319.5 * math.cos(math.radians(lat0)))
        area = P.area_m2([
            [lon0, lat0], [lon0 + dlon, lat0],
            [lon0 + dlon, lat0 + dlat], [lon0, lat0 + dlat],
        ])
        self.assertAlmostEqual(area, 48400, delta=80)  # 0,17% da aproximação plana


class TesteDistanciaEAzimute(unittest.TestCase):
    def test_graus_no_equador(self):
        self.assertAlmostEqual(P.distancia_m((0, 0), (0, 1)), 110574.4, delta=0.5)
        self.assertAlmostEqual(P.distancia_m((0, 0), (1, 0)), 111319.5, delta=0.5)

    def test_azimutes_cardeais(self):
        self.assertAlmostEqual(P.azimute_graus((0, 0), (0, 1)), 0.0, places=6)
        self.assertAlmostEqual(P.azimute_graus((0, 0), (1, 0)), 90.0, places=6)
        self.assertAlmostEqual(P.azimute_graus((0, 1), (0, 0)), 180.0, places=6)

    def test_distancia_e_simetrica(self):
        a, b = (-49.10, -17.73), (-49.05, -17.70)
        self.assertAlmostEqual(P.distancia_m(a, b), P.distancia_m(b, a), places=6)


class TesteUtm(unittest.TestCase):
    def test_meridiano_central_volta_nele_mesmo(self):
        for fuso, meridiano in ((21, -57.0), (22, -51.0), (23, -45.0)):
            with self.subTest(fuso=fuso):
                lon, lat = P.utm_para_geografica(500000.0, 10000000.0, fuso, True)
                self.assertAlmostEqual(lon, meridiano, places=9)
                self.assertAlmostEqual(lat, 0.0, places=9)

    def test_ida_e_volta_fecha_em_milimetros(self):
        random.seed(11)
        pior = 0.0
        for _ in range(400):
            lon = random.uniform(-53.0, -46.0)
            lat = random.uniform(-19.5, -12.5)
            utm = P.geografica_para_utm(lon, lat)
            volta = P.utm_para_geografica(
                utm["leste"], utm["norte"], utm["fuso"], True)
            pior = max(pior, P.distancia_m((lon, lat), volta))
        self.assertLess(pior, 0.001, f"pior erro de ida e volta: {pior * 1000:.3f} mm")

    def test_morrinhos_cai_no_fuso_22(self):
        self.assertEqual(P.fuso_de(-49.1), 22)


class TesteGeodesicoDireto(unittest.TestCase):
    """Vincenty direto: a conta do memorial descritivo.

    "Do vértice P-01, segue com azimute X e distância Y até o P-02".
    Ele é o que permite lançar o memorial na tabela de lados.
    """

    def test_ida_e_volta_contra_o_inverso(self):
        random.seed(3)
        pior_distancia = pior_azimute = 0.0
        for _ in range(500):
            origem = (random.uniform(-53.0, -46.0), random.uniform(-19.5, -12.5))
            azimute = random.uniform(0, 360)
            distancia = random.uniform(1, 20000)
            destino = P.destino_geodesico(origem, azimute, distancia)
            pior_distancia = max(
                pior_distancia, abs(P.distancia_m(origem, destino) - distancia))
            diferenca = abs(
                (P.azimute_graus(origem, destino) - azimute + 180) % 360 - 180)
            pior_azimute = max(pior_azimute, diferenca)
        self.assertLess(pior_distancia, 0.001, f"{pior_distancia * 1000:.4f} mm")
        self.assertLess(pior_azimute * 3600, 0.01, f"{pior_azimute * 3600:.4f}\"")

    def test_azimutes_cardeais_saem_onde_deviam(self):
        origem = (-49.10, -17.73)
        norte = P.destino_geodesico(origem, 0, 1000)
        leste = P.destino_geodesico(origem, 90, 1000)
        self.assertAlmostEqual(norte[0], origem[0], places=9)   # não muda a longitude
        self.assertGreater(norte[1], origem[1])                 # sobe
        self.assertGreater(leste[0], origem[0])                 # vai para a direita
        self.assertAlmostEqual(leste[1], origem[1], places=5)

    def test_distancia_zero_fica_no_lugar(self):
        origem = (-49.10, -17.73)
        self.assertEqual(P.destino_geodesico(origem, 137, 0), origem)


class TesteSobreposicao(unittest.TestCase):
    def test_quadrados_que_se_invadem(self):
        a = [[0, 0], [2, 0], [2, 2], [0, 2]]
        b = [[1, 1], [3, 1], [3, 3], [1, 3]]
        self.assertTrue(P.se_sobrepoem(a, b))

    def test_quadrados_separados(self):
        a = [[0, 0], [1, 0], [1, 1], [0, 1]]
        b = [[5, 5], [6, 5], [6, 6], [5, 6]]
        self.assertFalse(P.se_sobrepoem(a, b))

    def test_um_dentro_do_outro_sem_cruzar_aresta(self):
        # Nenhuma aresta se cruza, mas há invasão total.
        fora = [[0, 0], [10, 0], [10, 10], [0, 10]]
        dentro = [[2, 2], [3, 2], [3, 3], [2, 3]]
        self.assertTrue(P.se_sobrepoem(fora, dentro))
        self.assertTrue(P.se_sobrepoem(dentro, fora))

    def test_vizinhos_que_so_encostam_na_divisa(self):
        # Divisa comum conta como sobreposição: numa qualificação, dois
        # memoriais que compartilham linha precisam ser olhados.
        a = [[0, 0], [1, 0], [1, 1], [0, 1]]
        b = [[1, 0], [2, 0], [2, 1], [1, 1]]
        self.assertTrue(P.se_sobrepoem(a, b))


class TesteLeituraDeCoordenadas(unittest.TestCase):
    def test_decimal_em_latitude_longitude(self):
        pontos = P.interpretar_coordenadas("-17,7305 -49,1003\n-17,7310 -49,1010")
        self.assertEqual(len(pontos), 2)
        self.assertAlmostEqual(pontos[0][0], -49.1003, places=4)
        self.assertAlmostEqual(pontos[0][1], -17.7305, places=4)

    def test_gms_com_hemisferio(self):
        pontos = P.interpretar_coordenadas(
            "17°43'49.80\"S 49°06'01.08\"W 17°43'51.60\"S 49°06'03.60\"W")
        self.assertEqual(len(pontos), 2)
        self.assertAlmostEqual(pontos[0][1], -17.7305, places=4)
        self.assertAlmostEqual(pontos[0][0], -49.1003, places=4)

    def test_utm_com_fuso_e_banda(self):
        pontos = P.interpretar_coordenadas("22K 701473.14 8038668.23 22K 701500.00 8038700.00")
        self.assertEqual(len(pontos), 2)
        self.assertAlmostEqual(pontos[0][1], -17.7300, places=3)
        self.assertAlmostEqual(pontos[0][0], -49.1000, places=3)

    def test_texto_sem_coordenada_nao_inventa_ponto(self):
        self.assertEqual(P.interpretar_coordenadas("nenhum número aqui"), [])

    def test_cabecalho_declara_longitude_primeiro(self):
        # É o formato que o botão "Copiar coordenadas" produz. Sem honrar
        # o cabeçalho, o par seria lido como latitude/longitude e o imóvel
        # iria parar a milhares de quilômetros, sem aviso nenhum.
        pontos = P.interpretar_coordenadas(
            "# longitude, latitude\n-49.10030000, -17.73050000\n"
            "-49.09800000, -17.73100000")

        self.assertEqual(len(pontos), 2)
        self.assertAlmostEqual(pontos[0][0], -49.1003, places=6)
        self.assertAlmostEqual(pontos[0][1], -17.7305, places=6)

    def test_cabecalho_declara_latitude_primeiro(self):
        pontos = P.interpretar_coordenadas(
            "Latitude, Longitude\n-17.7305, -49.1003")

        self.assertAlmostEqual(pontos[0][0], -49.1003, places=6)
        self.assertAlmostEqual(pontos[0][1], -17.7305, places=6)

    def test_ida_e_volta_pelo_texto_copiado(self):
        # Copiar e colar de volta tem de devolver o mesmo desenho.
        anel = [[-49.1003, -17.7305], [-49.0980, -17.7305], [-49.0980, -17.7280]]
        copiado = "# longitude, latitude\n" + "\n".join(
            f"{lon:.8f}, {lat:.8f}" for lon, lat in anel)

        voltou = P.interpretar_coordenadas(copiado)

        self.assertEqual(len(voltou), len(anel))
        for original, devolvido in zip(anel, voltou):
            self.assertAlmostEqual(original[0], devolvido[0], places=7)
            self.assertAlmostEqual(original[1], devolvido[1], places=7)

    def test_sem_cabecalho_mantem_o_palpite_antigo(self):
        # Quem cola do Google Maps não escreve rótulo; o comportamento
        # anterior continua valendo para esse caso.
        pontos = P.interpretar_coordenadas("-17,7305 -49,1003")
        self.assertAlmostEqual(pontos[0][0], -49.1003, places=4)
        self.assertAlmostEqual(pontos[0][1], -17.7305, places=4)


class TesteValidacao(unittest.TestCase):
    def test_poligono_exige_tres_vertices(self):
        with self.assertRaises(ValueError):
            P.validar_anel([[0, 0], [1, 1]], "POLIGONO")

    def test_vertice_de_fechamento_repetido_e_descartado(self):
        anel = P.validar_anel([[0, 0], [1, 0], [1, 1], [0, 0]], "POLIGONO")
        self.assertEqual(len(anel), 3)

    def test_coordenada_fora_da_faixa_e_ignorada(self):
        anel = P.validar_anel(
            [[0, 0], [1, 0], [999, 0], [1, 1]], "POLIGONO")
        self.assertEqual(len(anel), 3)

    def test_desenho_gigante_e_recusado(self):
        with self.assertRaises(ValueError):
            P.validar_anel([[i / 100000, 0] for i in range(10_001)], "POLIGONO")


@unittest.skipIf(shutil.which("node") is None, "node não disponível")
class TesteJavaScriptBateComPython(unittest.TestCase):
    """A medida mostrada na tela tem de ser a medida gravada no banco."""

    def test_area_perimetro_e_azimute_coincidem(self):
        amostras = _poligonos_de_amostra()
        script = f"""
        import {{areaM2, perimetroM, azimuteGraus, distanciaM}}
            from {json.dumps(MODULO_JS.as_uri())};
        const casos = JSON.parse(process.argv[2]);
        console.log(JSON.stringify(casos.map(anel => ({{
            area: areaM2(anel),
            perimetro: perimetroM(anel, true),
            azimute: azimuteGraus(anel[0], anel[1]),
            distancia: distanciaM(anel[0], anel[1]),
        }}))));
        """
        with tempfile.TemporaryDirectory() as pasta:
            arquivo = Path(pasta) / "conferir.mjs"
            arquivo.write_text(script, encoding="utf-8")
            saida = subprocess.run(
                ["node", str(arquivo), json.dumps(amostras)],
                capture_output=True, text=True, timeout=60, check=True,
            )
        do_js = json.loads(saida.stdout)

        self.assertEqual(len(do_js), len(amostras))
        for indice, (anel, js) in enumerate(zip(amostras, do_js)):
            with self.subTest(poligono=indice):
                area = P.area_m2(anel)
                perimetro = P.perimetro_m(anel, fechado=True)
                # Tolerância relativa de 1e-9: o que sobra é o último bit
                # do float, não diferença de fórmula.
                self.assertLess(abs(js["area"] - area) / max(area, 1), 1e-9)
                self.assertLess(abs(js["perimetro"] - perimetro) / max(perimetro, 1), 1e-9)
                self.assertAlmostEqual(
                    js["azimute"], P.azimute_graus(anel[0], anel[1]), places=9)
                self.assertAlmostEqual(
                    js["distancia"], P.distancia_m(anel[0], anel[1]), places=6)


if __name__ == "__main__":
    unittest.main()


@unittest.skipIf(shutil.which("node") is None, "node não disponível")
class TesteGeodesicoDiretoNoJavaScript(unittest.TestCase):
    """A tabela de lados usa a versão JS; ela tem de andar junto."""

    def test_destino_coincide_com_o_python(self):
        random.seed(29)
        casos = [
            [random.uniform(-53.0, -46.0), random.uniform(-19.5, -12.5),
             random.uniform(0, 360), random.uniform(1, 20000)]
            for _ in range(60)
        ]
        script = f"""
        import {{destinoGeodesico}} from {json.dumps(MODULO_JS.as_uri())};
        const casos = JSON.parse(process.argv[2]);
        console.log(JSON.stringify(
            casos.map(([lon, lat, az, d]) => destinoGeodesico([lon, lat], az, d))));
        """
        with tempfile.TemporaryDirectory() as pasta:
            arquivo = Path(pasta) / "d.mjs"
            arquivo.write_text(script, encoding="utf-8")
            saida = subprocess.run(
                ["node", str(arquivo), json.dumps(casos)],
                capture_output=True, text=True, encoding="utf-8",
                timeout=60, check=True,
            )
        do_js = json.loads(saida.stdout)

        for indice, (caso, js) in enumerate(zip(casos, do_js)):
            with self.subTest(caso=indice):
                lon, lat, azimute, distancia = caso
                esperado = P.destino_geodesico((lon, lat), azimute, distancia)
                # Milímetro: o que sobra é o último bit do float.
                self.assertLess(P.distancia_m(esperado, js), 0.001)
