import io
import re
from functools import lru_cache
from hashlib import sha256
from pathlib import Path
import unicodedata
from collections import Counter
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from pypdf import PdfReader

from backend.app.parser import separar_atos


# 3 dígitos + ponto + 3 dígitos, sem ser parte de um número maior (evita
# casar com trechos do CNPJ do rodapé, ex.: "20.639.962" contém "639.962").
PADRAO_NUMERO_PROTOCOLO = re.compile(r"(?<!\d\.)\b(\d{3}\.\d{3})\b(?!/\d)")
PADRAO_DATA = re.compile(r"\b(\d{2})/(\d{2})/(\d{4})\b")
PADRAO_SEM_EFEITO = re.compile(r"\(Sem Efeito\)", re.IGNORECASE)
PADRAO_PRENOTADO = re.compile(r"\bPrenotado\b", re.IGNORECASE)
# Cabeçalho de uma referência de ato no "Resumo dos Atos": R.13 -, Av.6 -,
# Mat.0 -, Reg.0 - (inclui "Reg. Auxiliar").
PADRAO_ATO_REF = re.compile(r"\b(?:R|Av|Mat|Reg)\.\s*\d+\s*-\s*", re.IGNORECASE)

PADRAO_DATA_PLACEHOLDER = re.compile(r"\bxx[./]\d{2}[./]\d{4}\b|\b\d{2}[./]xx[./]\d{4}\b", re.IGNORECASE)
PADRAO_VALOR_EM_BRANCO = re.compile(r"R\$\s*;|R\$\s*\.")
PADRAO_SELO_EM_BRANCO = re.compile(r"\bSelo:\s*\.")
PADRAO_FECHO_EM_BRANCO = re.compile(r"-\s*[A-ZÀ-Ü]{2},\s*de\s+de\.", re.IGNORECASE)
PADRAO_TOTAL_COTACAO = re.compile(
    r"\bTotal\s*:\s*R\$\s*([0-9][0-9.\s]*(?:,[0-9]{1,2})?)",
    re.IGNORECASE,
)

STATUS_VALIDOS = ("PRENOTADO", "REGISTRADO", "SEM_EFEITO", "INDEFINIDO")
DIAS_RETROATIVOS_LIVRO = 90
DIAS_POR_CONSULTA_LIVRO = 30


def _colapsar_espacos(valor: str) -> str:
    return re.sub(r"\s+", " ", valor or "").strip()


def _normalizar(valor: str) -> str:
    sem_acentos = "".join(
        c for c in unicodedata.normalize("NFKD", valor or "") if not unicodedata.combining(c)
    )
    return _colapsar_espacos(sem_acentos).upper()


def _texto_valido(valor: object) -> bool:
    return isinstance(valor, str) and valor.strip() != ""


# Preposições/conectivos comuns que variam entre "Dados do Título" (texto
# livre do protocolo) e "Natureza Formal" (catálogo padronizado da Tri7) sem
# mudar o sentido — ex.: "Designação Cadastral do Imóvel" vs "Designação
# Cadastral de Imóvel". Como a comparação é por substring exata, essa única
# palavra trocada já derrubava o match inteiro mesmo descrevendo o mesmo ato.
PADRAO_CONECTIVO = re.compile(r"\b(?:DE|DO|DA|DOS|DAS|EM|NO|NA|NOS|NAS|E)\b")


def normalizar_tema(valor: str) -> str:
    sem_conectivos = PADRAO_CONECTIVO.sub(" ", _normalizar(valor))
    return _colapsar_espacos(sem_conectivos)


def classificar_status(bloco: str) -> str:
    # "(Sem Efeito)" e a presença de uma referência de ato (R./Av./Mat./Reg.)
    # são evidências concretas; checadas antes de "Prenotado" para não cair
    # nesse rótulo por vazamento de texto de uma linha vizinha.
    if PADRAO_SEM_EFEITO.search(bloco):
        return "SEM_EFEITO"
    if PADRAO_ATO_REF.search(bloco):
        return "REGISTRADO"
    if PADRAO_PRENOTADO.search(bloco):
        return "PRENOTADO"
    return "INDEFINIDO"


def _parse_bloco(numero_bruto: str, bloco: str) -> dict:
    sem_numero = bloco[len(numero_bruto):]
    match_data = PADRAO_DATA.search(sem_numero)
    if match_data:
        nome = _colapsar_espacos(sem_numero[: match_data.start()])
        resto = sem_numero[match_data.end():]
        data_iso = f"{match_data.group(3)}-{match_data.group(2)}-{match_data.group(1)}"
    else:
        nome = _colapsar_espacos(sem_numero)
        resto = ""
        data_iso = None
    return {
        "numero": numero_bruto.replace(".", ""),
        "numeroFormatado": numero_bruto,
        "data": data_iso,
        "nomeApresentante": nome or "NÃO CONSTA",
        "status": classificar_status(bloco),
        "resumoBruto": _colapsar_espacos(resto)[:600],
    }


