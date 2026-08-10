from __future__ import annotations

import copy
import html
import re
import unicodedata
import zipfile
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader


MODELO_NOTA_DESISTENCIA = Path(
    r"T:\Setor Apoio\Setor Certidao\04. Processos Intimacao\02 - Processos SAEC"
    r"\02 - Modelos para Processos\Notas de Devolucao-Exigencia"
    r"\Pedido Prenotado - Desistencia Credor.docx"
)
PASTA_SAIDA = "Expedido pelo Cartorio"
PASTA_PEDIDO_DESISTENCIA = "RECEBIDO PARA INTIMACAO"
NOME_PEDIDO_DESISTENCIA = "PEDIDO DE DESISTENCIA"
ASSINANTE_PENDENTE = "[INFORMAR O NOME DO SIGNATÁRIO APÓS VALIDAR NO ITI]"
LIMITE_PDFS = 100
LIMITE_PDF_BYTES = 30_000_000
LIMITE_TOTAL_BYTES = 250_000_000
PADRAO_PROTOCOLO = re.compile(r"^IN\d{8}C$")
PADRAO_PARAGRAFO_XML = re.compile(r"<w:p(?:\s[^>]*)?>.*?</w:p>", re.DOTALL)
PADRAO_TEXTO_XML = re.compile(r"(<w:t\b[^>]*>)(.*?)(</w:t>)", re.DOTALL)
MESES = {
    "JANEIRO": 1, "FEVEREIRO": 2, "MARCO": 3, "ABRIL": 4,
    "MAIO": 5, "JUNHO": 6, "JULHO": 7, "AGOSTO": 8,
    "SETEMBRO": 9, "OUTUBRO": 10, "NOVEMBRO": 11, "DEZEMBRO": 12,
}


class ErroNotaDesistencia(RuntimeError):
    """Falha segura e compreensível durante a geração local da nota."""


@dataclass(frozen=True)
class DocumentoPdf:
    caminho: Path
    texto: str
    assinantes: tuple[str, ...] = ()


@dataclass(frozen=True)
class DadosNotaDesistencia:
    protocolo_onr: str
    protocolo_ri: str
    data_protocolo: str
    titulo: str
    credor: str
    devedor: str
    matricula: str
    ato_registro: str
    endereco_imovel: str
    oficio_desistencia: str
    data_desistencia: str
    assinante_desistencia: str


def _normalizar_espacos(texto: str) -> str:
    return re.sub(r"\s+", " ", str(texto or "")).strip()


def _normalizar_busca(texto: str) -> str:
    decomposicao = unicodedata.normalize("NFD", str(texto or "").upper())
    sem_acentos = "".join(
        caractere for caractere in decomposicao
        if unicodedata.category(caractere) != "Mn"
    )
    return _normalizar_espacos(sem_acentos)


def _somente_digitos(texto: str) -> str:
    return re.sub(r"\D", "", str(texto or ""))


def _corrigir_ruidos_extracao(texto: str) -> str:
    corrigido = _normalizar_espacos(texto)
    corrigido = re.sub(r"\bD\s+E\b", "DE", corrigido, flags=re.IGNORECASE)
    corrigido = re.sub(r"(?<=\d)\s+-(?=\d)", "-", corrigido)
    corrigido = re.sub(
        r"\bCEP\s*:?\s*(\d{2})\.?\s*(\d{3})-?\s*(\d{3})\b",
        r"CEP: \1.\2-\3",
        corrigido,
        flags=re.IGNORECASE,
    )
    return corrigido


def _formatar_numero_registro(valor: str) -> str:
    digitos = _somente_digitos(valor).lstrip("0") or "0"
    return f"{int(digitos):,}".replace(",", ".")


def _formatar_data_extenso(valor: str) -> str:
    texto = _normalizar_espacos(valor)
    numerica = re.fullmatch(r"(\d{1,2})[./-](\d{1,2})[./-](\d{4})", texto)
    if numerica:
        return f"{int(numerica.group(1)):02d}.{int(numerica.group(2)):02d}.{numerica.group(3)}"
    por_extenso = re.fullmatch(
        r"(\d{1,2})\s+de\s+([A-Za-zÀ-ÿ]+)\s+de\s+(\d{4})",
        texto,
        re.IGNORECASE,
    )
    if not por_extenso:
        raise ErroNotaDesistencia(f"Data não reconhecida: {texto}")
    mes = MESES.get(_normalizar_busca(por_extenso.group(2)))
    if mes is None:
        raise ErroNotaDesistencia(f"Mês não reconhecido: {por_extenso.group(2)}")
    return f"{int(por_extenso.group(1)):02d}.{mes:02d}.{por_extenso.group(3)}"


