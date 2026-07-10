from pathlib import Path
from urllib.parse import urlparse
import os
import re
import sys


PASTA_BASE = Path(
    r"T:\Setor Apoio\Setor Certidao\04. Processos Intimacao\02 - Processos SAEC\07 - 2026\02 - Agua. pagamento (emolu informados)"
)
PASTAS_PROTOCOLOS = {
    "IN01504624C": Path(r"T:\Setor Apoio\Setor Certidao\04. Processos Intimacao\02 - Processos SAEC\06 - 2025\01 - Abertos (pagos)\IN01504624C"),
    "IN01503150C": Path(r"T:\Setor Apoio\Setor Certidao\04. Processos Intimacao\02 - Processos SAEC\06 - 2025\02 - Agua. pagamento (emolu informados)\IN01503150C"),
    "IN01473689C": Path(r"T:\Setor Apoio\Setor Certidao\04. Processos Intimacao\02 - Processos SAEC\06 - 2025\02 - Agua. pagamento (emolu informados)\IN01473689C"),
    "IN01460329C": Path(r"T:\Setor Apoio\Setor Certidao\04. Processos Intimacao\02 - Processos SAEC\06 - 2025\02 - Agua. pagamento (emolu informados)\IN01460329C"),
    "IN01430613C": Path(r"T:\Setor Apoio\Setor Certidao\04. Processos Intimacao\02 - Processos SAEC\06 - 2025\03 - Intimacao por Edital\IN01430613C"),
    "IN01422847C": Path(r"T:\Setor Apoio\Setor Certidao\04. Processos Intimacao\02 - Processos SAEC\06 - 2025\03 - Intimacao por Edital\IN01422847C"),
    "IN01401145C": Path(r"T:\Setor Apoio\Setor Certidao\04. Processos Intimacao\02 - Processos SAEC\06 - 2025\02 - Agua. pagamento (emolu informados)\IN01401145C"),
    "IN01394314C": Path(r"T:\Setor Apoio\Setor Certidao\04. Processos Intimacao\02 - Processos SAEC\06 - 2025\03 - Intimacao por Edital\IN01394314C"),
    "IN01391476C": Path(r"T:\Setor Apoio\Setor Certidao\04. Processos Intimacao\02 - Processos SAEC\06 - 2025\03 - Intimacao por Edital\IN01391476C"),
    "IN01381247C": Path(r"T:\Setor Apoio\Setor Certidao\04. Processos Intimacao\02 - Processos SAEC\06 - 2025\02 - Agua. pagamento (emolu informados)\IN01381247C"),
    "IN01369960C": Path(r"T:\Setor Apoio\Setor Certidao\04. Processos Intimacao\02 - Processos SAEC\06 - 2025\02 - Agua. pagamento (emolu informados)\IN01369960C"),
    "IN01358054C": Path(r"T:\Setor Apoio\Setor Certidao\04. Processos Intimacao\02 - Processos SAEC\06 - 2025\01 - Abertos (pagos)\IN01358054C"),
    "IN01345616C": Path(r"T:\Setor Apoio\Setor Certidao\04. Processos Intimacao\02 - Processos SAEC\06 - 2025\01 - Abertos (pagos)\IN01345616C"),
}
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


def caminho_pasta(protocolo: str) -> Path:
    protocolo = str(protocolo or "").strip().upper()
    if not PADRAO_PROTOCOLO.fullmatch(protocolo):
        raise ValueError("Protocolo inválido.")
    return PASTAS_PROTOCOLOS.get(protocolo, PASTA_BASE / protocolo)


def abrir_pasta(protocolo: str) -> Path:
    pasta = caminho_pasta(protocolo)
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