def extrair_protocolos_pdf(pdf_bytes: bytes) -> list[dict]:
    """Extrai as linhas do Livro de Protocolos (PDF exportado da Tri7).

    Não distingue as duas seções da folha (expediente do dia vs. protocolos
    de dias anteriores que tiveram ato praticado nesta data) — quando o
    mesmo número aparece duas vezes (ex.: prenotado na 1ª seção e já
    registrado na 2ª), fica valendo a última ocorrência no texto, que reflete
    o estado mais atual.
    """
    leitor = PdfReader(io.BytesIO(pdf_bytes))
    if not leitor.pages:
        raise ValueError("O PDF não possui páginas legíveis.")
    texto = "\n".join(pagina.extract_text() or "" for pagina in leitor.pages)

    matches = list(PADRAO_NUMERO_PROTOCOLO.finditer(texto))
    if not matches:
        raise ValueError("Nenhum protocolo foi identificado neste PDF.")

    linhas: list[dict] = []
    indices_por_numero: dict[str, int] = {}
    for indice, match in enumerate(matches):
        inicio = match.start()
        fim = matches[indice + 1].start() if indice + 1 < len(matches) else len(texto)
        item = _parse_bloco(match.group(1), texto[inicio:fim])
        anterior = indices_por_numero.get(item["numero"])
        if anterior is not None:
            linhas[anterior] = item
        else:
            indices_por_numero[item["numero"]] = len(linhas)
            linhas.append(item)
    return linhas


@lru_cache(maxsize=1)
def hash_regras_livro_protocolos() -> str:
    return sha256(Path(__file__).read_bytes()).hexdigest()


def inferir_data_esperada(linhas: list[dict]) -> date | None:
    """Descobre a data que a folha representa a partir do próprio conteúdo.

    Antes disso a data esperada era sempre "hoje - 1 dia", assumindo que a
    folha é conferida no dia seguinte ao expediente. Isso quebra sempre que
    essa suposição não vale — depois de fim de semana/feriado (a folha de
    sexta é conferida na segunda, "ontem" seria domingo), ao reconferir uma
    folha antiga, ou ao rodar a conferência mais de uma vez no mesmo dia.
    Quando isso acontecia, TODO registro "REGISTRADO" caía na regra
    DATA_DIVERGENTE de uma vez, mesmo com as demais regras corretas — dava a
    impressão de que a conferência inteira estava errada.

    Usa a data mais frequente entre as linhas "REGISTRADO" (a maioria da
    folha), não a primeira nem a última, para não deixar uma linha isolada
    com data digitada errado decidir a data esperada de todo o resto.
    """
    datas = [
        linha["data"] for linha in linhas
        if linha.get("status") == "REGISTRADO" and linha.get("data")
    ]
    if not datas:
        return None
    mais_comum, _contagem = Counter(datas).most_common(1)[0]
    return date.fromisoformat(mais_comum)


def janelas_livro_protocolos(
    data_alvo: date,
    *,
    dias_retroativos: int = DIAS_RETROATIVOS_LIVRO,
    dias_por_consulta: int = DIAS_POR_CONSULTA_LIVRO,
) -> list[tuple[date, date]]:
    """Divide a busca retroativa em intervalos aceitos pela Tri7.

    O endpoint limita cada chamada a 31 dias. Usamos três intervalos de 30
    dias para cobrir 90 dias de apresentações sem sobreposição.
    """
    if dias_retroativos < 1 or dias_por_consulta < 1 or dias_por_consulta > 31:
        raise ValueError("Período de consulta do Livro de Protocolos inválido.")
    limite = data_alvo - timedelta(days=dias_retroativos - 1)
    janelas = []
    fim = data_alvo
    while fim >= limite:
        inicio = max(limite, fim - timedelta(days=dias_por_consulta - 1))
        janelas.append((inicio, fim))
        fim = inicio - timedelta(days=1)
    return janelas


def _data_tri7(valor: object) -> date | None:
    if valor is None or valor == "":
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    try:
        return datetime.fromisoformat(str(valor).strip().replace("Z", "+00:00")).date()
    except ValueError as erro:
        raise ValueError("A Tri7 retornou uma data inválida no Livro de Protocolos.") from erro


def _formatar_numero_protocolo(numero: int) -> str:
    return f"{numero:,}".replace(",", ".")