def _esta_dentro(caminho: Path, raiz: Path) -> bool:
    try:
        caminho.resolve().relative_to(raiz.resolve())
        return True
    except ValueError:
        return False


def _nome_pdf(valor) -> str:
    texto = _normalizar_espacos(str(valor or "")).strip("/()[]<>\"'")
    if not texto or texto.upper() in {"NONE", "NULL", "DESCONHECIDO"}:
        return ""
    return texto


def _extrair_assinantes_pdf(leitor: PdfReader) -> tuple[str, ...]:
    """Lê nomes declarados nas assinaturas embutidas sem transmitir o PDF."""
    nomes = []
    try:
        campos = leitor.get_fields() or {}
    except Exception:
        campos = {}
    for campo in campos.values():
        try:
            campo = campo.get_object() if hasattr(campo, "get_object") else campo
            if str(campo.get("/FT", "")) != "/Sig":
                continue
            assinatura = campo.get("/V")
            assinatura = assinatura.get_object() if hasattr(assinatura, "get_object") else assinatura
            nome = _nome_pdf(assinatura.get("/Name")) if hasattr(assinatura, "get") else ""
            if nome and nome not in nomes:
                nomes.append(nome)
        except Exception:
            continue
    return tuple(nomes)


def _e_pedido_desistencia_nomeado(caminho: Path) -> bool:
    partes = [_normalizar_busca(parte) for parte in Path(caminho).parts]
    nome = _normalizar_busca(Path(caminho).stem)
    return PASTA_PEDIDO_DESISTENCIA in partes and nome.startswith(NOME_PEDIDO_DESISTENCIA)


def ler_documentos_pdf(pasta: Path) -> tuple[list[DocumentoPdf], list[str]]:
    raiz = Path(pasta).resolve()
    if not raiz.is_dir():
        raise ErroNotaDesistencia("A pasta da intimação não foi localizada.")
    arquivos = sorted(
        (item for item in raiz.rglob("*") if item.is_file() and item.suffix.lower() == ".pdf"),
        key=lambda item: str(item).lower(),
    )
    if not arquivos:
        raise ErroNotaDesistencia("A pasta da intimação não possui documentos PDF.")
    if len(arquivos) > LIMITE_PDFS:
        raise ErroNotaDesistencia(f"A pasta possui mais de {LIMITE_PDFS} PDFs; revise manualmente.")

    total = 0
    documentos = []
    falhas = []
    for arquivo in arquivos:
        if not _esta_dentro(arquivo, raiz):
            falhas.append(f"{arquivo.name}: caminho fora da pasta permitida")
            continue
        tamanho = arquivo.stat().st_size
        total += tamanho
        if tamanho > LIMITE_PDF_BYTES:
            falhas.append(f"{arquivo.name}: excede 30 MB")
            continue
        if total > LIMITE_TOTAL_BYTES:
            raise ErroNotaDesistencia("Os PDFs ultrapassam o limite total de 250 MB.")
        try:
            leitor = PdfReader(str(arquivo), strict=False)
            if leitor.is_encrypted and leitor.decrypt("") == 0:
                raise ValueError("PDF protegido por senha")
            texto = "\n".join((pagina.extract_text() or "") for pagina in leitor.pages)
            if not texto.strip():
                raise ValueError("PDF sem texto pesquisável")
            documentos.append(DocumentoPdf(arquivo, texto, _extrair_assinantes_pdf(leitor)))
        except Exception as erro:
            falhas.append(f"{arquivo.name}: {erro}")
    if not documentos:
        raise ErroNotaDesistencia("Nenhum PDF com texto pesquisável pôde ser analisado.")
    return documentos, falhas


