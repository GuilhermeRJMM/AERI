import base64
import shutil
import subprocess
import unittest
from pathlib import Path


RAIZ = Path(__file__).parents[1]


@unittest.skipUnless(shutil.which("node"), "Node.js não está disponível")
class TesteContratoFrontendApi(unittest.TestCase):
    def test_preserva_objeto_que_possui_campo_resultado(self):
        fonte = (RAIZ / "backend/static/js/api.js").read_bytes()
        modulo = "data:text/javascript;base64," + base64.b64encode(fonte).decode("ascii")
        script = f"""
globalThis.window = {{dispatchEvent() {{}}}};
globalThis.CustomEvent = class {{}};
globalThis.fetch = async () => new Response(JSON.stringify({{
    resultado: 'NEGATIVA PARA ÔNUS',
    atos: [{{codigo: 'R.01'}}],
}}), {{status: 200, headers: {{'content-type': 'application/json'}}}});
const {{requisicaoAeri}} = await import({modulo!r});
const dados = await requisicaoAeri('/teste');
if (typeof dados !== 'object' || dados.resultado !== 'NEGATIVA PARA ÔNUS' || dados.atos.length !== 1) {{
    throw new Error('A resposta da análise foi desembrulhada indevidamente.');
}}
"""
        resultado = subprocess.run(
            [shutil.which("node"), "--input-type=module", "--eval", script],
            cwd=RAIZ,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        self.assertEqual(0, resultado.returncode, resultado.stderr)


if __name__ == "__main__":
    unittest.main()
