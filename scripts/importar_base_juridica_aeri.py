"""Carrega lotes jurídicos privados no AERI sem persistir credenciais.

Uso:
  Defina AERI_IMPORT_USER e AERI_IMPORT_PASSWORD apenas no processo e informe
  a pasta gerada por gerar_base_juridica_embutida.py.
"""

import argparse
import json
import os
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import HTTPCookieProcessor, Request, build_opener


def _json_resposta(resposta) -> dict:
    corpo = resposta.read().decode("utf-8")
    return json.loads(corpo) if corpo else {}


def importar(base_url: str, pasta: Path, usuario: str, senha: str) -> list[dict]:
    if not usuario or not senha:
        raise RuntimeError("Defina AERI_IMPORT_USER e AERI_IMPORT_PASSWORD no processo.")
    if not base_url.startswith("https://"):
        raise RuntimeError("A carga jurídica remota exige HTTPS.")
    lotes = sorted(pasta.glob("fontes-juridicas-*.json.gz"))
    if not lotes:
        raise RuntimeError("Nenhum lote jurídico foi encontrado na pasta informada.")
    cookies = CookieJar()
    cliente = build_opener(HTTPCookieProcessor(cookies))
    origem = base_url.rstrip("/")
    login = Request(
        f"{origem}/api/login",
        data=json.dumps({"usuario": usuario, "senha": senha}).encode("utf-8"),
        headers={"Content-Type": "application/json", "Origin": origem},
        method="POST",
    )
    with cliente.open(login, timeout=30) as resposta:
        sessao = _json_resposta(resposta)
    csrf = str(sessao.get("csrfToken") or "")
    if not csrf:
        raise RuntimeError("O login não retornou uma sessão válida.")
    resultados = []
    for lote in lotes:
        requisicao = Request(
            f"{origem}/api/analisar/base-juridica/importar",
            data=lote.read_bytes(),
            headers={
                "Content-Type": "application/gzip",
                "X-CSRF-Token": csrf,
                "Origin": origem,
            },
            method="POST",
        )
        with cliente.open(requisicao, timeout=120) as resposta:
            retorno = _json_resposta(resposta)
        resultados.append({"lote": lote.name, **retorno})
    return resultados


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pasta", type=Path)
    parser.add_argument("--url", default="https://aeri-two.vercel.app")
    argumentos = parser.parse_args()
    try:
        resultados = importar(
            argumentos.url.rstrip("/"), argumentos.pasta,
            os.getenv("AERI_IMPORT_USER", ""), os.getenv("AERI_IMPORT_PASSWORD", ""),
        )
    except (RuntimeError, HTTPError, URLError, json.JSONDecodeError) as erro:
        print(json.dumps({"erro": str(erro)}, ensure_ascii=True))
        return 1
    print(json.dumps({"lotes": resultados}, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