def _documento_desistencia(documentos: list[DocumentoPdf]) -> DocumentoPdf:
    nomeados = [documento for documento in documentos if _e_pedido_desistencia_nomeado(documento.caminho)]
    if not nomeados:
        raise ErroNotaDesistencia(
            "Inclua o PDF 'Pedido de Desistência' na subpasta 'Recebido para Intimacao'."
        )
    candidatos = []
    for documento in nomeados:
        texto = _normalizar_busca(documento.texto)
        pedido_expresso = bool(re.search(
            r"\bSOLICITAMOS\s+(?:O\s+)?(?:"
            r"CANCELAMENTO\s+DO\s+PROCESSO\s+DE\s+INTIMACAO|"
            r"DESISTENCIA\s+(?:DO|DESTE)\s+(?:PEDIDO|PROCESSO))\b",
            texto,
        ))
        if not pedido_expresso:
            continue
        pontuacao = 1 + int("CREDORA" in texto) + int("OFICIO" in texto)
        pontuacao += int("MATRICULA DO IMOVEL" in texto)
        candidatos.append((pontuacao, documento))
    if not candidatos:
        raise ErroNotaDesistencia(
            "Não foi encontrado pedido expresso de desistência ou cancelamento do processo."
        )
    candidatos.sort(key=lambda item: (item[0], str(item[1].caminho).lower()), reverse=True)
    return candidatos[0][1]


def _documento_autuacao(documentos: list[DocumentoPdf], protocolo: str) -> DocumentoPdf:
    candidatos = [
        documento for documento in documentos
        if "AUTUACAO" in _normalizar_busca(documento.texto)
        and "CREDORA FIDUCIARIA" in _normalizar_busca(documento.texto)
        and protocolo in _normalizar_busca(documento.texto)
    ]
    if not candidatos:
        raise ErroNotaDesistencia("A autuação do processo não foi identificada nos PDFs.")
    return max(candidatos, key=lambda documento: len(documento.texto))


def _documento_intimacao(documentos: list[DocumentoPdf], protocolo: str) -> DocumentoPdf:
    candidatos = [
        documento for documento in documentos
        if protocolo in _normalizar_busca(documento.texto)
        and "VENHO INTIMAR" in _normalizar_busca(documento.texto)
        and "REGISTRADO SOB O" in _normalizar_busca(documento.texto)
    ]
    if not candidatos:
        raise ErroNotaDesistencia("O ofício de intimação com o ato registral não foi identificado.")
    return max(candidatos, key=lambda documento: len(documento.texto))


def _buscar(padrao: str, texto: str, descricao: str) -> str:
    encontrado = re.search(padrao, texto, re.IGNORECASE | re.DOTALL)
    if not encontrado:
        raise ErroNotaDesistencia(f"Não foi possível identificar {descricao}.")
    return _normalizar_espacos(encontrado.group(1)).strip(" .;,-")


def _validar_vinculo_desistencia(
    texto_desistencia: str,
    matricula: str,
    devedor: str,
    titulo: str,
) -> None:
    busca = _normalizar_busca(texto_desistencia)
    matricula_desistencia = _buscar(
        r"Matr[íi]cula\s+do\s+Im[óo]vel\s*:\s*([\d.]+)",
        texto_desistencia,
        "a matrícula no pedido de desistência",
    )
    if _somente_digitos(matricula_desistencia) != _somente_digitos(matricula):
        raise ErroNotaDesistencia("A matrícula do pedido de desistência diverge da autuação.")
    if _normalizar_busca(devedor) not in busca:
        raise ErroNotaDesistencia("O devedor do pedido de desistência diverge da autuação.")
    contrato_desistencia = _buscar(
        r"contrato\s+de\s+financiamento\s+imobili[áa]rio\s+n[º°o.]?\s*([\d.\-/]+)",
        texto_desistencia,
        "o contrato no pedido de desistência",
    )
    contrato_titulo = _somente_digitos(titulo)
    contrato_pedido = _somente_digitos(contrato_desistencia)
    if len(contrato_pedido) < 8 or contrato_pedido not in contrato_titulo:
        raise ErroNotaDesistencia("O contrato do pedido de desistência diverge da autuação.")


