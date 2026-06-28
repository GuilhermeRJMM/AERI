import io
import re
import unicodedata
from collections import OrderedDict

from pypdf import PdfReader


def _normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFD", texto.upper())
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", texto).strip()


REGRAS_COMUNICAR = (
    (("VENDA E COMPRA", "COMPRA E VENDA"), "Mudança de titularidade"),
    (("INVENTARIO", "PARTILHA", "ARROLAMENTO"), "Mudança de titularidade por sucessão"),
    (("INCORPORACAO DE PATRIMONIO",), "Mudança de titularidade"),
    (("DIVISAO AMIGAVEL", "DIVISAO DE IMOVEL"), "Divisão ou parcelamento"),
    (("DESMEMBRAMENTO", "PARCELAMENTO", "LOTEAMENTO"), "Parcelamento ou desmembramento"),
    (("FUSAO", "UNIFICACAO", "REMEMBRAMENTO"), "Fusão ou remembramento"),
    (("RETIFICACAO DE AREA",), "Retificação de área"),
    (("RESERVA LEGAL", "PATRIMONIO NATURAL", "RPPN"), "Limitação ambiental"),
    (("INSCRICAO NO CAR", "CADASTRO AMBIENTAL RURAL"), "Restrição ou informação ambiental"),
    (("REFORMA AGRARIA",), "Modificação territorial ou de titularidade"),
)

REGRAS_REVISAR = (
    (("GEORREFERENCIAMENTO",), "Confirmar se houve alteração de área ou perímetro"),
    (("RETIFICACAO ADMINISTRATIVA", "RETIFICACAO EX-OFFICIO"), "Confirmar o objeto da retificação"),
    (("AVERBACAO",), "Tipo genérico: conferir o conteúdo do ato"),
)


def classificar_ato(ato: str) -> tuple[str, str]:
    normalizado = _normalizar(ato)
    for termos, motivo in REGRAS_COMUNICAR:
        if any(termo in normalizado for termo in termos):
            return "COMUNICAR", motivo
    for termos, motivo in REGRAS_REVISAR:
        if any(termo in normalizado for termo in termos):
            return "REVISAR", motivo
    return "FORA_DAS_HIPOTESES", "Não corresponde às hipóteses fornecidas"


def extrair_protocolos(pdf_bytes: bytes) -> dict:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    if not reader.pages:
        raise ValueError("O PDF não possui páginas legíveis.")

    texto = "\n".join((pagina.extract_text() or "") for pagina in reader.pages)
    padrao = re.compile(
        r"Ato\s+Praticado:\s*\n?[^\n]*?/[^\n]*?\n"
        r"(?P<ato>.*?)\s*Protocolo:\s*(?P<protocolo>\d+)",
        re.IGNORECASE | re.DOTALL,
    )

    agrupados = OrderedDict()
    lancamentos = 0
    for match in padrao.finditer(texto):
        protocolo = match.group("protocolo")
        ato = re.sub(r"\s+", " ", match.group("ato")).strip(" -:;")
        if not ato:
            continue
        lancamentos += 1
        chave = (protocolo, _normalizar(ato))
        if chave not in agrupados:
            status, motivo = classificar_ato(ato)
            agrupados[chave] = {
                "protocolo": protocolo, "ato": ato, "status": status,
                "motivo": motivo, "ocorrencias": 0,
            }
        agrupados[chave]["ocorrencias"] += 1

    if not agrupados:
        raise ValueError("Nenhum protocolo com tipo de ato foi identificado neste PDF.")

    itens = sorted(agrupados.values(), key=lambda item: (int(item["protocolo"]), item["ato"]))
    status_validos = ("COMUNICAR", "REVISAR", "FORA_DAS_HIPOTESES")
    return {
        "paginas": len(reader.pages),
        "lancamentos": lancamentos,
        "protocolos_unicos": len({item["protocolo"] for item in itens}),
        "itens": itens,
        "contagens": {s: sum(1 for item in itens if item["status"] == s) for s in status_validos},
    }
