import base64
import re
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

    def test_requisicao_de_escrita_recupera_csrf_antes_de_enviar(self):
        fonte = (RAIZ / "backend/static/js/api.js").read_bytes()
        modulo = "data:text/javascript;base64," + base64.b64encode(fonte).decode("ascii")
        script = f"""
globalThis.window = {{dispatchEvent() {{}}}};
globalThis.CustomEvent = class {{}};
const chamadas = [];
globalThis.fetch = async (url, opcoes = {{}}) => {{
    chamadas.push([url, opcoes.headers?.get?.('X-CSRF-Token') || '']);
    if (url === '/api/sessao') return new Response(JSON.stringify({{csrfToken: 'csrf-atual'}}), {{status: 200, headers: {{'content-type': 'application/json'}}}});
    return new Response(JSON.stringify({{ok: true}}), {{status: 200, headers: {{'content-type': 'application/json'}}}});
}};
const {{requisicaoAeri}} = await import({modulo!r});
await requisicaoAeri('/salvar', {{method: 'POST', body: '{{}}'}});
if (chamadas.length !== 2 || chamadas[0][0] !== '/api/sessao' || chamadas[1][1] !== 'csrf-atual') {{
    throw new Error('A escrita foi enviada sem recuperar o CSRF da sessão. ' + JSON.stringify(chamadas));
}}
"""
        resultado = subprocess.run(
            [shutil.which("node"), "--input-type=module", "--eval", script],
            cwd=RAIZ, capture_output=True, text=True, timeout=15, check=False,
        )
        self.assertEqual(0, resultado.returncode, resultado.stderr)

    def test_csrf_trocado_e_renovado_e_retentado_uma_vez(self):
        fonte = (RAIZ / "backend/static/js/api.js").read_bytes()
        modulo = "data:text/javascript;base64," + base64.b64encode(fonte).decode("ascii")
        script = f"""
globalThis.window = {{dispatchEvent() {{}}}};
globalThis.CustomEvent = class {{}};
const chamadas = [];
globalThis.fetch = async (url, opcoes = {{}}) => {{
    const token = opcoes.headers?.get?.('X-CSRF-Token') || '';
    chamadas.push([url, token]);
    if (url === '/api/sessao') return new Response(JSON.stringify({{csrfToken: 'csrf-novo'}}), {{status: 200, headers: {{'content-type': 'application/json'}}}});
    if (token === 'csrf-velho') return new Response(JSON.stringify({{detail: 'Validação de segurança expirada.'}}), {{status: 403, headers: {{'content-type': 'application/json'}}}});
    return new Response(JSON.stringify({{ok: true}}), {{status: 200, headers: {{'content-type': 'application/json'}}}});
}};
const {{definirCsrfToken, requisicaoAeri}} = await import({modulo!r});
definirCsrfToken('csrf-velho');
await requisicaoAeri('/salvar', {{method: 'POST', body: '{{}}'}});
if (chamadas.length !== 3 || chamadas[0][1] !== 'csrf-velho' || chamadas[1][0] !== '/api/sessao' || chamadas[2][1] !== 'csrf-novo') {{
    throw new Error('O CSRF vencido não foi renovado e retentado corretamente. ' + JSON.stringify(chamadas));
}}
"""
        resultado = subprocess.run(
            [shutil.which("node"), "--input-type=module", "--eval", script],
            cwd=RAIZ, capture_output=True, text=True, timeout=15, check=False,
        )
        self.assertEqual(0, resultado.returncode, resultado.stderr)

    def test_todos_os_modulos_compartilham_a_mesma_instancia_da_api(self):
        versoes = set()
        for arquivo in (RAIZ / "backend/static/js").glob("*.js"):
            versoes.update(re.findall(r"\./api\.js\?v=([^'\"]+)", arquivo.read_text(encoding="utf-8")))
        self.assertEqual({"20260824-csrf-v1"}, versoes)


if __name__ == "__main__":
    unittest.main()