def extrair_dados_nota(
    documentos: list[DocumentoPdf],
    protocolo_esperado: str,
) -> DadosNotaDesistencia:
    protocolo = str(protocolo_esperado or "").strip().upper()
    if not PADRAO_PROTOCOLO.fullmatch(protocolo):
        raise ErroNotaDesistencia("Protocolo ONR inválido.")
    autuacao = _normalizar_espacos(_documento_autuacao(documentos, protocolo).texto)
    intimacao = _normalizar_espacos(_documento_intimacao(documentos, protocolo).texto)
    documento_desistencia = _documento_desistencia(documentos)
    desistencia = _normalizar_espacos(documento_desistencia.texto)

    data_protocolo_extenso = _buscar(
        r"protocolado\s+em\s+(\d{1,2}\s+de\s+[A-Za-zÀ-ÿ]+\s+de\s+\d{4})\s+sob",
        autuacao,
        "a data da prenotação",
    )
    protocolo_ri = _buscar(
        r"protocolado\s+em\s+\d{1,2}\s+de\s+[A-Za-zÀ-ÿ]+\s+de\s+\d{4}\s+sob\s+o\s+n[.º°o]*\s*([\d.]+)",
        autuacao,
        "o protocolo do Registro de Imóveis",
    )
    titulo = _buscar(
        r"T[ÍI]TULO\s*:\s*(.*?)\s+CREDORA\s+FIDUCI[ÁA]RIA\s*:",
        autuacao,
        "o título",
    )
    credor = _buscar(
        r"CREDORA\s+FIDUCI[ÁA]RIA\s*:\s*(.*?)\s+DEVEDOR(?:\(A\))?",
        autuacao,
        "a credora fiduciária",
    )
    devedor = _buscar(
        r"DEVEDOR(?:\(A\))?(?:\(ES\))?\s+FIDUCIANTE(?:\(S\))?\s*:\s*(.*?)(?:,?\s*\(?CPF\s*:)",
        autuacao,
        "a parte devedora",
    )
    endereco = _buscar(
        r"ENDERE[ÇC]O\s*:\s*(.*?)\s+AUTUA[ÇC][ÃA]O\b",
        autuacao,
        "o endereço do imóvel",
    )
    matricula = _buscar(
        r"Matr[íi]cula\s+n[.º°o]*\s*([\d.]+(?:\s+[\d.]+)*)",
        intimacao,
        "a matrícula",
    )
    ato_registro = _buscar(
        r"registrado\s+sob\s+o\s+((?:R|AV)\.\s*\d+)",
        intimacao,
        "o ato registral",
    ).replace(" ", "").upper()
    oficio = _buscar(
        r"Of[íi]cio\s+n[º°o.]?\s*([\d]+/\d{4}(?:\s+[A-Z]+/[A-Z]+)?)",
        desistencia,
        "o número do ofício de desistência",
    )
    data_desistencia_extenso = _buscar(
        r"(?:Bauru|Morrinhos)(?:-GO)?\s*,\s*(\d{1,2}\s+de\s+[A-Za-zÀ-ÿ]+\s+de\s+\d{4})",
        desistencia,
        "a data do pedido de desistência",
    )

    _validar_vinculo_desistencia(desistencia, matricula, devedor, titulo)
    return DadosNotaDesistencia(
        protocolo_onr=protocolo,
        protocolo_ri=_formatar_numero_registro(protocolo_ri),
        data_protocolo=_formatar_data_extenso(data_protocolo_extenso),
        titulo=_corrigir_ruidos_extracao(titulo).rstrip("."),
        credor=credor.rstrip("."),
        devedor=devedor.rstrip("."),
        matricula=_formatar_numero_registro(matricula),
        ato_registro=ato_registro,
        endereco_imovel=_corrigir_ruidos_extracao(endereco).rstrip("."),
        oficio_desistencia=oficio,
        data_desistencia=_formatar_data_extenso(data_desistencia_extenso),
        assinante_desistencia=", ".join(documento_desistencia.assinantes) or ASSINANTE_PENDENTE,
    )


def montar_paragrafos(dados: DadosNotaDesistencia) -> tuple[str, str]:
    processo = (
        "Iniciando o procedimento de qualificação registrária do título apresentado por V.S.ª, "
        f"detectamos tratar-se do protocolo de intimação n.º {dados.protocolo_onr}, sob o "
        f"protocolo de n.º {dados.protocolo_ri}, procedido em data de {dados.data_protocolo} "
        "através do Operador Nacional do Sistema de Registro Eletrônico de Imóveis (ONR), "
        f"referente ao {dados.titulo.upper()}, registrado sob o {dados.ato_registro} da matrícula "
        f"n.º {dados.matricula} deste CRI, em que figura como parte devedora fiduciante "
        f"{dados.devedor}, relativo ao imóvel urbano situado no endereço {dados.endereco_imovel}."
    )
    desistência = (
        f"Por meio do Ofício n.º {dados.oficio_desistencia}, datado de "
        f"{dados.data_desistencia} e assinado eletronicamente por {dados.assinante_desistencia}, "
        "representante da credora "
        f"fiduciária {dados.credor}, foi solicitada a desistência do pedido em comento."
    )
    return processo, desistência


