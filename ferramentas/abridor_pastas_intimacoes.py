from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import json
import os
import re


HOST = "127.0.0.1"
PORTA = 8767
PASTA_BASE = Path(
    r"T:\Setor Apoio\Setor Certidao\04. Processos Intimacao\02 - Processos SAEC\07 - 2026\02 - Agua. pagamento (emolu informados)"
)
PADRAO_PROTOCOLO = re.compile(r"^IN\d{8}C$")


class AbridorPastasHandler(BaseHTTPRequestHandler):
    def _enviar_html(self, status: int, titulo: str, mensagem: str, fechar: bool = False) -> None:
        script = "<script>setTimeout(() => window.close(), 350);</script>" if fechar else ""
        corpo = f"""<!doctype html>
<html lang="pt-br">
<head><meta charset="utf-8"><title>{titulo}</title></head>
<body style="font-family:Arial,sans-serif;padding:24px;color:#172033">
<h1 style="font-size:18px">{titulo}</h1>
<p>{mensagem}</p>
{script}
</body>
</html>""".encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def _enviar_json(self, status: int, dados: dict) -> None:
        corpo = json.dumps(dados, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.end_headers()
        self.wfile.write(corpo)

    def do_OPTIONS(self) -> None:
        self._enviar_json(200, {"ok": True})

    def do_GET(self) -> None:
        rota = urlparse(self.path)
        if rota.path == "/status":
            self._enviar_json(200, {"ok": True, "servico": "abridor-pastas-intimacoes"})
            return

        if rota.path != "/abrir":
            self._enviar_json(404, {"ok": False, "erro": "Rota não encontrada."})
            return

        parametros = parse_qs(rota.query)
        resposta_html = parametros.get("formato", [""])[0].lower() == "html"
        protocolo = parametros.get("protocolo", [""])[0].strip().upper()
        if not PADRAO_PROTOCOLO.fullmatch(protocolo):
            if resposta_html:
                self._enviar_html(400, "Protocolo inválido", "O protocolo informado não está no padrão esperado.")
                return
            self._enviar_json(400, {"ok": False, "erro": "Protocolo inválido."})
            return

        pasta = PASTA_BASE / protocolo
        try:
            os.startfile(str(pasta))
        except FileNotFoundError:
            try:
                pasta.mkdir(parents=True, exist_ok=True)
                os.startfile(str(pasta))
            except OSError as erro:
                if resposta_html:
                    self._enviar_html(500, "Não foi possível abrir a pasta", f"{erro}<br><br>{pasta}")
                    return
                self._enviar_json(500, {"ok": False, "erro": str(erro), "caminho": str(pasta)})
                return
        except OSError as erro:
            if resposta_html:
                self._enviar_html(500, "Não foi possível abrir a pasta", f"{erro}<br><br>{pasta}")
                return
            self._enviar_json(500, {"ok": False, "erro": str(erro), "caminho": str(pasta)})
            return

        if resposta_html:
            self._enviar_html(200, "Pasta aberta", f"A pasta do protocolo {protocolo} foi aberta.", fechar=True)
            return
        self._enviar_json(200, {"ok": True, "caminho": str(pasta)})

    def log_message(self, formato: str, *args) -> None:
        return


if __name__ == "__main__":
    servidor = ThreadingHTTPServer((HOST, PORTA), AbridorPastasHandler)
    print(f"Abridor de pastas do AERI ativo em http://{HOST}:{PORTA}")
    print(f"Pasta-base: {PASTA_BASE}")
    servidor.serve_forever()
