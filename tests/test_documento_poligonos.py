"""Testes da planta e memorial imprimíveis do módulo Polígonos."""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from backend.app.servicos.poligonos import fuso_de, geografica_para_utm


RAIZ = Path(__file__).resolve().parent.parent
MODULO = RAIZ / "backend" / "static" / "js" / "mapa" / "documento.js"


def _dados(nome="Fazenda Teste"):
    anel = [
        [-49.1003, -17.7305], [-49.0999, -17.7305],
        [-49.0999, -17.7308], [-49.1003, -17.7308],
    ]
    fuso = fuso_de(anel[0][0])
    vertices = [
        {"ordem": i + 1, **geografica_para_utm(lon, lat, fuso)}
        for i, (lon, lat) in enumerate(anel)
    ]
    return {
        "nome": nome,
        "matricula": "10.151",
        "anel": anel,
        "utm": {"fuso": fuso, "vertices": vertices},
        "dadosMapa": {
            "municipio": "Morrinhos", "uf": "GO",
            "proprietarios": "Guilherme de Teste", "documentos": "12345678901",
            "memorial": {
                "lote": "06", "quadra": "02", "logradouro": "Rua São José",
                "estilo": "CONFRONTACOES",
                "lados": [
                    {"posicao": "FRENTE", "confrontante": "Rua A"},
                    {"posicao": "DIREITO", "confrontante": "Lote 7"},
                    {"posicao": "FUNDOS", "confrontante": "Chácara B"},
                    {"posicao": "ESQUERDO", "confrontante": "Lote 5"},
                ],
            },
        },
    }


@unittest.skipIf(shutil.which("node") is None, "node não disponível")
class TesteDocumentoPoligonos(unittest.TestCase):
    def _gerar(self, dados):
        script = f"""
        import {{montarDocumentoPoligonos}} from {json.dumps(MODULO.as_uri())};
        console.log(montarDocumentoPoligonos(JSON.parse(process.argv[2])));
        """
        with tempfile.TemporaryDirectory() as pasta:
            arquivo = Path(pasta) / "gerar.mjs"
            arquivo.write_text(script, encoding="utf-8")
            resultado = subprocess.run(
                ["node", str(arquivo), json.dumps(dados, ensure_ascii=False)],
                capture_output=True, text=True, encoding="utf-8", timeout=60,
                check=True,
            )
        return resultado.stdout

    def test_gera_planta_rosa_dos_ventos_e_texto_corridao_das_medidas(self):
        html = self._gerar(_dados())

        self.assertEqual(html.count('<article class="poligonos-folha'), 2)
        self.assertIn('class="poligonos-folha poligonos-folha-planta"', html)
        self.assertIn('class="poligonos-folha poligonos-folha-memorial"', html)
        self.assertIn('class="rosa-ventos"', html)
        self.assertIn('>Norte da</text>', html)
        self.assertIn('>quadrícula</text>', html)
        self.assertIn('do vértice P-01 ao vértice P-02', html)
        self.assertIn('confrontando com Rua A', html)
        self.assertIn('metros pela frente', html)
        self.assertIn('Quadro de vértices', html)
        self.assertIn('1:', html)

    def test_dado_de_usuario_e_escapado_e_confrontante_ausente_e_sinalizado(self):
        dados = _dados('<script>alert("x")</script>')
        dados["dadosMapa"]["memorial"]["lados"][0]["confrontante"] = ""
        html = self._gerar(dados)

        self.assertNotIn('<script>', html)
        self.assertIn('&lt;script&gt;', html)
        self.assertIn('Conferir confrontantes', html)
        self.assertIn('P-01–P-02', html)

    def test_coordenadas_svg_usam_ponto_decimal(self):
        html = self._gerar(_dados())
        pontos = html.split('points="', 1)[1].split('"', 1)[0].split()

        self.assertEqual(len(pontos), 4)
        for ponto in pontos:
            leste, norte = ponto.split(',')
            self.assertRegex(leste, r"^-?\d+\.\d{3}$")
            self.assertRegex(norte, r"^-?\d+\.\d{3}$")


if __name__ == "__main__":
    unittest.main()