def montar_protocolos_do_dia(
    respostas_periodos: list[dict], data_alvo: date,
) -> list[dict]:
    """Reproduz as duas seções do Livro para uma data sem depender do PDF.

    Entram os títulos apresentados no dia e os títulos, ainda que apresentados
    antes, que tiveram registro no dia. Se um protocolo estiver nas duas
    seções, ele aparece uma vez e prevalece o estado REGISTRADO, igual ao
    comportamento já adotado na importação do PDF.
    """
    por_numero: dict[int, dict] = {}
    for resposta in respostas_periodos:
        for item in resposta.get("protocolos") or []:
            if not isinstance(item, dict):
                continue
            try:
                numero = int(item.get("protocolo"))
            except (TypeError, ValueError):
                raise ValueError("A Tri7 retornou um protocolo inválido no Livro.")
            if numero <= 0:
                raise ValueError("A Tri7 retornou um protocolo inválido no Livro.")
            por_numero[numero] = item

    selecionados = []
    for numero, item in por_numero.items():
        data_apresentacao = _data_tri7(item.get("data_apresentacao"))
        data_registro = _data_tri7(item.get("data_registro"))
        apresentado_no_dia = data_apresentacao == data_alvo
        registrado_no_dia = data_registro == data_alvo
        if not apresentado_no_dia and not registrado_no_dia:
            continue
        naturezas = [
            _colapsar_espacos(str(subitem.get("natureza") or ""))
            for subitem in item.get("itens") or []
            if isinstance(subitem, dict) and _texto_valido(subitem.get("natureza"))
        ]
        selecionados.append({
            "numero": str(numero),
            "numeroFormatado": _formatar_numero_protocolo(numero),
            "data": data_apresentacao.isoformat() if data_apresentacao else None,
            "dataRegistro": data_registro.isoformat() if data_registro else None,
            "nomeApresentante": _colapsar_espacos(str(item.get("apresentante") or "")) or "NÃO CONSTA",
            "status": "REGISTRADO" if registrado_no_dia else "PRENOTADO",
            "resumoBruto": "; ".join(dict.fromkeys(naturezas))[:600],
            "origemDia": (
                "APRESENTADO_E_REGISTRADO" if apresentado_no_dia and registrado_no_dia
                else "APRESENTADO" if apresentado_no_dia
                else "REGISTRADO"
            ),
            "_ordem": (0 if apresentado_no_dia else 1, numero),
        })
    selecionados.sort(key=lambda item: item["_ordem"])
    for item in selecionados:
        item.pop("_ordem", None)
    return selecionados


PADRAO_ITEM_AUXILIAR = re.compile(
    r"\b(?:PRENOTACAO|BUSCA|CODIGO\s+DE\s+ENDERECAMENTO\s+POSTAL|CEP)\b"
)
PALAVRAS_GENERICAS_TITULO = {
    "ATO", "AVERBACAO", "CONTRATO", "ESCRITURA", "FORMAL", "IMOVEL",
    "INSTRUMENTO", "PARTICULAR", "PUBLICA", "REGISTRO", "RURAL", "SIMPLES",
    "TITULO", "URBANO",
}
PALAVRAS_ANCORA = {
    "ARREMATACAO", "CASAMENTO", "CEDULA", "CONSOLIDACAO",
    "DESMEMBRAMENTO", "DIVORCIO", "EDIFICACAO", "GEORREFERENCIAMENTO",
    "HIPOTECA", "INTIMACAO", "PARTILHA", "PENHORA",
    "USUCAPIAO", "USUFRUTO",
}
PALAVRAS_CANCELAMENTO = {"BAIXA", "CANCELAMENTO", "EXTINCAO"}


def _item_tem_resultado_registral(item: dict) -> bool:
    natureza = _normalizar(str(item.get("natureza_formal_descricao") or ""))
    if not natureza or natureza == "PRENOTACAO" or re.search(r"\bBUSCA\b", natureza):
        return False
    registrado = item.get("atos_registrados") or {}
    if registrado.get("ato_tipo") is not None and registrado.get("ato_numero") is not None:
        return True
    # Matrículas novas e alguns atos de intimação aparecem como Mat.0 no
    # Livro, mas a Tri7 não preenche ato_tipo/ato_numero. O vínculo ao imóvel
    # ainda demonstra que este é um item efetivamente formalizado.
    return (item.get("dados_imovel") or {}).get("numero_registro") is not None


def _itens_com_resultado_registral(protocolo_json: dict) -> list[dict]:
    return [
        item for item in protocolo_json.get("itens_do_pedido") or []
        if _item_tem_resultado_registral(item)
    ]


def _palavras_tema(valor: str) -> set[str]:
    limpo = re.sub(r"[^A-Z0-9]+", " ", normalizar_tema(valor))
    return {
        palavra for palavra in limpo.split()
        if palavra not in PALAVRAS_GENERICAS_TITULO and len(palavra) > 1
    }


