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
    def _enviar_json(self, status: int, dados: dict) -> None:
        corpo = json.dumps(dados, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
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

        protocolo = parse_qs(rota.query).get("protocolo", [""])[0].strip().upper()
        if not PADRAO_PROTOCOLO.fullmatch(protocolo):
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
                self._enviar_json(500, {"ok": False, "erro": str(erro), "caminho": str(pasta)})
                return
        except OSError as erro:
            self._enviar_json(500, {"ok": False, "erro": str(erro), "caminho": str(pasta)})
            return

        self._enviar_json(200, {"ok": True, "caminho": str(pasta)})

    def log_message(self, formato: str, *args) -> None:
        return


if __name__ == "__main__":
    servidor = ThreadingHTTPServer((HOST, PORTA), AbridorPastasHandler)
    print(f"Abridor de pastas do AERI ativo em http://{HOST}:{PORTA}")
    print(f"Pasta-base: {PASTA_BASE}")
    servidor.serve_forever()
