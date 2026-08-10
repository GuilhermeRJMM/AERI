from pathlib import Path
import os
import re
import subprocess
import sys
from urllib.parse import unquote, urlparse

try:
    from ferramentas.nota_desistencia import ErroNotaDesistencia, gerar_nota_desistencia
except ModuleNotFoundError:  # Execução direta pelo protocolo local do Windows.
    from nota_desistencia import ErroNotaDesistencia, gerar_nota_desistencia


PASTA_BASE = Path(
    r"T:\Setor Apoio\Setor Certidao\04. Processos Intimacao\02 - Processos SAEC\07 - 2026\02 - Agua. pagamento (emolu informados)"
)
RAIZ_PROCESSOS_SAEC = PASTA_BASE.parents[1]
RAIZES_BUSCA = (
    RAIZ_PROCESSOS_SAEC / "07 - 2026",
    RAIZ_PROCESSOS_SAEC / "06 - 2025",
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
ACOES_VALIDAS = {"ABRIR", "GERAR-DESISTENCIA"}


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


def extrair_comando(argumento: str) -> tuple[str, str]:
    texto = str(argumento or "").strip().strip('"')
    if PADRAO_PROTOCOLO.fullmatch(texto.upper()):
        return "ABRIR", texto.upper()
    url = urlparse(texto)
    acao = unquote(str(url.netloc or "")).strip().upper()
    protocolo = unquote(url.path.strip("/").split("/")[-1] if url.path else "").upper()
    if acao not in ACOES_VALIDAS:
        raise ValueError("Ação local inválida.")
    if not PADRAO_PROTOCOLO.fullmatch(protocolo):
        raise ValueError("Protocolo inválido.")
    return acao, protocolo


def caminho_pasta(protocolo: str) -> Path:
    protocolo = str(protocolo or "").strip().upper()
    if not PADRAO_PROTOCOLO.fullmatch(protocolo):
        raise ValueError("Protocolo inválido.")
    return PASTAS_PROTOCOLOS.get(protocolo, PASTA_BASE / protocolo)


def localizar_pasta_existente(protocolo: str, raizes=None) -> Path | None:
    preferencial = caminho_pasta(protocolo)
    if preferencial.is_dir():
        return preferencial
    encontradas = []
    for raiz in raizes or RAIZES_BUSCA:
        raiz = Path(raiz)
        if not raiz.is_dir():
            continue
        encontradas.extend(
            item for item in raiz.rglob(protocolo)
            if item.is_dir() and item.name.upper() == protocolo.upper()
        )
    unicas = list(dict.fromkeys(item.resolve() for item in encontradas))
    if len(unicas) > 1:
        raise ValueError("O protocolo foi encontrado em mais de uma pasta.")
    return unicas[0] if unicas else None


def abrir_pasta(protocolo: str) -> Path:
    pasta = localizar_pasta_existente(protocolo) or caminho_pasta(protocolo)
    if not pasta.exists():
        pasta.mkdir(parents=True, exist_ok=True)
    os.startfile(str(pasta))
    return pasta


def notificar(mensagem: str) -> None:
    texto = re.sub(r"[\r\n]+", " ", str(mensagem or "")).strip()[:900]
    try:
        subprocess.run(["msg", "*", f"AERI: {texto}"], check=False, timeout=10)
    except (OSError, subprocess.SubprocessError):
        pass


def executar_comando(argumento: str) -> Path:
    acao, protocolo = extrair_comando(argumento)
    if acao == "ABRIR":
        return abrir_pasta(protocolo)
    pasta = localizar_pasta_existente(protocolo)
    if pasta is None:
        raise ErroNotaDesistencia("A pasta da intimação não foi localizada.")
    destino = gerar_nota_desistencia(pasta, protocolo)
    os.startfile(str(destino))
    notificar(
        f"Nota criada em {destino.name}. Confira obrigatoriamente no ITI o nome do signatário antes de salvar em PDF."
    )
    return destino


if __name__ == "__main__":
    try:
        executar_comando(sys.argv[1] if len(sys.argv) > 1 else "")
    except Exception as erro:
        notificar(str(erro))