def _temas_correspondem(titulo: str, natureza: str) -> bool:
    palavras_titulo = _palavras_tema(titulo)
    palavras_natureza = _palavras_tema(natureza)
    if not palavras_titulo or not palavras_natureza:
        return False
    # Não confunde constituição/manutenção de um direito com sua baixa.
    # Ex.: "Alienação Fiduciária" e "Cancelamento de Alienação
    # Fiduciária" compartilham quase todas as palavras, mas são opostos.
    if bool(palavras_titulo & PALAVRAS_CANCELAMENTO) != bool(
        palavras_natureza & PALAVRAS_CANCELAMENTO
    ):
        return False
    if palavras_titulo <= palavras_natureza or palavras_natureza <= palavras_titulo:
        return True
    comuns = palavras_titulo & palavras_natureza
    # Dois termos materiais em comum identificam o mesmo negócio mesmo
    # quando cada fonte acrescenta qualificadores diferentes: "Escritura
    # Pública de Venda e Compra" x "Venda e Compra Imóvel Urbano (Simples)".
    if len(comuns) >= 2:
        return True
    # Alguns atos têm uma palavra jurídica suficientemente distintiva para
    # identificar o tema sozinha: "Formal de Partilha" x "Partilha Divórcio".
    return bool(comuns & PALAVRAS_ANCORA)


def natureza_permite_excecao(natureza: str) -> bool:
    # Itens instrumentais nunca devem virar equivalência manual de um título
    # principal. Isso impede cadastrar pares perigosos como
    # "Escritura de Venda e Compra" x "CEP".
    return not PADRAO_ITEM_AUXILIAR.search(_normalizar(natureza))


def _pontuacao_natureza(titulo: str, natureza: str) -> tuple[int, int]:
    titulo_palavras = _palavras_tema(titulo)
    natureza_palavras = _palavras_tema(natureza)
    comuns = titulo_palavras & natureza_palavras
    return (len(comuns & PALAVRAS_ANCORA), len(comuns))


def _regra_natureza_bate_com_titulo(
    protocolo_json: dict, excecoes: frozenset[tuple[str, str]] = frozenset(),
) -> list[dict]:
    # A ordem da API é operacional: atos preparatórios como CEP e cancelamento
    # podem vir corretamente antes do ato principal (Venda e Compra). Por isso
    # o título não é comparado apenas com a primeira posição; procura-se, entre
    # os resultados formalizados, ao menos uma Natureza Formal correspondente.
    protocolo = protocolo_json.get("protocolo") or {}
    descricao_titulo = protocolo.get("descricao_titulo")
    if not _texto_valido(descricao_titulo):
        return [{
            "regra": "NATUREZA_TITULO",
            "gravidade": "GRAVE",
            "descricao": "O protocolo não possui descrição do título (descricao_titulo em branco).",
        }]
    itens_com_natureza = [
        item for item in _itens_com_resultado_registral(protocolo_json)
        if _texto_valido(item.get("natureza_formal_descricao"))
    ]
    if not itens_com_natureza:
        return [{
            "regra": "NATUREZA_TITULO",
            "gravidade": "GRAVE",
            "descricao": "Nenhum item formalizado possui Natureza Formal para conferir contra o título.",
        }]
    titulo_tema = normalizar_tema(str(descricao_titulo))
    for item in itens_com_natureza:
        natureza = str(item["natureza_formal_descricao"])
        natureza_tema = normalizar_tema(natureza)
        if _temas_correspondem(str(descricao_titulo), natureza):
            return []
        if (
            natureza_permite_excecao(natureza)
            and (titulo_tema, natureza_tema) in excecoes
        ):
            return []

    # Ao sugerir a correção, itens meramente preparatórios não podem vencer
    # o ato principal num empate textual. Ex.: protocolo 185.366 com título
    # cadastrado por engano como "INSCRIÇÃO NO CAR", mas cujo resultado real
    # é CEP + Venda e Compra. A sugestão útil é Venda e Compra, não o CEP.
    candidatos_principais = [
        item for item in itens_com_natureza
        if natureza_permite_excecao(str(item["natureza_formal_descricao"]))
    ]
    item_candidato = max(
        candidatos_principais or itens_com_natureza,
        key=lambda item: _pontuacao_natureza(
            str(descricao_titulo), str(item["natureza_formal_descricao"]),
        ),
    )
    natureza = str(item_candidato["natureza_formal_descricao"])
    return [{
        "regra": "NATUREZA_TITULO",
        "gravidade": "ATENCAO",
        "descricao": (
            f"Dados do Título ('{descricao_titulo}') não corresponde a nenhuma Natureza "
            f"Formal dos atos. Candidata mais próxima: '{natureza}'."
        ),
        "tituloOriginal": str(descricao_titulo),
        "naturezaOriginal": natureza,
        "permiteExcecao": natureza_permite_excecao(natureza),
    }]


PADRAO_NATUREZA_BUSCA = re.compile(r"\bBUSCA\b")


def _regra_busca_com_matricula(protocolo_json: dict) -> list[dict]:
    ocorrencias = []
    for item in protocolo_json.get("itens_do_pedido") or []:
        # Palavra "BUSCA" em qualquer lugar da natureza, não só o texto
        # exato "Busca" — variantes como "Busca Simples" ou "Busca de Bens"
        # antes escapavam dessa checagem por não baterem a igualdade exata.
        if not PADRAO_NATUREZA_BUSCA.search(_normalizar(str(item.get("natureza_formal_descricao") or ""))):
            continue
        numero_registro = (item.get("dados_imovel") or {}).get("numero_registro")
        if numero_registro:
            ocorrencias.append({
                "regra": "BUSCA_COM_MATRICULA",
                "gravidade": "GRAVE",
                "descricao": f"Item de Busca retornou matrícula/registro nº {numero_registro} vinculado.",
            })
    return ocorrencias


