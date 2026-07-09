from pathlib import Path
from urllib.parse import urlparse
import os
import re
import sys


PASTA_BASE = Path(
    r"T:\Setor Apoio\Setor Certidao\04. Processos Intimacao\02 - Processos SAEC\07 - 2026\02 - Agua. pagamento (emolu informados)"
)
PADRAO_PROTOCOLO = re.compile(r"^IN\d{8}C$")


def extrair_protocolo(argumento: str) -> str:
    texto = str(argumento or "").strip().strip('"')
    if PADRAO_PROTOCOLO.fullmatch(texto.upper()):
        return texto.upper()

    url = urlparse(texto)
    candidatos = [
        url.netloc,
        url.path.strip("/").split("/")[-1] if url.path else "",
    ]
    for candidato in candidatos:
        candidato = str(candidato or "").strip().upper()
        if PADRAO_PROTOCOLO.fullmatch(candidato):
            return candidato

    raise ValueError("Protocolo inválido.")


def abrir_pasta(protocolo: str) -> Path:
    pasta = PASTA_BASE / protocolo
    if not pasta.exists():
        pasta.mkdir(parents=True, exist_ok=True)
    os.startfile(str(pasta))
    return pasta


if __name__ == "__main__":
    try:
        protocolo = extrair_protocolo(sys.argv[1] if len(sys.argv) > 1 else "")
        abrir_pasta(protocolo)
    except Exception as erro:
        os.system(f'msg * "AERI: não foi possível abrir a pasta da intimação. {erro}"')