def _texto_paragrafo_xml(paragrafo: str) -> str:
    return "".join(html.unescape(item.group(2)) for item in PADRAO_TEXTO_XML.finditer(paragrafo))


def _preencher_nos_texto_xml(paragrafo: str, novo_texto: str) -> str:
    primeiro = True

    def substituir(encontrado: re.Match) -> str:
        nonlocal primeiro
        abertura, fechamento = encontrado.group(1), encontrado.group(3)
        if not primeiro:
            return abertura + fechamento
        primeiro = False
        if "xml:space=" not in abertura:
            abertura = abertura[:-1] + ' xml:space="preserve">'
        return abertura + html.escape(novo_texto, quote=False) + fechamento

    resultado = PADRAO_TEXTO_XML.sub(substituir, paragrafo)
    if primeiro:
        raise ErroNotaDesistencia("O modelo possui um parágrafo editável sem texto.")
    return resultado


def _substituir_paragrafo_xml(documento: str, marcador, novo_texto: str) -> str:
    for encontrado in PADRAO_PARAGRAFO_XML.finditer(documento):
        paragrafo = encontrado.group(0)
        if marcador(_texto_paragrafo_xml(paragrafo)):
            preenchido = _preencher_nos_texto_xml(paragrafo, novo_texto)
            return documento[:encontrado.start()] + preenchido + documento[encontrado.end():]
    raise ErroNotaDesistencia("O modelo mudou e não possui mais os campos esperados.")


def _destino_disponivel(pasta: Path, protocolo: str) -> Path:
    base = pasta / f"Nota de Devolução - Desistência - {protocolo}.docx"
    if not base.exists():
        return base
    for indice in range(2, 100):
        candidato = pasta / f"Nota de Devolução - Desistência - {protocolo} ({indice}).docx"
        if not candidato.exists():
            return candidato
    raise ErroNotaDesistencia("Há muitas versões da nota na pasta; organize-as antes de continuar.")


def preencher_modelo(modelo: Path, destino: Path, dados: DadosNotaDesistencia) -> Path:
    modelo = Path(modelo).resolve()
    destino = Path(destino).resolve()
    if not modelo.is_file() or modelo.suffix.lower() != ".docx":
        raise ErroNotaDesistencia("O modelo da nota de desistência não foi localizado.")
    processo, desistência = montar_paragrafos(dados)
    with zipfile.ZipFile(modelo, "r") as origem:
        try:
            documento = origem.read("word/document.xml").decode("utf-8")
        except (KeyError, UnicodeDecodeError) as erro:
            raise ErroNotaDesistencia("O modelo Word está inválido.") from erro
        documento = _substituir_paragrafo_xml(
            documento,
            lambda texto: texto.startswith("Iniciando o procedimento"),
            processo,
        )
        documento = _substituir_paragrafo_xml(
            documento,
            lambda texto: "desistência do pedido em comento" in texto and "credora fiduciária" in texto,
            desistência,
        )

        destino.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(destino, "w") as saida:
            for item in origem.infolist():
                conteudo = origem.read(item.filename)
                if item.filename == "word/document.xml":
                    conteudo = documento.encode("utf-8")
                saida.writestr(copy.copy(item), conteudo)
    return destino


def gerar_nota_desistencia(
    pasta_intimacao: Path,
    protocolo: str,
    modelo: Path = MODELO_NOTA_DESISTENCIA,
) -> Path:
    pasta = Path(pasta_intimacao).resolve()
    documentos, falhas = ler_documentos_pdf(pasta)
    try:
        dados = extrair_dados_nota(documentos, protocolo)
    except ErroNotaDesistencia as erro:
        detalhe = f" PDFs não lidos: {'; '.join(falhas[:3])}." if falhas else ""
        raise ErroNotaDesistencia(f"{erro}{detalhe}") from erro
    pasta_saida = (pasta / PASTA_SAIDA).resolve()
    if not _esta_dentro(pasta_saida, pasta):
        raise ErroNotaDesistencia("A pasta de saída não é permitida.")
    destino = _destino_disponivel(pasta_saida, protocolo)
    return preencher_modelo(modelo, destino, dados)