def _chave_registro(item: dict) -> tuple[str, int] | None:
    imovel = item.get("dados_imovel") or {}
    numero = imovel.get("numero_registro")
    if numero is None:
        return None
    try:
        return (str(imovel.get("tipo_registro") or "").upper(), int(numero))
    except (TypeError, ValueError):
        return None


def referencias_textos_protocolo(protocolo_json: dict) -> set[tuple[str, int]]:
    """Retorna as matrículas/Registros Auxiliares que precisam ser lidos.

    O texto é consultado somente durante a requisição e não é persistido.
    """
    referencias = set()
    for item in protocolo_json.get("itens_do_pedido") or []:
        chave = _chave_registro(item)
        if not chave or chave[1] <= 0:
            continue
        if chave[0] == "M":
            if _codigo_ato_registrado(item):
                referencias.add(chave)
            continue
        registrado = item.get("atos_registrados") or {}
        if registrado.get("ato_tipo") is not None and registrado.get("ato_numero") is not None:
            referencias.add(chave)
    return referencias


def registros_alterados_no_protocolo(protocolo_json: dict) -> set[tuple[str, int]]:
    """Matrículas e Registros Auxiliares que este protocolo efetivamente alterou.

    Matrículas seguem a numeração registral R/AV. No Registro Auxiliar, a Tri7
    pode devolver tipo ``S`` e ato número zero mesmo após o registro; por isso,
    nele a presença objetiva do ato registrado é a evidência utilizada.
    """
    alterados = set()
    for item in protocolo_json.get("itens_do_pedido") or []:
        chave = _chave_registro(item)
        if not chave or chave[1] <= 0:
            continue
        if chave[0] == "M" and _codigo_ato_registrado(item):
            alterados.add(chave)
            continue
        registrado = item.get("atos_registrados") or {}
        if (
            chave[0] != "M"
            and registrado.get("ato_tipo") is not None
            and registrado.get("ato_numero") is not None
        ):
            alterados.add(chave)
    return alterados


def _codigo_ato_registrado(item: dict) -> tuple[str, int] | None:
    registrado = item.get("atos_registrados") or {}
    tipo = _normalizar(str(registrado.get("ato_tipo") or ""))
    numero = registrado.get("ato_numero")
    if numero is None or tipo not in {"A", "AV", "R"}:
        return None
    return ("AV" if tipo in {"A", "AV"} else "R", int(numero))


def _atos_do_texto(texto: str) -> list[tuple[tuple[str, int], str]]:
    resultado = []
    for ato in separar_atos(texto):
        match = re.fullmatch(r"(R|AV)\.0*(\d+)", ato["codigo"], re.IGNORECASE)
        if match:
            resultado.append(((match.group(1).upper(), int(match.group(2))), ato["texto"]))
    return resultado


def codigos_atos_confirmados(resposta_atos: dict) -> set[tuple[str, int]]:
    """Normaliza R./Av. registrados pelo endpoint ``matricula-atos``."""
    confirmados = set()
    if not isinstance(resposta_atos, dict):
        return confirmados
    for item in resposta_atos.get("atos") or []:
        if not isinstance(item, dict) or _normalizar(str(item.get("status") or "")) != "REGISTRADO":
            continue
        codigo = _normalizar(str(item.get("ato") or ""))
        match = re.fullmatch(r"(R|AV)\.?0*(\d+)", codigo)
        if match:
            confirmados.add((match.group(1), int(match.group(2))))
    return confirmados


def _decimal_monetario(valor: object) -> Decimal | None:
    if isinstance(valor, bool) or valor is None:
        return None
    try:
        if isinstance(valor, (int, float, Decimal)):
            return Decimal(str(valor)).quantize(Decimal("0.01"))
        texto = str(valor).strip().replace("R$", "").replace(" ", "")
        if not texto:
            return None
        if "," in texto:
            texto = texto.replace(".", "").replace(",", ".")
        return Decimal(texto).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _total_cotacao_no_texto(texto: str) -> Decimal | None:
    encontrados = PADRAO_TOTAL_COTACAO.findall(texto or "")
    if not encontrados:
        return None
    return _decimal_monetario(encontrados[-1].rstrip("."))


def _formatar_reais(valor: Decimal) -> str:
    formatado = f"{valor:,.2f}"
    return formatado.replace(",", "_").replace(".", ",").replace("_", ".")


def _grupos_de_selo(item: dict) -> set[str]:
    grupos = set()
    for selo in item.get("selos") or []:
        if not isinstance(selo, dict):
            continue
        agrupador = str(selo.get("selo_agrupador") or "").strip()
        if agrupador:
            grupos.add(agrupador)
    return grupos


