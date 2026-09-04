"""OCR de documento digitalizado.

Dois motores, escolhidos nesta ordem:

1. **Tesseract** (`tesseract.exe`), quando instalado. É o motor de OCR livre
   mais usado, mantido pelo Google por uma década e hoje pela comunidade.
2. **`Windows.Media.Ocr`**, que já vem no sistema e não precisa de instalação.

Os dois têm a mesma propriedade que importa para um cartório: **rodam nesta
máquina**. O documento não sai daqui, o que é a condição para poder usar isto
com contrato de cliente. Nenhum dos dois existe fora do Windows — na Vercel,
`disponivel()` devolve False e o sistema diz que o contrato é digitalizado sem
tentar lê-lo.

**O texto de OCR nunca é tratado como certo.** Ele entra na ficha marcado, a
tela avisa, e o dígito verificador de CPF vale de rede: um algarismo lido errado
reprova em vez de passar.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from . import documento as doc

RAIZ = Path(__file__).resolve().parent.parent
SCRIPT_WINDOWS = RAIZ / "tools" / "ocr_windows.ps1"

# A rasterização acompanha a resolução do que o scanner capturou, entre estes
# limites. Fixar uma largura só era erro: no acervo as imagens vão de 2416 a
# 4816px, e rasterizar tudo a 2200px descartava mais da metade do detalhe nos
# documentos maiores — o OCR pagava por informação que existia no arquivo.
LARGURA_MINIMA = 1700
LARGURA_MAXIMA = 5000
TEMPO_LIMITE = 900

# O idioma tem nome diferente em cada motor.
IDIOMA = {"tesseract": "por", "windows": "pt-BR"}

# O instalador do Windows oferece dois destinos, e o que ele usa depende de ter
# sido aberto como administrador ou não. Sem privilégio, ele instala para o
# usuário — em %LOCALAPPDATA% — e procurar só em "Program Files" dava
# "não instalado" para quem tinha acabado de instalar.
CAMINHOS_TESSERACT = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Tesseract-OCR\tesseract.exe"),
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"),
    os.path.expandvars(r"%APPDATA%\Tesseract-OCR\tesseract.exe"),
)


def caminho_tesseract() -> str | None:
    """Procura o executável no PATH e nos lugares onde o instalador o põe.

    O instalador oficial não acrescenta o Tesseract ao PATH por padrão, então
    procurar só ali daria "não instalado" para quem acabou de instalar."""
    achado = shutil.which("tesseract")
    if achado:
        return achado
    for caminho in CAMINHOS_TESSERACT:
        if Path(caminho).exists():
            return caminho
    variavel = os.environ.get("TESSERACT_EXE")
    if variavel and Path(variavel).exists():
        return variavel
    return None


def _powershell() -> str | None:
    return shutil.which("powershell") or shutil.which("pwsh")


def motor() -> str | None:
    """Qual motor será usado, ou None se nenhum estiver disponível.

    **O do Windows vem primeiro, por medição, não por preferência.** Nos 24
    páginas do contrato de pessoa jurídica, comparados no mesmo documento e na
    mesma resolução (`tools/compara_ocr.py`, 25/08/2026):

        motor              contrato  financeiro  CPF   CNPJ   tempo
        tesseract psm 3       4/5       4/6      1/1    não     39s
        tesseract psm 6       4/5       3/6      1/1    não     36s
        tesseract psm 11      3/5       4/6      2/2    não     46s
        windows               5/5       6/6      2/2    sim     24s

    O Tesseract perdeu em toda configuração testada, e por dois motivos que não
    se corrigem com tolerância no código: leu `CNP)` no lugar de `CNPJ`, e
    engoliu um parágrafo inteiro da caixa A1 — o trecho do representante da
    empresa, com NIRE, cláusula de poderes, nome e CPF de quem assina.

    Ele fica instalado e disponível: `texto_de(..., forcar="tesseract")` dá uma
    segunda opinião quando um documento sair ruim no motor padrão.
    """
    if sys.platform != "win32":
        return None
    if SCRIPT_WINDOWS.exists() and _powershell():
        return "windows"
    if caminho_tesseract():
        return "tesseract"
    return None


def disponivel() -> bool:
    return motor() is not None


# ---------------------------------------------------------------- correções
# Erros que os motores cometem sempre, nos sinais pequenos e grudados no número.
# Todos ancorados no que vem depois, para nunca atingir palavra legítima.
CORRECOES = [
    # "ng", "n?", "n.2" no lugar de "nº"
    (re.compile(r"\bn[.\s]?[?g](?=\s*[\d.])"), "nº"),
    (re.compile(r"\bN[.\s]?[?G](?=\s*[\d.])"), "Nº"),
    (re.compile(r"\bn\.2(?=\s+\d)"), "n.º"),
    # "S 52 do art. 61" no lugar de "§ 5º do art. 61"
    (re.compile(r"\bS\s*(\d)2\s+(?=do\s+art)"), r"§ \1º "),
    # "22 Ofício", "12 Tabelionato" no lugar de "2º Ofício", "1º Tabelionato"
    (re.compile(r"\b(\d)2\s+(?=(?:Ofício|Oficio|Tabelionato|Registro|Vara|Serventia))"),
     r"\1º "),
    # "Lei 4,380/1964" no lugar de "Lei 4.380/1964": o ponto do milhar vira
    # vírgula. Número de lei nunca leva vírgula, então a troca é segura.
    (re.compile(r"\b(Lei\s+\d{1,2}),(\d{3}/\d{4})", re.I), r"\1.\2"),
]

# Os rótulos das caixas perdem os algarismos para letras parecidas: "A1" vira
# "Al", "B10" vira "BIO", "B10.1" vira "BIO.I". É o erro mais caro, porque a
# extração inteira ancora no rótulo — sem ele nada é encontrado, e a ficha volta
# vazia sem explicar por quê.
ROTULO = re.compile(
    r"\b([AB])([lIO0-9]{1,2}(?:\.[lIO0-9]{1,2})?)(?=\s*[-–]\s*[A-ZÀ-Ý])")
TROCA_ROTULO = str.maketrans({"l": "1", "I": "1", "O": "0"})


def corrige(texto: str) -> str:
    """Só o que os motores erram sempre. Nada de adivinhação além disso."""
    for padrao, troca in CORRECOES:
        texto = padrao.sub(troca, texto)
    return ROTULO.sub(
        lambda casou: casou.group(1) + casou.group(2).translate(TROCA_ROTULO),
        texto)


# ------------------------------------------------------------------ motores
def _rasteriza(caminho: Path, pasta: Path, paginas: list[int] | None = None) -> int:
    """Grava um PNG por página, na resolução do que o scanner capturou."""
    import pymupdf
    with pymupdf.open(caminho) as pdf:
        total = pdf.page_count

    alvos = paginas if paginas is not None else list(range(total))
    for indice in alvos:
        nativa = doc.largura_nativa(caminho, indice)
        largura = min(max(nativa or LARGURA_MINIMA, LARGURA_MINIMA), LARGURA_MAXIMA)
        png = doc.renderiza(caminho, indice, largura=largura)
        (pasta / f"p{indice + 1:03d}.png").write_bytes(png)
    return len(alvos)


def _com_tesseract(pasta: Path) -> str:
    """Uma chamada só para o documento inteiro: o Tesseract aceita um arquivo
    com a lista de imagens, e abrir um processo por página custaria caro."""
    executavel = caminho_tesseract()
    lista = pasta / "paginas.txt"
    lista.write_text(
        "\n".join(str(p) for p in sorted(pasta.glob("*.png"))), encoding="utf-8")

    processo = subprocess.run(
        [executavel, str(lista), "stdout", "-l", IDIOMA["tesseract"]],
        capture_output=True, timeout=TEMPO_LIMITE)
    if processo.returncode != 0:
        erro = processo.stderr.decode("utf-8", "replace").strip()
        raise RuntimeError(f"o Tesseract falhou: {erro[:300]}")
    return processo.stdout.decode("utf-8", "replace")


def _com_windows(pasta: Path) -> str:
    processo = subprocess.run(
        [_powershell(), "-NoProfile", "-ExecutionPolicy", "Bypass",
         "-File", str(SCRIPT_WINDOWS), "-Pasta", str(pasta),
         "-Idioma", IDIOMA["windows"]],
        capture_output=True, timeout=TEMPO_LIMITE)
    if processo.returncode != 0:
        erro = processo.stderr.decode("utf-8", "replace").strip()
        raise RuntimeError(f"o OCR do Windows falhou: {erro[:300]}")
    bruto = processo.stdout.decode("utf-8", "replace")
    # os marcadores de página do script não fazem parte do documento
    return re.sub(r"^@@PAGINA \S+\s*$", "", bruto, flags=re.M)


def texto_de_pasta(pasta, forcar: str | None = None) -> str:
    """Reconhece uma pasta de PNGs ja rasterizados, com as correcoes aplicadas.

    Existe porque o pipeline de contratos rasteriza pagina a pagina, para poder
    reportar progresso, e precisava do mesmo motor sem repetir a escolha nem a
    tabela de correcoes -- a copia que havia em servicos/documentos_contratos.py
    trazia o caminho do script escrito a mao e parou de achar o arquivo.
    """
    escolhido = forcar or motor()
    if escolhido is None:
        raise RuntimeError("nenhum motor de OCR disponível nesta máquina.")
    bruto = _com_tesseract(Path(pasta)) if escolhido == "tesseract" else _com_windows(Path(pasta))
    return corrige(bruto)


def texto_de(caminho, forcar: str | None = None) -> str:
    """Rasteriza o PDF e devolve o texto reconhecido.

    `forcar` escolhe o motor à mão ("tesseract" ou "windows"); serve para
    comparar os dois sobre o mesmo documento.
    """
    escolhido = forcar or motor()
    if escolhido is None:
        raise RuntimeError("nenhum motor de OCR disponível nesta máquina.")
    if escolhido == "tesseract" and not caminho_tesseract():
        raise RuntimeError("o Tesseract não está instalado nesta máquina.")

    pasta = Path(tempfile.mkdtemp(prefix="minutas-ocr-"))
    try:
        _rasteriza(Path(caminho), pasta)
        bruto = _com_tesseract(pasta) if escolhido == "tesseract" \
            else _com_windows(pasta)
    finally:
        shutil.rmtree(pasta, ignore_errors=True)

    return corrige(bruto)