def _regra_total_custas_agrupadas(
    protocolo_json: dict,
    textos_registros: dict[tuple[str, int], str] | None = None,
) -> list[dict]:
    """Compara a cotação do ato com todos os itens do mesmo selo agrupador.

    Na Tri7, o total impresso no ato principal pode reunir as custas do ato,
    prenotação, busca e outros itens do agrupamento. Portanto, comparar esse
    texto apenas com ``total_do_item`` do ato principal produz falso erro.

    Quando o agrupamento produz matrícula e Registro Auxiliar, cada saída tem
    cotação própria. Nesse caso, a soma das cotações impressas nas duas saídas
    deve ser comparada à soma de todos os itens agrupados. Entre vários atos
    somente de matrícula, preserva a cautela anterior e não tenta repartir
    custos sem informação suficiente.
    """
    textos_registros = textos_registros or {}
    itens = protocolo_json.get("itens_do_pedido") or []
    por_grupo: dict[str, list[dict]] = {}
    for item in itens:
        for grupo in _grupos_de_selo(item):
            por_grupo.setdefault(grupo, []).append(item)

    ocorrencias = []
    alvos_conferidos: set[tuple[tuple[str, int], tuple[str, int]]] = set()
    for itens_grupo in por_grupo.values():
        if len(itens_grupo) < 2:
            continue
        totais = [
            _decimal_monetario((item.get("detalhes_emolumentos") or {}).get("total_do_item"))
            for item in itens_grupo
        ]
        if any(total is None for total in totais):
            continue
        candidatos = []
        for item, total in zip(itens_grupo, totais):
            chave = _chave_registro(item)
            if not chave or chave[1] <= 0 or total <= 0:
                continue
            registrado = item.get("atos_registrados") or {}
            if chave[0] == "M":
                codigo = _codigo_ato_registrado(item)
                if codigo:
                    candidatos.append((item, chave, codigo))
            elif registrado.get("ato_tipo") is not None and registrado.get("ato_numero") is not None:
                candidatos.append((
                    item,
                    chave,
                    (
                        _normalizar(str(registrado.get("ato_tipo") or "REG")),
                        int(registrado.get("ato_numero") or 0),
                    ),
                ))
        if not candidatos:
            continue
        tipos_saida = {chave[0] for _item, chave, _codigo in candidatos}
        if len(candidatos) > 1 and tipos_saida == {"M"}:
            continue

        totais_saidas = []
        rotulos_saidas = []
        alvos_grupo = []
        for _item, chave, codigo in candidatos:
            alvo = (chave, codigo)
            if alvo in alvos_conferidos:
                continue
            texto_registro = textos_registros.get(chave)
            if not texto_registro:
                totais_saidas = []
                break
            if chave[0] == "M":
                bloco = dict(_atos_do_texto(texto_registro)).get(codigo)
                total_saida = _total_cotacao_no_texto(bloco or "")
                rotulo = f"{codigo[0]}.{codigo[1]}"
            else:
                total_saida = _total_cotacao_no_texto(texto_registro)
                rotulo = f"Registro Auxiliar {chave[1]:,}".replace(",", ".")
            if total_saida is None:
                totais_saidas = []
                break
            totais_saidas.append(total_saida)
            rotulos_saidas.append(rotulo)
            alvos_grupo.append(alvo)
        if not totais_saidas or len(totais_saidas) != len(candidatos):
            continue
        alvos_conferidos.update(alvos_grupo)

        total_texto = sum(totais_saidas, Decimal("0.00"))
        total_agrupado = sum(totais, Decimal("0.00"))
        if total_texto != total_agrupado:
            rotulo = " e ".join(rotulos_saidas)
            ocorrencias.append({
                "regra": "TOTAL_CUSTAS_DIVERGENTE",
                "gravidade": "GRAVE",
                "descricao": (
                    f"{rotulo}: total das cotações R$ {_formatar_reais(total_texto)} "
                    f"diverge da soma dos itens agrupados "
                    f"(R$ {_formatar_reais(total_agrupado)})."
                ),
            })
    return ocorrencias


def _ocorrencias_campos_ato(codigo: tuple[str, int], texto: str) -> list[dict]:
    return _ocorrencias_campos_ato_com_isencao(codigo, texto, isento=False)


def _item_isento_de_custas(item: dict) -> bool:
    """Reconhece a isenção pela discriminação objetiva da Tri7.

    Não basta o texto da tabela sugerir gratuidade: todos os campos
    financeiros que a API informou precisam estar zerados, inclusive o total.
    Assim um ato comum com minuta ainda incompleta continua sendo alertado.
    """
    detalhes = item.get("detalhes_emolumentos")
    if not isinstance(detalhes, dict) or "total_do_item" not in detalhes:
        return False
    campos = (
        "emolumentos", "fundos", "iss", "total_do_item", "tx_jud",
        "valor_base_calculo",
    )
    valores = [detalhes[campo] for campo in campos if campo in detalhes]
    if len(valores) < 2:
        return False
    return all(
        isinstance(valor, (int, float))
        and not isinstance(valor, bool)
        and abs(float(valor)) < 0.000001
        for valor in valores
    )


def _ocorrencias_campos_ato_com_isencao(
    codigo: tuple[str, int], texto: str, *, isento: bool,
) -> list[dict]:
    rotulo = f"{codigo[0]}.{codigo[1]}"
    ocorrencias = []
    # A pedido da Serventia, o Livro de Protocolos não confere datas neste
    # momento. Isso inclui tanto a data do relatório quanto placeholders
    # internos como "xx.07.2026" e o fecho "de de".
    if not isento and (
        PADRAO_VALOR_EM_BRANCO.search(texto) or PADRAO_SELO_EM_BRANCO.search(texto)
    ):
        ocorrencias.append({
            "regra": "CAMPO_EM_BRANCO",
            "gravidade": "ATENCAO",
            "descricao": f"{rotulo}: selo e/ou cotação (emolumentos/ISSQN/taxa/total) aparentam estar em branco.",
        })
    return ocorrencias


def _regra_ordem_itens_protocolo(protocolo_json: dict) -> list[dict]:
    """Confere a ordem registral por fase, sem confiar na ordem do JSON.

    A Tri7 pode devolver o ato principal antes das averbações preparatórias e
    vários selos podem ter o mesmo segundo. A numeração R./AV. é a fonte da
    sequência efetivamente praticada. Nessa sequência, atualizações do imóvel
    devem anteceder atualizações das pessoas e, por fim, o ato principal.
    """
    padrao_imovel = re.compile(
        r"\b(?:CODIGO DE ENDERECAMENTO POSTAL|CEP|ITR|CCIR|INCRA|CAR|CCI|"
        r"CADASTRO MUNICIPAL|DESIGNACAO CADASTRAL|ATUALIZACAO DE DESIGNACAO|"
        r"DENOMINACAO DO IMOVEL|LOGRADOURO|NUMERACAO PREDIAL)\b"
    )
    padrao_pessoa = re.compile(
        r"\b(?:INSERCAO|ATUALIZACAO|RETIFICACAO)\s+(?:DE\s+)?(?:DADOS|"
        r"QUALIFICACAO|CPF|CNPJ|NOME|ESTADO CIVIL|REGIME DE CASAMENTO)\b|"
        r"\b(?:REGIME DE CASAMENTO|ALTERACAO DE NOME|QUALIFICACAO PESSOAL)\b"
    )

    def fase(item: dict) -> int:
        natureza = _normalizar(str(item.get("natureza_formal_descricao") or ""))
        if padrao_imovel.search(natureza):
            return 0
        if padrao_pessoa.search(natureza):
            return 1
        return 2

    ocorrencias = []
    sequencias: dict[tuple[str, int], list[tuple[tuple[str, int], int, str]]] = {}
    for item in protocolo_json.get("itens_do_pedido") or []:
        chave = _chave_registro(item)
        registrado = item.get("atos_registrados") or {}
        tipo = _normalizar(str(registrado.get("ato_tipo") or ""))
        numero = registrado.get("ato_numero")
        if not chave or chave[0] != "M" or numero is None or tipo not in {"A", "AV", "R", "M"}:
            continue
        try:
            codigo = ("AV" if tipo in {"A", "AV"} else tipo, int(numero))
        except (TypeError, ValueError):
            continue
        natureza = _colapsar_espacos(str(item.get("natureza_formal_descricao") or ""))
        sequencias.setdefault(chave, []).append((codigo, fase(item), natureza))

    for chave, itens_sequencia in sequencias.items():
        # Um mesmo ato pode aparecer repetido em itens de custas. Consolida-o
        # e usa a numeração oficial, nunca a posição instável no retorno.
        por_codigo: dict[tuple[str, int], tuple[int, str]] = {}
        for codigo, fase_item, natureza in itens_sequencia:
            anterior = por_codigo.get(codigo)
            if anterior is None or fase_item < anterior[0]:
                por_codigo[codigo] = (fase_item, natureza)
        ordenados = sorted(
            ((codigo, *dados) for codigo, dados in por_codigo.items()),
            key=lambda valor: valor[0][1],
        )
        for anterior, atual in zip(ordenados, ordenados[1:]):
            codigo_anterior, fase_anterior, natureza_anterior = anterior
            codigo_atual, fase_atual, natureza_atual = atual
            if fase_atual < fase_anterior:
                ocorrencias.append({
                    "regra": "ORDEM_OPERACIONAL",
                    "gravidade": "GRAVE",
                    "descricao": (
                        f"Matrícula {chave[1]}: sequência operacional incompatível; "
                        f"{codigo_anterior[0]}.{codigo_anterior[1]} ({natureza_anterior}) "
                        f"foi numerado antes de {codigo_atual[0]}.{codigo_atual[1]} "
                        f"({natureza_atual})."
                    ),
                })
    return ocorrencias


def _regra_ordem_e_texto_dos_atos(
    protocolo_json: dict,
    textos_registros: dict[tuple[str, int], str] | None = None,
    falhas_textos: dict[tuple[str, int], str] | None = None,
    atos_confirmados: dict[tuple[str, int], set[tuple[str, int]]] | None = None,
) -> list[dict]:
    ocorrencias = []
    textos_registros = textos_registros or {}
    falhas_textos = falhas_textos or {}
    atos_confirmados = atos_confirmados or {}
    alvos_por_registro: dict[tuple[str, int], dict[tuple[str, int], list[dict]]] = {}
    for item in protocolo_json.get("itens_do_pedido") or []:
        chave = _chave_registro(item)
        codigo = _codigo_ato_registrado(item)
        # Ordem R./AV. só existe em matrícula. Registro Auxiliar usa outra
        # estrutura e não deve ser comparado como se fosse Livro 2.
        if chave and chave[0] == "M" and codigo:
            alvos_por_registro.setdefault(chave, {}).setdefault(codigo, []).append(item)

    for chave, itens_por_codigo in alvos_por_registro.items():
        codigos_alvo = set(itens_por_codigo)
        if chave in falhas_textos:
            ocorrencias.append({
                "regra": "TEXTO_INDISPONIVEL",
                "gravidade": "ATENCAO",
                "descricao": f"Não foi possível conferir o texto atual da matrícula {chave[1]}: {falhas_textos[chave]}",
            })
            continue
        texto = textos_registros.get(chave)
        if not texto:
            # A função também é usada isoladamente em testes; sem o texto
            # oficial, não tenta validar existência nem conteúdo do ato.
            continue
        atos_texto = _atos_do_texto(texto)
        por_codigo = {codigo: bloco for codigo, bloco in atos_texto}
        encontrados = {codigo for codigo, _bloco in atos_texto if codigo in codigos_alvo}
        # O cadastro objetivo de atos pode estar adiante do texto corrido na
        # Tri7. Se ele confirma o R./AV. como Registrado, não acusa ausência
        # do ato; as verificações de conteúdo só são executadas quando o bloco
        # textual correspondente estiver realmente disponível.
        encontrados |= codigos_alvo & atos_confirmados.get(chave, set())
        ausentes = sorted(codigos_alvo - encontrados, key=lambda codigo: codigo[1])
        for codigo in ausentes:
            ocorrencias.append({
                "regra": "ATO_NAO_LOCALIZADO",
                "gravidade": "GRAVE",
                "descricao": f"{codigo[0]}.{codigo[1]} não foi localizado no texto atual da matrícula {chave[1]}.",
            })
        for codigo in sorted(codigos_alvo, key=lambda valor: valor[1]):
            if codigo in por_codigo:
                isento = any(_item_isento_de_custas(item) for item in itens_por_codigo[codigo])
                ocorrencias.extend(_ocorrencias_campos_ato_com_isencao(
                    codigo, por_codigo[codigo], isento=isento,
                ))
    return ocorrencias


def _regra_data_um_dia_antes(item_pdf: dict, data_esperada: date) -> list[dict]:
    if item_pdf.get("status") != "REGISTRADO" or not item_pdf.get("data"):
        return []
    data_linha = date.fromisoformat(item_pdf["data"])
    if data_linha != data_esperada:
        return [{
            "regra": "DATA_DIVERGENTE",
            "gravidade": "GRAVE",
            "descricao": (
                f"Data do registro ({data_linha.strftime('%d/%m/%Y')}) diferente da esperada "
                f"({data_esperada.strftime('%d/%m/%Y')})."
            ),
        }]
    return []


def conferir_protocolo(
    item_pdf: dict,
    protocolo_json: dict,
    data_esperada: date,
    excecoes_natureza_titulo: frozenset[tuple[str, str]] = frozenset(),
    textos_registros: dict[tuple[str, int], str] | None = None,
    falhas_textos: dict[tuple[str, int], str] | None = None,
    atos_confirmados: dict[tuple[str, int], set[tuple[str, int]]] | None = None,
) -> list[dict]:
    return [
        *_regra_natureza_bate_com_titulo(protocolo_json, excecoes_natureza_titulo),
        *_regra_busca_com_matricula(protocolo_json),
        *_regra_ordem_itens_protocolo(protocolo_json),
        *_regra_ordem_e_texto_dos_atos(
            protocolo_json, textos_registros, falhas_textos, atos_confirmados,
        ),
        *_regra_total_custas_agrupadas(protocolo_json, textos_registros),
        # Regra de data desativada por enquanto: mesmo com inferir_data_esperada()
        # olhando a própria folha em vez de "hoje - 1 dia" fixo, ainda gerou
        # ocorrência em casos legítimos. Fica pausada até a lógica ser revista;
        # _regra_data_um_dia_antes/item_pdf/data_esperada seguem disponíveis
        # pra quando isso for retomado.
    ]
