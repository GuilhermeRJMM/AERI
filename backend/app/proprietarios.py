import re
import unicodedata
import math
from difflib import SequenceMatcher
from types import SimpleNamespace

from backend.app.parser import separar_atos

def limpar_nome(nome):
    nome = ''.join(c for c in unicodedata.normalize('NFD', nome) if unicodedata.category(c) != 'Mn')
    nome = nome.upper().strip()
    nome = re.sub(r'^(O\s+)?ESPOLIO DE\s+', '', nome)
    nome = re.sub(r'^SUCESSORES DE\s+', '', nome)
    return nome

def padronizar_chave(cpf, nome):
    cpf_limpo = re.sub(r'\D', '', cpf)
    # MEGA BRAIN: Mantém os 14 dígitos do CNPJ intactos, mas corta o CPF para 11
    if len(cpf_limpo) == 14:
        return cpf_limpo 
    elif len(cpf_limpo) >= 11:
        return cpf_limpo[:11] 
    elif len(cpf_limpo) >= 9: 
        return cpf_limpo
    return limpar_nome(nome)

def parse_valor_monetario(texto):
    valor = re.sub(r'[^\d,.]', '', texto or '')
    valor = valor.strip(',.')
    if not valor:
        return None
    # OCR histórico: "5.5000.000,00" (zero duplicado no grupo de milhar) e
    # "5.500,000, 00" (vírgula usada também como separador de milhar).
    valor = re.sub(r'\.(\d{3})0(?=[.,])', r'.\1', valor)
    if valor.count(',') > 1:
        inteiro, decimal = valor.rsplit(',', 1)
        valor = re.sub(r'[.,]', '', inteiro) + '.' + decimal
        try:
            return float(valor)
        except ValueError:
            return None
    if ',' in valor:
        valor = valor.replace('.', '').replace(',', '.')
    else:
        pontos = valor.count('.')
        if pontos > 1:
            partes = valor.split('.')
            valor = ''.join(partes[:-1]) + '.' + partes[-1]
    try:
        return float(valor)
    except ValueError:
        return None

def parse_percentual_declarado(texto):
    """Normaliza percentuais, inclusive vírgula omitida por OCR (8562% = 85,62%)."""
    bruto = str(texto or '').strip()
    valor = float(bruto.replace(',', '.'))
    if valor > 100 and re.fullmatch(r'\d{3,4}', bruto):
        corrigido = valor / 100.0
        if corrigido <= 100:
            return corrigido
    return valor

def parse_percent(texto):
    percentual_resultante_da_quota = re.search(
        r'(\d+(?:[,.]\d+)?)\s*%\s+da\s+quota\s*'
        r'\(\s*(\d+(?:[,.]\d+)?)\s*%\s*\)',
        texto,
        re.I,
    )
    if percentual_resultante_da_quota:
        fator = parse_percentual_declarado(percentual_resultante_da_quota.group(1))
        quota = parse_percentual_declarado(percentual_resultante_da_quota.group(2))
        return fator / 100.0 * quota

    # Inventários podem declarar primeiro o percentual interno do quinhão e,
    # depois, a fração que esse quinhão representa no imóvel. Ex.: 4,1666%
    # ``sobre 50% ... do imóvel`` corresponde a 2,0833% do todo, não a
    # 4,1666%. A restrição a "em pagamento" evita alterar redações em que
    # percentuais independentes apenas aparecem próximos no mesmo ato.
    percentual_sobre_quinhao = re.search(
        r'\bem\s+pagamento\b.{0,500}?'
        r'(\d+(?:[,.]\d+)?)\s*%.{0,500}?'
        r'\bsobre\s+(\d+(?:[,.]\d+)?)\s*%.{0,240}?'
        r'\bdo\s+im[óo]vel\b',
        texto,
        re.I | re.DOTALL,
    )
    if percentual_sobre_quinhao:
        percentual = parse_percentual_declarado(percentual_sobre_quinhao.group(1))
        quinhao = parse_percentual_declarado(percentual_sobre_quinhao.group(2))
        return percentual / 100.0 * quinhao

    parte_monetaria_sobre_quinhao = re.search(
        r'\bparte\s+ideal\s+(?:no\s+valor\s+)?de\s*'
        r'(?:[A-Z]{1,3}\$?\s*)?([\d.,]+).*?'
        r'\bsobre\s+(\d+(?:[,.]\d+)?)\s*%\s*'
        r'(?:do\s+im[óo]vel\s+)?avaliad[oa]\s+por\s*'
        r'(?:[A-Z]{1,3}\$?\s*)?([\d.,]+)',
        texto,
        re.I | re.DOTALL,
    )
    if parte_monetaria_sobre_quinhao:
        parte = parse_valor_monetario(parte_monetaria_sobre_quinhao.group(1))
        quinhao = parse_percentual_declarado(parte_monetaria_sobre_quinhao.group(2))
        total = parse_valor_monetario(parte_monetaria_sobre_quinhao.group(3))
        if parte is not None and total and 0 < parte <= total:
            return parte / total * quinhao

    percentual_correspondente_total = re.search(
        r'(?:o\s+que\s+)?corresponde\s+a\s+'
        r'(\d+(?:[,.]\d+)?)\s*%\s+do\s+im[óo]vel',
        texto,
        re.I,
    )
    if percentual_correspondente_total:
        return parse_percentual_declarado(percentual_correspondente_total.group(1))

    percentual_das_partes = re.search(
        r'(\d+(?:[,.]\d+)?)\s*%\s+das\s+partes?\s+a\s+saber\b',
        texto,
        re.I,
    )
    if percentual_das_partes:
        return parse_percentual_declarado(percentual_das_partes.group(1))

    multiplas_partes_percentuais = re.search(
        r'(?:(\d+)|\b(duas|tr[eê]s|quatro|cinco|seis|sete|oito|nove|dez))\s+'
        r'partes?\s+(?:ideais?\s+)?correspondentes?\s+a\s*'
        r'(\d+(?:[,.]\d+)?)\s*%',
        texto,
        re.I,
    )
    if multiplas_partes_percentuais:
        quantidades = {
            "duas": 2, "tres": 3, "três": 3, "quatro": 4, "cinco": 5,
            "seis": 6, "sete": 7, "oito": 8, "nove": 9, "dez": 10,
        }
        quantidade = (
            int(multiplas_partes_percentuais.group(1))
            if multiplas_partes_percentuais.group(1)
            else quantidades[limpar_nome(multiplas_partes_percentuais.group(2)).lower()]
        )
        percentual = quantidade * parse_percentual_declarado(
            multiplas_partes_percentuais.group(3)
        )
        if percentual <= 100.1:
            return percentual

    duas_partes_monetarias = re.search(
        r'\bduas\s+partes?(?:\s+ideais?)?\s+de\s*'
        r'(?:[A-Z]{1,3}\$?\s*)?([\d.,]+)\s+e\s+'
        r'(?:[A-Z]{1,3}\$?\s*)?([\d.,]+).*?'
        r'na\s+avalia(?:a)?[çc][ãa]o\s+de\s*'
        r'(?:[A-Z]{1,3}\$?\s*)?([\d.,]+)',
        texto,
        re.I | re.DOTALL,
    )
    if duas_partes_monetarias:
        primeira, segunda, total = (
            parse_valor_monetario(valor)
            for valor in duas_partes_monetarias.groups()
        )
        if (
            primeira is not None and segunda is not None and total
            and 0 < primeira + segunda <= total + 0.01
        ):
            return (primeira + segunda) / total * 100.0

    percentual_sobre_parte = re.search(
        r'(\d+(?:[,.]\d+)?)\s*%\s+da\s+parte\s+ideal\s+de\s*'
        r'(?:[A-Z]{1,3}\$?\s*)?([\d.,]+).*?'
        r'na\s+(?:avalia\S*|qualifica\S*)\s+de\s*'
        r'(?:[A-Z]{1,3}\$?\s*)?([\d.,]+)',
        texto,
        re.I | re.DOTALL,
    )
    if percentual_sobre_parte:
        fator = float(percentual_sobre_parte.group(1).replace(',', '.')) / 100.0
        parte = parse_valor_monetario(percentual_sobre_parte.group(2))
        total = parse_valor_monetario(percentual_sobre_parte.group(3))
        if parte is not None and total and 0 < parte <= total:
            return fator * parte / total * 100.0

    fracoes_da_parte = re.search(
        r'(?P<fracoes>\d+\s*/\s*\d+.{0,180}?)\bda\s+parte\s+ideal\s+de\s*'
        r'(?:[A-Z]{1,3}\$?\s*)?(?P<parte>[\d.,]+).*?'
        r'na\s+avalia(?:a)?[çc][ãa]o\s+de\s*'
        r'(?:[A-Z]{1,3}\$?\s*)?(?P<total>[\d.,]+)',
        texto,
        re.I | re.DOTALL,
    )
    if fracoes_da_parte:
        fracoes = [
            int(numerador) / int(denominador)
            for numerador, denominador in re.findall(
                r'(\d+)\s*/\s*(\d+)', fracoes_da_parte.group('fracoes')
            )
            if int(denominador) > 0
        ]
        parte = parse_valor_monetario(fracoes_da_parte.group('parte'))
        total = parse_valor_monetario(fracoes_da_parte.group('total'))
        if fracoes and parte is not None and total and 0 < parte <= total * 1.05:
            percentual_base = parte / total * 100.0
            if abs(percentual_base - 50.0) <= 3.0:
                percentual_base = 50.0
            return math.prod(fracoes) * percentual_base

    fracao_objeto = re.search(
        r'(?:OBJETO|IM[ÓO]VEL)\s*:\s*.{0,120}?parte\s+ideal\s+de\s+'
        r'(\d+)\s*/\s*(\d+)\s+do\s+im[óo]vel',
        texto,
        re.IGNORECASE | re.DOTALL,
    )
    if fracao_objeto and int(fracao_objeto.group(2)) > 0:
        return int(fracao_objeto.group(1)) / int(fracao_objeto.group(2)) * 100.0

    fracao_direta_imovel = re.search(
        r'(?<!\d)(\d+)\s*/\s*(\d+)\s*'
        r'(?:\([^)]{1,80}\)\s*)?(?:do|sobre\s+o)\s+im[óo]vel\s+'
        r'(?:objeto|constante|descrito)\b',
        texto,
        re.I,
    )
    if fracao_direta_imovel and int(fracao_direta_imovel.group(2)) > 0:
        return (
            int(fracao_direta_imovel.group(1))
            / int(fracao_direta_imovel.group(2))
            * 100.0
        )

    # Percentual declarado no título prevalece sobre valores monetários.
    # Sem essa prioridade, "parte ideal de 50% ... avaliação de 700.000,10"
    # era interpretada incorretamente como 50 / 700.000,10.
    percentual_explicito = re.search(
        r'(?:IM[ÓOÃÕ]VEL\s*:\s*(?:equivalente\s+a\s*)?'
        r'|proporção\s+de\s*'
        r'|em\s+pagamento\s+de\s+sua\s+(?:mea[çc][ãa]o|heran[çc]a)\s*'
        r'|parte\s+(?:ideal\s+)?(?:correspondente\s+a\s*|de\s*)?)'
        r'(?:[A-Z]{1,3}\$?\s*)?(\d+(?:,\d+)?)\s*%',
        texto,
        re.IGNORECASE,
    )
    if percentual_explicito:
        return parse_percentual_declarado(percentual_explicito.group(1))

    fracoes_textuais = (
        (r'\b(?:a\s+)?metade\s+do\s+im[óo]vel\b', 50.0),
        (r'\b(?:uma\s+)?ter[çc]a\s+parte\s+do\s+im[óo]vel\b', 100.0 / 3.0),
        (r'\b(?:uma\s+)?quarta\s+parte\s+do\s+im[óo]vel\b', 25.0),
        (r'\b(?:uma\s+)?quinta\s+parte\s+do\s+im[óo]vel\b', 20.0),
        (r'\b(?:um\s+)?sexto\s+do\s+im[óo]vel\b', 100.0 / 6.0),
        (r'\b(?:um\s+)?s[ée]timo\s+do\s+im[óo]vel\b', 100.0 / 7.0),
        (r'\b(?:um\s+)?oitavo\s+do\s+im[óo]vel\b', 12.5),
        (r'\b(?:um\s+)?nono\s+do\s+im[óo]vel\b', 100.0 / 9.0),
        (r'\b(?:um\s+)?d[ée]cimo\s+do\s+im[óo]vel\b', 10.0),
        (r'\btr[eê]s\s+quart[oa]s?\s+do\s+im[óo]vel\b', 75.0),
        (r'\bdois\s+ter[çc]os\s+do\s+im[óo]vel\b', 200.0 / 3.0),
        (r'\btr[eê]s\s+quintos\s+do\s+im[óo]vel\b', 60.0),
        (r'\bdois\s+quintos\s+do\s+im[óo]vel\b', 40.0),
        (r'\bquatro\s+quintos\s+do\s+im[óo]vel\b', 80.0),
        (r'\bcinco\s+sextos\s+do\s+im[óo]vel\b', 500.0 / 6.0),
    )
    for padrao, percentual in fracoes_textuais:
        if re.search(padrao, texto, re.IGNORECASE):
            return percentual

    percentual_do_imovel = re.search(
        r'(?<![\d.,])(?:parte\s+ideal\s+de\s+)?(\d+(?:,\d+)?)\s*%\s*'
        r'(?:\([^)]*\)\s*)?do\s+im[óo]vel\b',
        texto,
        re.IGNORECASE,
    )
    tem_fracao_monetaria = bool(re.search(
        r'(?:parte|porte)\s+(?:ideal|inicial)\s+de\s*(?:[A-Z]{1,3}\$?\s*)?[\d.,]+.*?'
        r'na\s+avali(?:a)?[çc][ãa]o\s+de\s*(?:[A-Z]{1,3}\$?\s*)?[\d.,]+',
        texto,
        re.IGNORECASE | re.DOTALL,
    ))
    if percentual_do_imovel and not tem_fracao_monetaria:
        return parse_percentual_declarado(percentual_do_imovel.group(1))

    multiplas_partes = re.search(
        r'(?:(\d+)|\b(duas|tr[eê]s|quatro|cinco|seis|sete|oito|nove|dez))\s+'
        r'partes?\s+ideais?\s+de\s+(?:[A-Z]{1,3}\$?\s*)?([\d.,]+)'
        r'.{0,120}?na\s+avali(?:a)?[çc][ãa]o\s+de\s+(?:[A-Z]{1,3}\$?\s*)?([\d.,]+)',
        texto,
        re.IGNORECASE | re.DOTALL,
    )
    if multiplas_partes:
        quantidades = {
            "duas": 2, "tres": 3, "três": 3, "quatro": 4, "cinco": 5,
            "seis": 6, "sete": 7, "oito": 8, "nove": 9, "dez": 10,
        }
        quantidade = int(multiplas_partes.group(1)) if multiplas_partes.group(1) else quantidades[multiplas_partes.group(2).lower()]
        parte = parse_valor_monetario(multiplas_partes.group(3))
        total = parse_valor_monetario(multiplas_partes.group(4))
        if parte is not None and total and quantidade * parte <= total + 0.01:
            return quantidade * parte / total * 100.0

    avaliacao_antes_fracao = re.search(
        r'avaliad[oa]\s+por\s*(?:[A-Z]{1,3}\$?\s*)?([\d.,]+).*?'
        r'(?:uma\s+)?fra[çc][ãa]o\s+ideal\s+de\s*(?:[A-Z]{1,3}\$?\s*)?([\d.,]+)',
        texto,
        re.IGNORECASE | re.DOTALL,
    )
    if avaliacao_antes_fracao:
        total = parse_valor_monetario(avaliacao_antes_fracao.group(1))
        parte = parse_valor_monetario(avaliacao_antes_fracao.group(2))
        if parte is not None and total and 0 < parte <= total:
            return parte / total * 100.0

    fracao_sobre_fracao = re.search(
        r'(?:parte|porte)\s+(?:ideal|inicial)\s+de\s*(?:[A-Z]{1,3}\$?\s*)?([\d.,\s]+?)\s*'
        r'(?:\([^)]*\)\s*)?,?\s*na\s+avali(?:a)?[çc][ãa]o\s+de\s*'
        r'(?:[A-Z]{1,3}\$?\s*)?([\d.,\s]+?)\s*'
        r'(?:\([^)]*\)\s*)?,?\s*na\s+parte\s+ideal\s+de\s*'
        r'(?:[A-Z]{1,3}\$?\s*)?([\d.,\s]+?)\s*'
        r'(?:\([^)]*\)\s*)?,?\s*na\s+avali(?:a)?[çc][ãa]o\s+de\s*'
        r'(?:[A-Z]{1,3}\$?\s*)?([\d.,\s]+)',
        texto,
        re.IGNORECASE | re.DOTALL,
    )
    if fracao_sobre_fracao:
        parte_interna, total_interno, parte_externa, total_externo = (
            parse_valor_monetario(valor) for valor in fracao_sobre_fracao.groups()
        )
        if (
            parte_interna is not None and total_interno
            and parte_externa is not None and total_externo
            and 0 < parte_interna <= total_interno
            and 0 < parte_externa <= total_externo
        ):
            return parte_interna / total_interno * parte_externa / total_externo * 100.0

    avaliacao = re.search(
        r'na\s+avali(?:a)?[çc][ãa]o\s+de\s*(?:[A-Z]{1,3}\$?\s*)?([\d.,]+)',
        texto,
        re.IGNORECASE,
    )
    if avaliacao:
        # Escrituras antigas podem enumerar quinhões em redações como
        # "uma de ... e a outra ...", ou repetir "parte ideal" depois da
        # primeira avaliação. Varremos o ato inteiro e desconsideramos
        # denominadores introduzidos por "da/na parte ideal".
        numeradores = re.findall(
            r'(?:'
            r'(?<!da\s)(?<!na\s)(?:parte|porte)\s+(?:ideal|inicial)\s+de'
            r'|(?:a\s+)?(?:primeira|segunda|terceira|quarta|quinta|sexta|s[eé]tima|oitava|nona|d[eé]cima)\s+de'
            r'|(?:uma|outra)\s+(?:de\s+)?'
            r'|corresponde\s+(?:a\s+)?o?\s*valor\s+de'
            r')\s*(?:[A-Z]{1,3}\$?\s*)?([\d.,]+)',
            texto,
            re.IGNORECASE,
        )
        valores = [parse_valor_monetario(valor) for valor in numeradores]
        valores = [valor for valor in valores if valor is not None]
        total = parse_valor_monetario(avaliacao.group(1))
        if len(valores) >= 3 and abs(valores[0] - sum(valores[1:])) <= max(0.01, valores[0] * 0.0001):
            valores = valores[:1]
        elif len(valores) >= 4 and len(valores) % 2 == 0:
            metade = len(valores) // 2
            if all(
                abs(a - b) <= max(0.01, abs(a) * 0.0001)
                for a, b in zip(valores[:metade], valores[metade:])
            ):
                valores = valores[:metade]
        if valores and total and 0 < sum(valores) <= total + 0.01:
            return sum(valores) / total * 100.0

    m_valor = re.search(
        r'(?:(?:parte|porte)\s+)?(?:ideal|inicial|correspondente\s+a)\s+(?:de\s*)?'
        r'(?:[A-Z]{1,3}\$?\s*)?([\d\.,]+).*?'
        r'na\s+(?:avalia\S*|qualifica\S*)\s+de\s*(?:[A-Z]{1,3}\$?\s*)?([\d\.,]+)',
        texto,
        re.IGNORECASE | re.DOTALL
    )
    if m_valor:
        parte = parse_valor_monetario(m_valor.group(1))
        total = parse_valor_monetario(m_valor.group(2))
        if parte is not None and total and 0 <= parte <= total:
            return (parte / total) * 100.0

    m_pagamento = re.search(
        r'\bem\s+pagamento\b.{0,500}?'
        r'(\d+(?:[,.]\d+)?)\s*%.{0,500}?'
        r'\b(?:sobre|do)\s+(?:o\s+)?im[óo]vel\b',
        texto,
        re.IGNORECASE | re.DOTALL,
    )
    if m_pagamento:
        return parse_percentual_declarado(m_pagamento.group(1))

    m0 = re.search(r'IM[ÓOÃ“]VEL\s*:\s*(?:equivalente\s+a\s*)?(\d+(?:,\d+)?)%', texto, re.IGNORECASE)
    if m0: return parse_percentual_declarado(m0.group(1))

    m1 = re.search(r'IMÓVEL\s*:\s*(\d+(?:,\d+)?)%', texto, re.IGNORECASE)
    if m1: return parse_percentual_declarado(m1.group(1))
    
    m2 = re.search(r'proporção de\s*(\d+(?:,\d+)?)%', texto, re.IGNORECASE)
    if m2: return parse_percentual_declarado(m2.group(1))

    m3 = re.search(r'parte\s+correspondente\s+a\s*(\d+(?:,\d+)?)%', texto, re.IGNORECASE)
    if m3: return parse_percentual_declarado(m3.group(1))

    if re.search(r'em\s+pagamento\s+de\s+sua\s+mea[çc][ãa]o', texto, re.I):
        return 50.0
        
    if re.search(r'(totalidade|integralidade|100%|o imóvel constante|o imóvel objeto)', texto, re.IGNORECASE):
        return 100.0
        
    return 100.0


# Sinal amplo (não tenta replicar as ~25 ramificações acima, só pergunta "há
# algum indício de fração/percentual neste trecho?") usado só para saber se o
# 100,0 devolvido por parse_percent() veio de evidência real ou do último
# fallback cego (linha "return 100.0" acima), quando o ato de transferência
# não menciona nenhuma fração reconhecível — ex.: "dois terços", "um oitavo"
# fora da lista, ou uma redação totalmente atípica. Deliberadamente permissivo:
# na dúvida, considera que há evidência, para não gerar alerta de incerteza à
# toa em cima de casos que o parse_percent já sabe interpretar.
_PADRAO_SINAL_FRACAO_OU_PERCENTUAL = re.compile(
    r'\d+(?:[,.]\d+)?\s*%'
    r'|\d+\s*/\s*\d+'
    r'|\bmetade\b|\bter[çc]a\s+parte\b|\bquarta\s+parte\b|\bquinta\s+parte\b'
    r'|\bs[ée]timo\b|\boitavo\b|\bnono\b|\bd[ée]cimo\b|\bsexto\b'
    r'|\btr[eê]s\s+quart[oa]s?\b|\bdois\s+ter[çc]os\b|\btr[eê]s\s+quintos\b'
    r'|\bdois\s+quintos\b|\bquatro\s+quintos\b|\bcinco\s+sextos\b'
    r'|\btotalidade\b|\bintegralidade\b'
    r'|\bo\s+im[óo]vel\s+(?:constante|objeto)\b'
    r'|\bpropor[çc][ãa]o\b|\bfra[çc][ãa]o\s+ideal\b|\bparte\s+ideal\b|\bquinh[ãa]o\b',
    re.IGNORECASE,
)


def percentual_e_presumido(texto: str, percentual: float) -> bool:
    """True quando parse_percent() devolveu 100.0 sem nenhum sinal textual de
    fração/percentual no trecho -- ou seja, foi um chute pelo fallback final,
    não uma leitura real do texto. Usado para marcar a proporção resultante
    como incerta em vez de assumi-la como certeza."""
    if percentual != 100.0:
        return False
    return not _PADRAO_SINAL_FRACAO_OU_PERCENTUAL.search(texto or "")


MARCADOR_PAPEL_NAO_ADQUIRENTE = (
    r"(?:"
    r"(?:\bCOMPAREC(?:ERAM|EU|EM|E)\s+(?:(?:AINDA|TAMB[ÉE]M)\s+)*(?:COMO\s+)?)?"
    r"\bINTERVENIENTES?\b[^:;.\n]{0,180}:"
    r"|(?:^|[.;]\s*)"
    r"(?:\bCOMPAREC(?:ERAM|EU|EM|E)\s+(?:(?:AINDA|TAMB[ÉE]M)\s+)*(?:COMO\s+)?)?"
    r"\b(?:ANUENTES?|GARANTES?|GARANTIDOR(?:A|ES|AS)?|FIADOR(?:A|ES|AS)?|"
    r"AVALISTAS?|COOBRIGAD[OA]S?|TERCEIROS?\s+GARANTIDOR(?:A|ES|AS)?|"
    r"DEVEDOR(?:A|ES|AS)?(?:\s+(?:FIDUCIANTE|SOLID[ÁA]RI[OA]))?|"
    r"CREDOR(?:A|ES|AS)?(?:\s+FIDUCI[ÁA]RI[OA]S?)?|HIPOTECANTES?|"
    r"MUTU[ÁA]RI[OA]S?|EMITENTES?)\b[^:;.\n]{0,140}:"
    r")"
)


def extrair_bloco(texto, tipo):
    if tipo == "ADQUIRENTE":
        # Nas divisões, a lista de "outorgados" pode reunir todos os
        # condôminos apenas para qualificação. A cláusula "coube
        # exclusivamente" é que identifica quem recebeu este quinhão.
        if re.search(r'\bDIVIS[ÃA]O\b|\bDIVISÓRIA\b', texto, re.I):
            m = re.search(
                r'\bcoube\s+exclusivamente\s+(?:a|ao|aos|à|às)\s+'
                r'(?:(?:cond[oô]min[oa]s?|meeir[oa]s?|herdeir[oa]s?)\s+)?(.*?)'
                r'(?=\bo\s+quinh[ãa]o\b|\bem pagamento\b|\bem virtude\b|'
                r',\s*(?:j[áa]\s+qualificad[oa]s?\s*,\s*)?'
                r'(?:a\s+gleba|o\s+im[óo]vel|a\s+[áa]rea)\b|'
                r',\s*no\s+valor\b|\bconforme\b|'
                r'\.\s*(?:\*?\s*NOTA\b|O\s+referido|DOU\s+F[ÉE])|\Z)',
                texto,
                re.I | re.DOTALL,
            )
            if m:
                return m.group(1).strip().rstrip(';, ')

        # Em divórcios antigos, "outorgantes e reciprocamente outorgados" nomeia
        # o casal inteiro, mas o próprio ato pode atribuir a fração a somente um
        # deles. A cláusula dispositiva prevalece sobre o rótulo genérico.
        if re.search(r'\bDIV[ÓO]RCIO\b', texto, re.I):
            m = re.search(
                r'\b(?:fica|ficou|ficando)\s+pertencendo\s+'
                r'(?:a|ao|aos|à|às)\s+(.*?)'
                r'(?=,\s*(?:brasileir[oa]|solteir[oa]|casad[oa]|divorciad[oa]|vi[úu]v[oa])\b|'
                r'\.\s*(?:O\s+referido|DOU\s+F[ÉE])|\Z)',
                texto,
                re.I | re.DOTALL,
            )
            if m:
                return m.group(1).strip().rstrip(';, ')

        m = re.search(
            r'\b(?:ADQUIRENTES?(?:/(?:TOMADOR(?:ES)?|'
            r'(?:PRIMEIR|SEGUND)[OA]S?\s+PERMUTANTES?))?|'
            r'OUTORGADOS?|DONAT[ÁA]RI[OA]S?|ADJUDICANTES?|'
            r'ARREMATANTES?|COMPRADOR(?:ES)?)\s*:\s*(.*?)'
            r'(?=\b(?:IM[ÓO]VEL|OBJETO|ORIGEM|FORMA\s+DO\s+T[ÍI]TULO|'
            r'TRANSMITENTES?|OUTORGANTES?|DOADORES?)\s*:|'
            + MARCADOR_PAPEL_NAO_ADQUIRENTE +
            r'|\*NOTA|\bDOU\s+F[ÉE]\b|\Z)',
            texto,
            re.I | re.DOTALL,
        )
        if m: return m.group(1).strip().rstrip(';, ')

        m = re.search(r'\bvend(?:eu|eram)\s+.{0,300}?\bpara\s+(.{0,400}?)(?=\bpelo valor\b|\bpelo preço\b|;|\.\s*Dou|\.\s*O referido|\Z)', texto, re.I | re.DOTALL)
        if m: return m.group(1).strip().rstrip(';, ')

        m = re.search(r'\badjudicante\s*:\s*(.*?)(?=\*NOTA|;|\.\s*Dou|\.\s*DOU|\Z)', texto, re.I | re.DOTALL)
        if m: return m.group(1).strip().rstrip(';, ')

        m = re.search(r'\barrematante\s*:\s*(.*?)(?=\*NOTA|\bCOTAÇÃO\b|;|\.\s*Dou|\.\s*DOU|\Z)', texto, re.I | re.DOTALL)
        if m: return m.group(1).strip().rstrip(';, ')

        m = re.search(
            r'\b(?:domínio|imóvel|matrícula)\s+foi\s+declarad[oa]\s+(?:em|a)\s+favor\s+de\s*:?\s*'
            r'(.*?)(?=\*NOTA|\bCOTAÇÃO\b|\.\s*Dou|\.\s*DOU|\Z)',
            texto,
            re.I | re.DOTALL,
        )
        if m: return m.group(1).strip().rstrip(';, ')

        m = re.search(
            r'\bação\s+de\s+usucapião\s*,?\s*promovida\s+por\s+(.*?)'
            r'(?=\s+em\s+desfavor\b|\s+contra\b|\*NOTA|\bCOTAÇÃO\b|\.\s*Dou|\.\s*DOU|\Z)',
            texto,
            re.I | re.DOTALL,
        )
        if m: return m.group(1).strip().rstrip(';, ')

        # Alguns registros históricos omitem a preposição "por" antes da
        # relação numerada dos compradores: "foi adquirido 1)- ...; 2)- ...".
        m = re.search(
            r'\bfoi\s+adquirid[oa]\s*:?\s*'
            r'((?:\(?\d{1,3}\)?\s*[-)]\s*).*?)'
            r'(?=\bpor\s+compra\s+feita\b)',
            texto,
            re.I | re.DOTALL,
        )
        if m:
            return m.group(1).strip().rstrip(';, ')

        m = re.search(
            r'foi\s+incorporad[oa]\s+ao\s+patrim[oô]nio\s+d[oa]\s+(?:sociedade\s+empres[áa]ria\s+limitada\s+)?'
            r'(.*?)(?=\bpor\s+integraliza[çc][ãa]o\s+feita\b|\bO\s+Capital\s+Social\b|\*NOTA|\bDOU\s+F[ÉE]\b)',
            texto,
            re.I | re.DOTALL,
        )
        if m: return m.group(1).strip().rstrip(';, ')

        m = None if re.search(r'\blavrada\b', texto, re.I) else re.search(
            r';\s*(.*?)(?=,?\s*adquiriu\s+por\s+compra\b)',
            texto,
            re.I | re.DOTALL,
        )
        if m and m.group(1).strip().rstrip(';, '): return m.group(1).strip().rstrip(';, ')

        m = re.search(
            r'lavrada\b.{0,200}?,\s*(.{0,400}?)(?=[;,]\s*adquiri(?:u|do)\s+por\s+compra\b)',
            texto,
            re.I | re.DOTALL,
        )
        if m:
            t = m.group(1).strip().rstrip(';, ')
            t = re.sub(
                r'^.*\bfls?\.?\s*[\w\-\/]+(?:\s+e\s+verso|\s*v[ºo°]?)?[;,.]\s*',
                '',
                t,
                flags=re.I | re.DOTALL,
            )
            t = re.sub(
                r'^.*\bL[º°o]\s*\d+\s*,\s*(?:fls?\.?\s*)?'
                r'[\w\-\/]+(?:\s+e\s+verso|\s*v[ºo°]?|ev)?[;,.]\s*',
                '',
                t,
                flags=re.I | re.DOTALL,
            )
            return t

        m = re.search(r'OUTORGADO[S]?\s*:(.*?)(?=\bIM[ÓO]VEL\s*:|\bORIGEM\s*:|\bFORMA DO T[ÍI]TULO\b)', texto, re.I | re.DOTALL)
        if m: return m.group(1).strip().rstrip(';, ')

        m = re.search(r'ADQUIRENTE[S]?\s*:(.*?)(?=\bIM[ÓO]VEL\s*:|\bORIGEM\s*:|\bFORMA DO TÍTULO\b)', texto, re.I | re.DOTALL)
        if m: return m.group(1).strip().rstrip(';, ')

        m = re.search(r'DONAT[AÁ]RI[OA]S?\s*:(.*?)(?=\bIM[ÓOÃ“]VEL\s*:|\bOBJETO\s*:|\bORIGEM\s*:|\bFORMA DO T[ÍI]TULO\b)', texto, re.I | re.DOTALL)
        if m: return m.group(1).strip().rstrip(';, ')

        m = re.search(r'adquirid[oa]\s+(?:por|pel[oa])\s*:?\s*(.*?)(?=\bpor compra\b|\bpelo preço\b|\bem pagamento\b|\bpor doação\b)', texto, re.I | re.DOTALL)
        if m:
            bloco = re.split(
                r'\bnest[ea]\s+ato\s+representad[oa]s?\b|\bdevidamente\s+representad[oa]s?\b',
                m.group(1),
                maxsplit=1,
                flags=re.I,
            )[0]
            return bloco.strip().rstrip(';, ')

        m = re.search(
            r'\bfoi\s+partilhad[oa]\s+entre\s*:?\s*(.*?)'
            r'(?=\*NOTA|\bDOU\s+F[ÉE]\b|\Z)',
            texto,
            re.I | re.DOTALL,
        )
        if m:
            return m.group(1).strip().rstrip(';, ')

        m = re.search(
            r'\bpassou\s+a\s+pertencer\s+aos?\s+primeiros?\s+permutantes?\s+'
            r'(.*?)(?=\bsendo\s+transmitentes?\b|\bpelo\s+valor\b|\bcondi[çc][õo]es\b|\Z)',
            texto,
            re.I | re.DOTALL,
        )
        if m:
            return m.group(1).strip().rstrip(';, ')

        m = re.search(
            r'coube\s+(?:exclusivamente\s+)?(?:a|ao|aos|à|às|á|ás)\s+'
            r'(?:(?:cond[oô]min[oa]s?|meeir[oa]s?|herdeir[oa]s?|'
            r'arrematantes?)\s*:?\s+)?(.*?)'
            r'(?=\bem pagamento\b|\bem virtude\b|\bparte\s+ideal\b|\ba totalidade\b|'
            r'\bo quinh[ãa]o\b|,\s*\d+(?:[,.]\d+)?\s*%|\bpor aquisi[çc][ãa]o\b|\bconforme\b|'
            r',\s*no\s+valor\b|;\s*o\s+im[óo]vel\b|\bcondi[çc][õo]es\b)',
            texto,
            re.I | re.DOTALL,
        )
        if m:
            t = m.group(1).strip().rstrip(';, ')
            t = re.sub(
                r'^(?:o\s+|a\s+|os\s+|as\s+)?'
                r'(?:(?:únic[oa]s?|herdeir[oa]s?(?:-cessionári[oa]s?)?|cessionári[oa]s?|filh[oa]s?|net[oa]s?|viúv[oa]s?|meeir[oa]s?)[,\s]*)*'
                r'(?:e\s+cessionári[oa]s?\s+)?[:\-]?\s*',
                '',
                t,
                flags=re.I
            ).strip(' ,;:-')
            correcao = re.search(
                r'\bdigo\s*,\s*([A-ZÀ-Ú][^,;]{2,120}),',
                t,
                re.I,
            )
            if correcao:
                t = t[correcao.start(1):]
            return t

    elif tipo == "TRANSMITENTE":
        m = re.search(
            r'\bsendo\s+transmitentes?\s+os\s+segundos?\s+permutantes?\s+(.*?)'
            r'(?=\bneste\s+ato\s+(?:assistid|representad)|\bpelo\s+valor\b|'
            r'\bcondi[çc][õo]es\b|\bO\s+referido\b|\Z)',
            texto,
            re.I | re.DOTALL,
        )
        if m:
            return m.group(1).strip().rstrip(';, ')

        m = re.search(
            r'\bim[óo]vel\s+objeto\s+da\s+presente\s+matr[íi]cula\s+'
            r'de\s+propriedade\s+de\s+(.*?)(?=,\s*avaliad[oa]\b)',
            texto,
            re.I | re.DOTALL,
        )
        if m:
            return m.group(1).strip().rstrip(';, ')

        m = re.search(
            r'por\s+integraliza[çc][ãa]o\s+feita\s+pel[oa]\s+(?:s[oó]ci[oa]\s+)?'
            r'(.*?)(?=,\s*com\s+plena\s+anu[êe]ncia|\bO\s+Capital\s+Social\b|\*NOTA|\bDOU\s+F[ÉE]\b)',
            texto,
            re.I | re.DOTALL,
        )
        if m: return m.group(1).strip().rstrip(';, ')

        m = re.search(
            r'por\s+compra(?:\s+compra)?\s+feita(?:\s+feita)?\s+(?:a|à|ao|aos|às)\s*:?\s*(.*?)'
            r'(?=\bpelo valor\b|\bpelo preço\b|,?\s+sobre\s+o\s+im[óo]vel\b|\.\s*O referido|\Z)',
            texto,
            re.I | re.DOTALL,
        )
        if m:
            bloco = re.split(
                r';?\s*(?:e\s+)?como\s+anuentes?\b|'
                r'\bdo\s+t[íi]tulo\s+consta\s+(?:ainda\s+)?como\s+anuentes?\b',
                m.group(1),
                maxsplit=1,
                flags=re.I,
            )[0]
            return bloco.strip().rstrip(';, ')

        m = re.search(r'OUTORGANTE[S]?\s*:(.*?)(?=\bOUTORGADO[S]?\s*:|\bIM[ÓO]VEL\s*:)', texto, re.I | re.DOTALL)
        if m: return m.group(1).strip().rstrip(';, ')

        m = re.search(
            r'TRANSMITENTE[S]?(?:/(?:DADOR(?:ES)?|DOADOR(?:ES)?|'
            r'(?:PRIMEIR|SEGUND)[OA]S?\s+PERMUTANTES?))?\s*:(.*?)'
            r'(?=\bADQUIRENTE[S]?(?:/(?:TOMADOR(?:ES)?|'
            r'(?:PRIMEIR|SEGUND)[OA]S?\s+PERMUTANTES?))?\s*:|\bIM[ÓO]VEL\s*:)',
            texto,
            re.I | re.DOTALL,
        )
        if m: return m.group(1).strip().rstrip(';, ')

        m = re.search(r'DOADOR(?:A|ES|AS)?\s*:(.*?)(?=\bINTERVENIENTE\s*:|\bDONAT[AÁ]RI[OA]S?\s*:|\bOBJETO\s*:|\bIM[ÓOÃ“]VEL\s*:)', texto, re.I | re.DOTALL)
        if m: return m.group(1).strip().rstrip(';, ')

        m = re.search(
            r'por\s+compra\s+feita(?:\s+feita)?\s+'
            r'(?:(?:a|à|ao|aos|às)\s+)?'
            r'(.*?)(?=\bpelo\s+preço\b|\bpelo\s+valor\b|;|\.\s*O\s+referido)',
            texto,
            re.I | re.DOTALL,
        )
        if m: return m.group(1).strip().rstrip(';, ')
        
        m = re.search(
            r'por\s+doa[çc][ãa]o\s+que\s+(?:lhe|lhes)\s+(?:fez|fizeram)\s+(.*?)'
            r'(?=\bno\s+valor\b|\bpelo\s+valor\b|\bsem\s+condi[çc][õo]es\b|;|\.\s*O\s+referido)',
            texto,
            re.I | re.DOTALL,
        )
        if m: return m.group(1).strip().rstrip(';, ')

        m = re.search(
            r'(?:por|em)\s+doa[çc][ãa]o\s+feita\s+por\s+(.*?)'
            r'(?=\bno\s+valor\b|\bpelo\s+valor\b|\bsem\s+condi[çc][õo]es\b|;|\.\s*O\s+referido|\Z)',
            texto,
            re.I | re.DOTALL,
        )
        if m: return m.group(1).strip().rstrip(';, ')

        m = re.search(r'deixados por falecimento\s+(?:de\s+)?(.*?)(?=,|\s+julgado|;)', texto, re.I | re.DOTALL)
        if m: return m.group(1).strip().rstrip(';, ')

    return ""

def extrair_pessoas(texto_bloco):
    pessoas = []
    if not texto_bloco: return pessoas
    # Participantes instrumentais podem vir depois dos compradores sem um
    # novo rótulo simples (por exemplo: "Compareceram como INTERVENIENTES
    # ANUENTES na qualidade de filhos:"). Eles não integram a aquisição.
    texto_bloco = re.split(
        MARCADOR_PAPEL_NAO_ADQUIRENTE,
        texto_bloco,
        maxsplit=1,
        flags=re.I | re.DOTALL,
    )[0].strip().rstrip(';, ')
    # Em traslados antigos, uma coproprietária pode aparecer sem documento
    # próprio entre a qualificação do vendedor anterior e a do marido:
    # ``... CPF. Vera Maria; filha de ... e seu marido Antônio, CPF ... e
    # Iraci, CPF ...``. O marido é apenas qualificado; a pessoa antes de
    # ``filha de`` é que integra a lista de transmitentes.
    texto_bloco = re.sub(
        r'(?:^|\.\s+)(?P<nome>[A-ZÀ-Ú][A-Za-zÀ-ú\s]{4,100})\s*;\s*'
        r'filh[oa]\s+de\b.*?\be\s+(?:seu|sua)\s+'
        r'(?:marido|mulher|c[oô]njuge)\s+[A-ZÀ-Ú].*?'
        r'(?=\s+e\s+(?!(?:domiciliad|resident|casad|portador|brasileir|'
        r'lavrador)\w*)[A-ZÀ-Ú][^;]{2,500}?\b'
        r'(?:CPF|CIC|CNPJ|CGC)\b)',
        lambda encontrado: f'; {encontrado.group("nome").strip()};',
        texto_bloco,
        flags=re.I | re.DOTALL,
    )
    texto_bloco = re.split(
        r';\s*neste\s+ato\s+(?:o\s+primeiro|a\s+primeira|representad[oa]|assistid[oa])\b',
        texto_bloco,
        maxsplit=1,
        flags=re.I,
    )[0]

    conjuge_casamento = re.search(
        r'\bcasad[oa]\s+sob\s+o\s+regime\b.*?\bcom\s+'
        r'([A-ZÁÀÂÃÉÈÊÍÌÎÓÒÔÕÚÙÛÇ][^,]+?)\s*,'
        r'.*?(?:CPF|CIC|CNPJ|CGC|MF)[^\d]*([\d\.\-\/]{9,20})',
        texto_bloco,
        re.I | re.DOTALL
    )

    # Escrituras antigas podem qualificar coletivamente uma lista de menores
    # e informar documento apenas para o pai/representante. Nesse caso os
    # nomes anteriores a "menores" são os adquirentes; o representante não é.
    texto_lista_menores = re.sub(
        r',\s*menor\s+(?:p.beres?|imp.beres?)\s*,',
        ', ',
        texto_bloco,
        flags=re.I,
    )
    lista_menores = re.match(
        r'^\s*(?P<nomes>[A-ZÀ-Ú][^;]{3,300}?)\s+menores?\s+'
        r'(?:púberes?|impúberes?)\b',
        texto_lista_menores,
        re.I | re.DOTALL,
    )
    partes_coletivas = []
    marcadores_menores = re.findall(
        r'\bmenores?\s+(?:p.beres?|imp.beres?)\b', texto_bloco, re.I,
    )
    if lista_menores and len(marcadores_menores) == 1:
        partes_coletivas = [
            nome.strip(' ,;')
            for nome in re.split(r'\s*,\s*|\s+e\s+', lista_menores.group("nomes"))
            if len(nome.strip(' ,;').split()) >= 2
        ]
    elif marcadores_menores:
        trecho_menores = re.split(
            r'\bbrasileir[oa]s?\b|\bresidentes?\b|\bportadores?\b|'
            r'\bneste\s+ato\b',
            texto_bloco,
            maxsplit=1,
            flags=re.I,
        )[0]
        trecho_menores = re.sub(
            r',?\s*menores?\s+(?:p.beres?|imp.beres?)\s*(?:,?\s*estudantes?)?\s*[,;]?',
            '; ',
            trecho_menores,
            flags=re.I,
        )
        partes_coletivas = [
            nome.strip(' ,;')
            for nome in re.split(r'\s*;\s*|\s*,\s*|\s+e\s+', trecho_menores)
            if len(nome.strip(' ,;').split()) >= 2
        ]

    # Rótulos intermediários de inventário não pertencem ao nome e não devem
    # impedir a separação de todos os itens numerados.
    texto_bloco = re.sub(
        r'\b(?:O\s+MEEIRO|A\s+MEEIRA|OS\s+HERDEIROS|AS\s+HERDEIRAS|'
        r'HERDEIROS|HERDEIRAS)\s*:\s*(?=(?:\d{1,3}|[IVX]+)\))',
        '',
        texto_bloco,
        flags=re.I,
    )

    # Em atos com casal, cada cônjuge pode ter nome e CPF próprios no mesmo bloco.
    # Se não separarmos aqui, a limpeza abaixo remove o segundo cônjuge inteiro.
    partes_numeradas = re.split(
        r'(?:^|\s+|;)\s*\(?(?:\d{1,3}|[IVX]+)\)\s*-?\s*|'
        r'(?:^|;|,\s*e\s*,?)\s*(?:e\s*,?\s*)?'
        r'(?:\d{1,3}|[IVX]+)-\s*',
        texto_bloco,
    )
    partes_numeradas = [p.strip() for p in partes_numeradas if p.strip()]

    if len(partes_coletivas) > 1:
        partes = partes_coletivas
    elif len(partes_numeradas) > 1:
        partes = partes_numeradas
    else:
        partes_sem_ponto_virgula = re.split(
            r';\s*(?:e\s*,?\s*)?(?=(?:(?:Dr|Dra|Doutor|Doutora)\.?\s+)?'
            r'[A-ZÁÀÂÃÉÈÊÍÌÎÓÒÔÕÚÙÛÇ]'
            r'[A-ZÁÀÂÃÉÈÊÍÌÎÓÒÔÕÚÙÛÇa-záàâãéèêíìîóòôõúùûç]+'
            r'(?:\s+(?:(?:da|de|do|das|dos|e)\s+)?'
            r'[A-ZÁÀÂÃÉÈÊÍÌÎÓÒÔÕÚÙÛÇ]'
            r'[A-ZÁÀÂÃÉÈÊÍÌÎÓÒÔÕÚÙÛÇa-záàâãéèêíìîóòôõúùûç]+){1,})',
            texto_bloco,
        )
        if len(partes_sem_ponto_virgula) > 1:
            partes = [p.strip() for p in partes_sem_ponto_virgula if p.strip()]
        else:
            partes_conjuges = re.split(
                r'\s*,?\s*e\s*,?\s+(?:(?:seu|sua)\s+'
                r'(?:c[oô]njuge|companheir[oa]|mulher|marido|espos[oa])|'
                r'(?:seu|sua)\s*/\s*m)\s+',
                texto_bloco,
                flags=re.I,
            )
            partes = [p.strip() for p in partes_conjuges if p.strip()]
            partes = [re.sub(r'\s+e\s+d[oa]\s+CPF', ' CPF', p, flags=re.I) for p in partes]
            padrao_pessoa_e = re.compile(
                r'\s+e\s+(?=[A-ZÀ-Ú][^,]+,\s*brasileir[oa])'
            )
            separador = next(
                (
                    encontrado for encontrado in padrao_pessoa_e.finditer(partes[0])
                    if not re.search(
                        r'filh[oa]\s+de\s+[^,;]{0,180}$',
                        partes[0][:encontrado.start()],
                        re.I,
                    )
                ),
                None,
            )
            if separador:
                partes = [
                    partes[0][:separador.start()].strip(),
                    partes[0][separador.end():].strip(),
                ]

    partes_expandidas = []
    for parte in partes:
        if not re.search(r'\b(?:CPF|CIC|CNPJ|CGC)\b', parte, re.I):
            trecho_nomes = re.split(
                r',\s*(?:j[áa]\s+qualificad[oa]s?\b|acima\s+qualificad[oa]s?\b)',
                parte,
                maxsplit=1,
                flags=re.I,
            )[0]
            nomes_qualificados = re.split(
                r'\s+e\s+(?=[A-ZÀ-Ú][A-Za-zÀ-ú]+(?:\s+[A-ZÀ-Ú][A-Za-zÀ-ú]+)+)',
                trecho_nomes,
            )
            if len(nomes_qualificados) > 1:
                partes_expandidas.extend(
                    item.strip(" ,;") for item in nomes_qualificados if item.strip(" ,;")
                )
                continue
        subdivisoes = re.split(
            r'(?<!\bDr)(?<!\bDra)(?<!\bSr)(?<!\bSra)\.\s+'
            r'(?=[A-ZÀ-Ú][^,;]{2,100},\s*brasileir[oa])',
            parte,
        )
        if len(re.findall(r'\b(?:CPF|CIC|CNPJ|CGC)\b', parte, re.I)) >= 2:
            expandidas = []
            for subdivisao in subdivisoes:
                padrao_nova_pessoa = re.compile(
                    r'\s+e\s+(?!(?:CPF|CIC|CNPJ|CGC|RG|CI)\b)'
                    r'(?=[A-ZÀ-Ú][^,;]{2,100},[^;]{0,420}?\b(?:CPF|CIC|CNPJ|CGC)\b)'
                )
                cortes = []
                for separador in padrao_nova_pessoa.finditer(subdivisao):
                    # "filha de José e Maria, CPF ..." qualifica uma única
                    # pessoa; Maria não é uma nova adquirente/proprietária.
                    if re.search(
                        r'filh[oa]\s+de\s+[^,;]{0,180}$',
                        subdivisao[:separador.start()],
                        re.I,
                    ):
                        continue
                    # A denominação do cartório integra a referência da
                    # certidão e nunca inicia uma nova pessoa qualificada.
                    if re.search(
                        r'\b(?:CART[ÓO]RIO\s+DE\s+)?REGISTRO\s+CIVIL\s*$',
                        subdivisao[:separador.start()],
                        re.I,
                    ):
                        continue
                    cortes.append(separador)
                if not cortes:
                    expandidas.append(subdivisao)
                else:
                    inicio = 0
                    for separador in cortes:
                        expandidas.append(subdivisao[inicio:separador.start()])
                        inicio = separador.end()
                    expandidas.append(subdivisao[inicio:])
            subdivisoes = expandidas
        menores = []
        for subdivisao in subdivisoes:
            menores.extend(re.split(
                r'\s+e\s+(?=[A-ZÀ-Ú][^,;]{2,100},\s*menor(?:\s+(?:púbere|impúbere))?\b)',
                subdivisao,
            ))
        partes_expandidas.extend(item.strip() for item in menores if item.strip())
    partes = partes_expandidas
    
    if not partes:
        sub_partes = re.split(r';\s*', texto_bloco)
        if len(sub_partes) > 1:
            partes = [p.strip() for p in sub_partes if len(p.strip()) > 10]
        else:
            partes = [texto_bloco]

    for parte in partes:
        parte = re.sub(r'^\s*e\s*,\s*', '', parte, flags=re.I)
        parte = re.sub(r'^\s*(?:meeir[oa]|vi[úu]v[oa])\s*,\s*', '', parte, flags=re.I)
        parte = re.split(r';\s*neste\s+ato\b', parte, maxsplit=1, flags=re.I)[0]
        
        # MEGA BRAIN: Agora aceita CNPJ, CGC e a barra "/" na leitura!
        cpf_match = re.search(
            r'(?:CPF|CIC|CNPJ|C\.?\s*G\.?\s*C\.?|MF)'
            r'[^\d]*([\d\.\-\/]{9,20})',
            parte,
            re.I,
        )
        # O documento do inventariante/representante não pertence ao espólio.
        if (
            cpf_match
            and re.match(
                r'^\s*(?:\d{1,3}\s*(?:\)|-)\s*)?ESP[ÓO]LIO\b',
                parte,
                re.I,
            )
            and re.search(
                r'\brepresentad[oa]\b',
                parte[:cpf_match.start()],
                re.I,
            )
        ):
            cpf_match = None
        percentual_match = re.search(
            r'(?:equivalente\s+a|(?:na|a)\s+propor[çc][ãa]o\s+de|'
            r'parte\s+correspondente\s+a)'
            r'\s*(\d+(?:,\d+)?)%',
            parte,
            re.I,
        )
        if not percentual_match and re.search(r'\bpertencente\s+(?:a|ao|à)\b', parte, re.I):
            percentual_match = re.match(r'\s*(\d+(?:,\d+)?)\s*%', parte)
        percentual = parse_percentual_declarado(percentual_match.group(1)) if percentual_match else None

        parte_nome = re.sub(
            r'^\s*\d+(?:[,.]\d+)?\s*%\s+'
            r'(?:(?:equivalente\s+a\s+[^,;]{1,100}?\s+)?'
            r'(?:do\s+im[óo]vel\s+)?)?'
            r'pertencente\s+(?:a|ao|à)\s+',
            '',
            parte,
            flags=re.I,
        )
        nome_match = re.match(r'^([^,]+)', parte_nome)
        nome = nome_match.group(1).strip() if nome_match else "DESCONHECIDO"
        nome = re.sub(r'^\(?\d+(?:\)\s*-?|-)\s*', '', nome)
        nome = re.sub(r'^(?:\+?\s*<[^>]+>\s*)+', '', nome)
        nome = re.sub(r'^\(?\d+(?:\)\s*-?|-)\s*', '', nome)
        nome = re.sub(r'^(?:Dr\.?|Dra\.?|Doutor(?:a)?)\s+', '', nome, flags=re.I)
        nome = re.sub(
            r'^\d+(?:[,.]\d+)?\s*%\s+equivalente\s+a\s+[^,;]{1,100}?'
            r'\bdo\s+im[óo]vel\s+pertencente\s+(?:a|ao|à)\s+',
            '',
            nome,
            flags=re.I,
        )
        nome = re.sub(
            r'^pessoa\s+jur[íi]dica\b.*?\bdenomina[çc][ãa]o\s+social\s+de\s+',
            '',
            nome,
            flags=re.I,
        )
        nome = re.sub(
            r'^d[oa]\s+dom[ií]nio\s+(?:[uú]til|direto)\s+sobre\s+o\s+terreno'
            r'(?:\s+descrito)?(?:\s+e\s+o\s+pr[eé]dio\s+residencial\s+nele\s+edificado)?'
            r'\s+(?:[oa]\s+)?',
            '',
            nome,
            flags=re.I,
        )
        cpf = cpf_match.group(1).strip().rstrip('.,;') if cpf_match else "CPF/CNPJ NÃO INFORMADO"

        # Limpeza visual (remove estado civil e termo "pessoa jurídica")
        nome = re.sub(r'\s+e\s+(?:seu\s+c[oô]njuge|sua\s+mulher|seu\s+marido|sua\s+esposa).*', '', nome, flags=re.I)
        nome = re.sub(
            r'^(?:(?:e\s+)?(?:(?:a|o|as|os)\s+)?(?:meeir[oa]|vi[úu]v[oa]|'
            r'cond[oô]min[oa]s?|'
            r'herdeir[oa]\s+e\s+cession[áa]ri[oa]|herdeir[oa]\s+(?:filh[oa]|net[oa])|'
            r'herdeir[oa]|cession[áa]ri[oa]|net[oa])\s*:?\s*)+',
            '', nome, flags=re.I,
        )
        nome = re.sub(r'\s*,?\s*casad[oa].*', '', nome, flags=re.I)
        nome = re.sub(r'\s*,?\s*pessoa jur[íi]dica.*', '', nome, flags=re.I)
        nome = re.sub(r'\s+', ' ', nome)
        nome = re.sub(r'(?:;\s*|\s+)e\s*$', '', nome, flags=re.I)
        nome = re.sub(r'^s\s*:\s*', '', nome, flags=re.I)
        nome = nome.strip(' ,.()')

        # Fragmentos de referência tabular, endereço ou fólio podem ficar
        # entre dois nomes quando o traslado histórico perdeu delimitadores.
        # Eles não representam pessoas e não podem entrar na cadeia dominial.
        nome_normalizado = limpar_nome(nome)
        if (
            re.match(r'^(?:NO\s+)?LIVRO\s+\d', nome_normalizado)
            or re.match(r'^\d[\d./-]*\s+E\s+V$', nome_normalizado)
            or re.match(
                r'^(?:SETOR|BAIRRO|JARDIM|LOTEAMENTO|RUA|AVENIDA|ALAMEDA|'
                r'TRAVESSA|RODOVIA)\b',
                nome_normalizado,
            )
        ):
            continue
        
        if re.match(r'^(?:CPF|CNPJ|CIC|RG)\b', nome, re.I):
            continue
        nome_sem_pontuacao = re.sub(r'[^A-ZÀ-Ú]', '', nome.upper())
        if (
            len(nome_sem_pontuacao) < 2
            or re.match(r'^N\s*[.º°O]*\s*\d', nome, re.I)
            or re.match(r'^[A-Z]{1,2}\s*;\s*(?:R|AV)\d', nome, re.I)
        ):
            continue
        pessoa = {"nome": nome, "cpf": cpf}
        if percentual is not None:
            pessoa["percentual"] = percentual
        pessoas.append(pessoa)

    if conjuge_casamento and len(pessoas) > 1:
        nome_conjuge = re.sub(r'\s+', ' ', conjuge_casamento.group(1)).strip(' ,.')
        cpf_conjuge = conjuge_casamento.group(2).strip().rstrip('.,;')
        indices_conjuge = [
            indice for indice, pessoa in enumerate(pessoas)
            if nomes_compativeis(pessoa["nome"], nome_conjuge)
        ]
        for indice in reversed(indices_conjuge):
            conjuge = pessoas[indice]
            if conjuge.get("percentual") is not None and indice > 0:
                pessoas[indice - 1]["percentual"] = conjuge["percentual"]
            del pessoas[indice]

    return pessoas


def enriquecer_documentos_adquirentes(adquirentes, texto):
    """Recupera documentos da qualificação anterior à cláusula dispositiva."""
    if not adquirentes:
        return adquirentes

    clausula = re.search(r'\bcoube\s+exclusivamente\b', texto, re.I)
    prefixo = texto[:clausula.start()] if clausula else texto
    qualificados = extrair_pessoas(prefixo[-5000:]) if clausula else []

    for adquirente in adquirentes:
        if re.sub(r'\D', '', adquirente.get("cpf", "")):
            continue
        nome = adquirente.get("nome", "").strip()
        if not nome:
            continue
        ocorrencias = list(re.finditer(re.escape(nome), prefixo, re.I))
        for ocorrencia in reversed(ocorrencias):
            trecho = prefixo[ocorrencia.end():ocorrencia.end() + 650]
            trecho = re.split(r';|\b\d{1,3}\s*\)\s*-?', trecho, maxsplit=1)[0]
            documento = re.search(
                r'\b(?:CPF|CIC|CNPJ|C\.?\s*G\.?\s*C\.?)(?:/MF)?'
                r'[^\d]{0,40}([\d.\-/]{9,20})',
                trecho,
                re.I,
            )
            if not documento:
                continue
            antes_documento = trecho[:documento.start()]
            if re.search(
                r'\b(?:representad[oa]s?|assistid[oa]s?|anuentes?)\b',
                antes_documento,
                re.I,
            ):
                continue
            adquirente["cpf"] = documento.group(1).rstrip(".,;")
            break
        if re.sub(r'\D', '', adquirente.get("cpf", "")):
            continue
        compativeis = [
            qualificado
            for qualificado in qualificados
            if (
                (
                    nomes_compativeis(
                        adquirente.get("nome", ""),
                        qualificado.get("nome", ""),
                    )
                    or SequenceMatcher(
                        None,
                        limpar_nome(adquirente.get("nome", "")),
                        limpar_nome(qualificado.get("nome", "")),
                    ).ratio() >= 0.88
                )
                and re.sub(r'\D', '', qualificado.get("cpf", ""))
            )
        ]
        if len(compativeis) == 1:
            adquirente["cpf"] = compativeis[0]["cpf"]

    sem_documento = [
        item for item in adquirentes
        if not re.sub(r'\D', '', item.get("cpf", ""))
    ]
    if sem_documento:
        trecho_dispositivo = texto[clausula.start():] if clausula else texto
        documentos_respectivos = re.search(
            r'\b(?:CPF|CIC)(?:/MF)?\s+n[.º°o]*s?[.:]?\s*'
            r'([\d.\-]{9,18})\s+e\s+([\d.\-]{9,18})'
            r'.{0,80}?\brespectivamente\b',
            trecho_dispositivo,
            re.I | re.DOTALL,
        )
        if documentos_respectivos and len(adquirentes) == 2:
            for adquirente, documento in zip(
                adquirentes,
                documentos_respectivos.groups(),
            ):
                adquirente["cpf"] = documento.rstrip(".,;")

    return adquirentes


def extrair_proprietario_inicial(texto_cabecalho):
    m = re.search(r'(?:(?:P?R[OÓ]PRIET)|PRORIET)[AÁ]RI[OA]S?\s*[:;]\s*(.*?)(?=\bORIGEM\b|\bT[IÍ]TULO AQUISITIVO\b|\bREGISTRO ANTERIOR\b|\bO referido [ée] verdade\b|\*NOTA\b|\bProtocolo\b|\Z)', texto_cabecalho, re.I | re.DOTALL)
    if m:
        bloco = m.group(1).strip()
        proprietarios = []

        # Em cabeçalhos plurais, cada item numerado representa um titular. O
        # cônjuge que aparece dentro do mesmo item apenas qualifica o titular,
        # salvo quando também recebe item próprio.
        marcadores = list(re.finditer(
            r'(?:^|;)\s*(?:e\s*,?\s*)?'
            r'(?:\d{1,3}\s*\)\s*-?|\d{1,3}\s+-)\s*',
            bloco,
            re.I,
        ))
        if len(marcadores) >= 2:
            for indice, marcador in enumerate(marcadores):
                fim = marcadores[indice + 1].start() if indice + 1 < len(marcadores) else len(bloco)
                parte = bloco[marcador.end():fim].strip(" ;")
                pessoas_item = extrair_pessoas(parte)
                if not pessoas_item:
                    continue
                titular = pessoas_item[0]
                if not re.sub(r'\D', '', titular.get("cpf", "")) and re.search(
                    r'\b(?:INSCRITOS|PORTADORES)\s+(?:NO|DO)\s+(?:CPF|CIC)\b',
                    parte,
                    re.I,
                ):
                    documento_compartilhado = re.search(
                        r'(?:CPF|CIC)(?:/MF)?[^\d]{0,30}([\d.\-/]{9,20})',
                        parte,
                        re.I,
                    )
                    if documento_compartilhado:
                        titular["cpf"] = documento_compartilhado.group(1).rstrip(".,;")
                percentual_parenteses = re.search(
                    r'\(\s*(\d+(?:[,.]\d+)?)\s*%\s*\)',
                    parte,
                    re.I,
                )
                if percentual_parenteses:
                    titular["percentual"] = parse_percentual_declarado(
                        percentual_parenteses.group(1)
                    )
                proprietarios.append(titular)

        # Matrículas antigas frequentemente separam coproprietários somente por
        # "(24,1202%). Nome seguinte", sem numeração nem ponto e vírgula.
        if not proprietarios:
            finais_percentuais = list(re.finditer(
                r'\(\s*(\d+(?:[,.]\d+)?)\s*%\s*\)\s*[.;]?',
                bloco,
                re.I,
            ))
            if len(finais_percentuais) >= 2:
                inicio = 0
                for final in finais_percentuais:
                    parte = bloco[inicio:final.end()].strip(" ;.")
                    inicio = final.end()
                    pessoas_item = extrair_pessoas(parte)
                    if not pessoas_item:
                        continue
                    titular = pessoas_item[0]
                    if not re.sub(r'\D', '', titular.get("cpf", "")) and re.search(
                        r'\b(?:INSCRITOS|PORTADORES)\s+(?:NO|DO)\s+(?:CPF|CIC)\b',
                        parte,
                        re.I,
                    ):
                        documento_compartilhado = re.search(
                            r'(?:CPF|CIC)(?:/MF)?[^\d]{0,30}([\d.\-/]{9,20})',
                            parte,
                            re.I,
                        )
                        if documento_compartilhado:
                            titular["cpf"] = documento_compartilhado.group(1).rstrip(".,;")
                    titular["percentual"] = parse_percentual_declarado(final.group(1))
                    proprietarios.append(titular)

        if not proprietarios:
            proprietarios = extrair_pessoas(bloco)
        percentuais_declarados = re.findall(
            r'\bque\s+(?:ainda\s+)?possui\s+'
            r'(\d+(?:[,.]\d+)?)\s*%\s+do\s+im[óo]vel',
            bloco,
            re.I,
        )
        if len(percentuais_declarados) == len(proprietarios):
            for proprietario, percentual in zip(
                proprietarios, percentuais_declarados
            ):
                proprietario["percentual"] = parse_percentual_declarado(
                    percentual
                )
        cabecalho_limpo = limpar_nome(texto_cabecalho)
        bloco_limpo = limpar_nome(m.group(1))
        proprietario_singular = (
            re.search(r'P?ROPRIETARI[OA]\s*:', cabecalho_limpo)
            and not re.search(r'P?ROPRIETARI[OA]S\s*:', cabecalho_limpo)
        )
        conjuge_qualificacao = (
            "CASAD" in bloco_limpo
            and "SOB O REGIME" in bloco_limpo
            and " COM " in bloco_limpo
        )
        if (
            proprietario_singular
            and conjuge_qualificacao
            and proprietarios
            and len(marcadores) < 2
        ):
            return proprietarios[:1]
        return proprietarios
    return []

def extrair_retificacoes_cpf(texto):
    if not re.search(r'RETIFICA[ÇC][ÃA]O', texto, re.I):
        return []

    pessoas = []
    padroes = (
        re.compile(
            r'(?i:\b(?:a|o)\s+(?:co-?)?propriet[áa]ri[oa]\s+)'
            r'(?P<nome>[A-ZÀ-Ú][A-Za-zÀ-ú\s\'.-]{2,120}?)\s*,?\s*'
            r'(?is:(?:permanece|est[áa]|[ée])\b.{0,320}?\binscrit[oa]\s+no\s+'
            r'CPF(?:/MF)?\s+sob\s+o\s+n[.º°o]*\s*)'
            r'(?P<cpf>[\d.\-]{9,18})'
        ),
        re.compile(
            r'(?:^|[;:])\s*\d+(?:\.\d+)?\)-\s*'
            r'(?P<nome>[A-ZÀ-Ú][A-Za-zÀ-ú\s\'.-]{2,120}?)\s*,?\s*'
            r'(?is:(?:permanece|est[áa]|[ée])\b.{0,320}?\binscrit[oa]\s+no\s+'
            r'CPF(?:/MF)?\s+sob\s+o\s+n[.º°o]*\s*)'
            r'(?P<cpf>[\d.\-]{9,18})'
        ),
    )
    vistos = set()
    for padrao in padroes:
        for encontrado in padrao.finditer(texto):
            nome = re.sub(
                r'^e\s+(?:seu|sua)\s+c[oô]njuge\s+',
                '',
                encontrado.group("nome"),
                flags=re.I,
            ).strip(' ,.;:')
            cpf = encontrado.group("cpf").strip().rstrip(".,;")
            chave = (limpar_nome(nome), re.sub(r'\D', '', cpf))
            if chave in vistos:
                continue
            vistos.add(chave)
            pessoas.append({"nome": nome, "cpf": cpf})
    return pessoas


def extrair_alteracao_nome(texto):
    if not re.search(
        r'ALTERA[ÇC][ÃA]O\s+(?:DO\s+)?NOME|ALTERA[ÇC][ÃA]O\s+DE\s+ESTADO\s+CIVIL|'
        r'MUDAN[ÇC]A\s+DE\s+DENOMINA[ÇC][ÃA]O\s+SOCIAL',
        texto,
        re.I,
    ):
        return ""
    denominacao = re.search(
        r'\bpassou\s+a\s+denominar-se\s+([^,;.]+)',
        texto,
        re.I | re.DOTALL,
    )
    if denominacao:
        return denominacao.group(1).strip()
    encontrado = re.search(
        r'(?:altera[çc][ãa]o\s+d[oa]\s+nome|nome\s+d[oa]\s+propriet[áa]ri[oa])'
        r'.{0,180}?\bpara\s+([^,;.]+)',
        texto,
        re.I | re.DOTALL,
    )
    return encontrado.group(1).strip() if encontrado else ""


def extrair_retorno_status_quo_ante(texto):
    if not re.search(r'\bSTATUS\s+QUO\s+ANTE\b', texto, re.I):
        return []
    retorno = re.search(
        r'\bretorna\s+ao\s+STATUS\s+QUO\s+ANTE\b.*?'
        r'\bpropriedade\s+d[ao]\s+(?:pessoa\s+jur[íi]dica\s+de\s+direito\s+privado\s+)?'
        r'([^,;.]+).*?\b(?:CNPJ|CGC)(?:/MF)?\s+sob\s+o\s+n[.º°o]*\s*'
        r'([\d.\-/]{9,20})',
        texto,
        re.I | re.DOTALL,
    )
    if not retorno:
        return []
    return [{
        "nome": retorno.group(1).strip(),
        "cpf": retorno.group(2).strip().rstrip(".,;"),
    }]


def extrair_credor_consolidacao(texto):
    if not re.search(r'CONSOLIDA[ÇC][ÃA]O\s+DA\s+PROPRIEDADE', texto, re.I):
        return []

    # credor[ao]? com o sufixo opcional: antes exigia "credora"/"credoro" e
    # por isso a forma masculina "em favor do credor fiduciário Banco X" --
    # a redação mais comum -- nunca casava. A consolidação era ignorada em
    # silêncio e o devedor continuava figurando como proprietário.
    m = re.search(
        r'em\s+favor\s+d[oa]\s+credor[ao]?\s+fiduci[áa]ri[oa]\s+([^,]+),'
        r'.*?(?:CNPJ|CPF)(?:/MF)?\s+sob\s+o\s+n[.º°o]*\s*([\d.\-/]{9,20})',
        texto,
        re.I | re.DOTALL
    )
    if not m:
        return []
    # rstrip('.'): a classe [\d.\-/] do documento engole o ponto final da
    # frase quando o número encerra o período ("...sob o n.º 00.000.000/0001-00.
    # DOU FÉ."), gerando um CNPJ/CPF malformado no resultado.
    return [{"nome": m.group(1).strip(), "cpf": m.group(2).strip().rstrip('.')}]

def contem_indicacao_titularidade(texto):
    texto_limpo = limpar_nome(texto)
    return "INDICA" in texto_limpo and "TITULARIDADE" in texto_limpo

def formatar_percentual_indicado(valor):
    texto = f"{valor:.5f}".rstrip('0').rstrip('.').replace('.', ',')
    return f"{texto}%"

def extrair_indicacao_titularidade(texto):
    if not contem_indicacao_titularidade(texto):
        return []

    # A API da Tri7 frequentemente devolve as tabelas históricas em uma única
    # linha ("ATOCO-PROPRIETÁRIO...R.24Nome11,85%..."). Nessas situações a
    # leitura por linhas não consegue separar as colunas; os códigos dos atos e
    # o percentual funcionam como delimitadores estáveis.
    inicio_tabela = limpar_nome(texto).find("ATOCO-PROPRIETARIO")
    if inicio_tabela >= 0:
        tabela = texto[inicio_tabela:]
        com_decimal = []
        padrao_decimal = re.compile(
            r'(?P<atos>(?:R|AV)[.\-]?\d+'
            r'(?:(?:\s*(?:E|,)\s*|\s+)(?:(?:R|AV)[.\-]?)?\d+)*)\s*'
            r'(?P<nome>[A-ZÀ-Ý][A-Za-zÀ-ú\s\'.-]{2,180}?)\s*'
            r'(?P<decimal>(?:0[,.]\d{4}|1(?:[,.]0{4})?))\s*'
            r'(?P<percentual>\d{1,3}(?:[,.]\d{2})?)\s*%?\s*'
            r'(?=\d+(?:[,.]\d+)?\s*ha)',
            re.I | re.DOTALL,
        )
        for encontrado in padrao_decimal.finditer(tabela):
            nome = re.sub(r'\s+', ' ', encontrado.group("nome")).strip(" \t|;-:")
            nome = re.sub(r'^(?:Matr(?:[ií]cula)?\.?\s*)+', '', nome, flags=re.I)
            percentual = float(encontrado.group("percentual").replace(',', '.'))
            if nome and 0 < percentual <= 100:
                com_decimal.append({
                    "nome": nome,
                    "cpf": "CPF/CNPJ NÃO INFORMADO",
                    "percentual": percentual,
                    "proporcao_texto": formatar_percentual_indicado(percentual),
                })
        if len(com_decimal) >= 2 and abs(
            sum(item["percentual"] for item in com_decimal) - 100.0
        ) <= 0.2:
            return com_decimal

        compactos = []
        padrao_compacto = re.compile(
            r'(?P<atos>(?:R|AV)[.\-]?\d+'
            r'(?:(?:\s*(?:E|,)\s*|\s+)(?:(?:R|AV)[.\-]?)?\d+)*)\s*'
            r'(?P<nome>.{2,700}?)\s*'
            r'(?P<percentual>\d{1,3}(?:[,.]\d{1,5})?)\s*%',
            re.I | re.DOTALL,
        )
        for encontrado in padrao_compacto.finditer(tabela):
            nome = encontrado.group("nome")
            nome = re.sub(r'^(?:(?:R|AV)[.\-]?\d+\s*)+', '', nome, flags=re.I)
            nome = re.split(
                r'\s+(?:à\s+época\s+da\s+aquisição\s+)?casad[oa]\b|'
                r'\s*\*\s*Forma\s+de\s+Aquisi[çc][ãa]o\s*:',
                nome,
                maxsplit=1,
                flags=re.I,
            )[0]
            nome = re.sub(r'^.*?\bCO-?PROPRIET[ÁA]RIO\b', '', nome, flags=re.I | re.DOTALL)
            nome = re.sub(r'\b(?:EQUIV(?:AL[ÊE]NCIA)?|DECIMAL|PERCENTUAL).*$', '', nome, flags=re.I)
            nome = re.sub(r'^(?:Matr(?:[ií]cula)?\.?\s*)+', '', nome, flags=re.I)
            nome = nome.strip(" \t|;-:")
            if not nome or limpar_nome(nome).startswith("TOTAL"):
                continue
            percentual = float(encontrado.group("percentual").replace(',', '.'))
            existente = next(
                (item for item in compactos if nomes_compativeis(item["nome"], nome)),
                None,
            )
            if existente:
                existente["percentual"] += percentual
                existente["proporcao_texto"] = formatar_percentual_indicado(existente["percentual"])
            else:
                compactos.append({
                    "nome": nome,
                    "cpf": "CPF/CNPJ NÃO INFORMADO",
                    "percentual": percentual,
                    "proporcao_texto": formatar_percentual_indicado(percentual),
                })
        if len(compactos) >= 2:
            return compactos

    # Matrículas recentes podem trazer a indicação como tabela HTML achatada,
    # sem espaços entre nome, percentual e área, e sem repetir o código do ato:
    # "Osmar Tagliari25%11,6642haSuely Tagliari25%...".
    cabecalho_area = re.search(
        r'CORRESPOND[ÊE]NCIA\s+NA\s+[ÁA]REA\s+DO\s+IM[ÓO]VEL\s*'
        r'\(EM\s+HECTARES\)',
        texto,
        re.I,
    )
    if cabecalho_area:
        tabela_compacta = texto[cabecalho_area.end():]
        indicados_compactos = []
        for encontrado in re.finditer(
            r'(?P<nome>[A-ZÀ-Ý][^\d%]{2,140}?)\s*'
            r'(?P<percentual>\d{1,3}(?:[,.]\d+)?)\s*%\s*'
            r'(?P<area>\d+(?:[,.]\d+)?)\s*ha',
            tabela_compacta,
        ):
            nome = re.sub(r'\s+', ' ', encontrado.group('nome')).strip(' .;-')
            nome = re.sub(r'^(?:Matr(?:[ií]cula)?\.?\s*)+', '', nome, flags=re.I)
            nome_limpo = limpar_nome(nome)
            if not nome or 'PROPRIETARIO' in nome_limpo or nome_limpo == 'TOTAL':
                continue
            percentual = float(encontrado.group('percentual').replace(',', '.'))
            indicados_compactos.append({
                'nome': nome,
                'cpf': 'CPF/CNPJ NÃO INFORMADO',
                'percentual': percentual,
                'proporcao_texto': formatar_percentual_indicado(percentual),
            })
        if len(indicados_compactos) >= 2:
            return indicados_compactos

    proprietarios = []
    buffer = []

    for linha in texto.splitlines():
        linha = linha.strip()
        if not linha:
            continue

        linha_limpa = limpar_nome(linha)
        if (
            linha_limpa in {"ATO", "CO-PROPRIETARIO", "PERCENTUAL", "(%)"}
            or "INDICA" in linha_limpa
            or "TITULARIDADE" in linha_limpa
            or linha_limpa.startswith("PROCEDE-SE")
            or linha_limpa.startswith("A FIM DE")
        ):
            continue
        if linha_limpa.startswith("TOTAL") or linha_limpa.startswith("DOU FE"):
            buffer = []
            continue

        buffer.append(linha)
        percentual = re.search(r'(\d+(?:[,.]\d+)?)\s*%', linha)
        if not percentual:
            continue

        linha_completa = " ".join(buffer)
        buffer = []
        proporcao = float(percentual.group(1).replace(',', '.'))
        antes_percentual = linha_completa[:linha_completa.rfind(percentual.group(0))].strip(" \t-")
        colunas = [
            parte.strip(" \t-")
            for parte in re.split(r'\t+|\s{2,}', antes_percentual)
            if parte.strip(" \t-")
        ]
        nome = colunas[-1] if colunas else antes_percentual
        nome = re.sub(
            r'^(?:(?:e\s*)?(?:Matr(?:[ií]cula)?\.?|R\.?\s*\d+|AV\.?\s*\d+)'
            r'[\s,.;/-]*)+',
            '',
            nome,
            flags=re.I,
        ).strip(" \t-")
        nome = re.sub(r'\s+', ' ', nome)

        if not nome or limpar_nome(nome).startswith("TOTAL"):
            continue

        proprietarios.append({
            "nome": nome,
            "cpf": "CPF/CNPJ NÃO INFORMADO",
            "percentual": proporcao,
            "proporcao_texto": formatar_percentual_indicado(proporcao),
        })

    return proprietarios

def nomes_compativeis(nome_a, nome_b):
    nome_a = limpar_nome(nome_a)
    nome_b = limpar_nome(nome_b)
    if not nome_a or not nome_b:
        return False
    if nome_a == nome_b:
        return True
    sufixos_familiares = {"FILHO", "FILHA", "NETO", "NETA", "SOBRINHO", "SOBRINHA", "JUNIOR", "JÚNIOR"}
    sem_particulas_a = re.sub(r'\b(?:DA|DE|DO|DAS|DOS|E)\b', '', nome_a)
    sem_particulas_b = re.sub(r'\b(?:DA|DE|DO|DAS|DOS|E)\b', '', nome_b)
    sem_particulas_a = re.sub(r'\s+', ' ', sem_particulas_a).strip()
    sem_particulas_b = re.sub(r'\s+', ' ', sem_particulas_b).strip()
    if sem_particulas_a == sem_particulas_b:
        return True
    # Grafias históricas e OCR alternam com frequência S/Z ("Três"/"Trez").
    # A equivalência é aplicada somente à expressão completa, preservando a
    # proteção abaixo contra homônimos com sufixos familiares distintos.
    fonetico_a = sem_particulas_a.replace("Z", "S")
    fonetico_b = sem_particulas_b.replace("Z", "S")
    if fonetico_a == fonetico_b:
        return True
    # Variação histórica de grafia e OCR no fim de nomes próprios:
    # Adeni/Adeny, Darci/Darcy. Só aceitamos quando todo o restante do nome é
    # idêntico, evitando aproximar pessoas distintas por mera semelhança.
    if re.sub(r'Y\b', 'I', fonetico_a) == re.sub(r'Y\b', 'I', fonetico_b):
        return True
    if len(nome_a) <= 5 or len(nome_b) <= 5:
        return False
    if nome_a in nome_b:
        complemento = nome_b.split(nome_a, 1)[1].strip().split()
        return not complemento or complemento[0] not in sufixos_familiares
    if nome_b in nome_a:
        complemento = nome_a.split(nome_b, 1)[1].strip().split()
        return not complemento or complemento[0] not in sufixos_familiares

    tokens_a = [item for item in sem_particulas_a.split() if item]
    tokens_b = [item for item in sem_particulas_b.split() if item]
    curto, longo = (tokens_a, tokens_b) if len(tokens_a) <= len(tokens_b) else (tokens_b, tokens_a)
    if len(curto) < 2 or SequenceMatcher(None, curto[0], longo[0]).ratio() < 0.85:
        return False
    posicao = 0
    usados = []
    for token in curto:
        encontrado = None
        for indice in range(posicao, len(longo)):
            if SequenceMatcher(None, token, longo[indice]).ratio() >= 0.8:
                encontrado = indice
                break
        if encontrado is None:
            return False
        usados.append(encontrado)
        posicao = encontrado + 1
    adicionais = [token for indice, token in enumerate(longo) if indice not in usados]
    if adicionais and all(token in sufixos_familiares for token in adicionais):
        return False
    return True

def chave_para_incluir(pessoa, estado):
    chave = padronizar_chave(pessoa["cpf"], pessoa["nome"])
    if chave in estado and not nomes_compativeis(estado[chave]["nome"], pessoa["nome"]):
        return limpar_nome(pessoa["nome"])
    documento = re.sub(r'\D', '', pessoa.get("cpf", ""))
    for chave_estado, dados in estado.items():
        if not nomes_compativeis(dados["nome"], pessoa["nome"]):
            continue
        if limpar_nome(dados["nome"]) == limpar_nome(pessoa["nome"]):
            return chave_estado
        documento_estado = re.sub(r'\D', '', dados.get("cpf_original", ""))
        if documento and documento_estado and documento != documento_estado:
            repeticoes_documento_estado = sum(
                re.sub(r'\D', '', item.get("cpf_original", "")) == documento_estado
                for item in estado.values()
            )
            if repeticoes_documento_estado <= 1:
                continue
        return chave_estado
    return chave


def _distribuicao_percentual_por_grupos(texto, adquirentes):
    """Lê percentuais coletivos ao final de escrituras históricas."""
    trecho = re.search(
        r'(?:seguinte|na)\s+propor[çc][ãa]o\s*:\s*(.*?)'
        r'(?=\bO\s+referido\b|\bDOU\s+F[ÉE]\b|\Z)',
        texto,
        re.I | re.DOTALL,
    )
    if not trecho:
        return []

    distribuicao = []
    vistos = set()
    for grupo in re.finditer(
        r'(?:^|;)\s*(?:e\s+)?(?:a|ao|aos|à|às)\s+(.*?)\s*,?\s*'
        r'(?:parte\s+correspondente\s+a|na\s+parte\s+de|com)\s*'
        r'(\d+(?:[,.]\d+)?)\s*%',
        trecho.group(1),
        re.I | re.DOTALL,
    ):
        nomes_grupo = re.sub(r'\s+', ' ', limpar_nome(grupo.group(1))).strip()
        integrantes = [
            (indice, pessoa)
            for indice, pessoa in enumerate(adquirentes)
            if re.sub(r'\s+', ' ', limpar_nome(pessoa["nome"])).strip() in nomes_grupo
        ]
        if not integrantes:
            return []
        percentual_grupo = float(grupo.group(2).replace(',', '.'))
        percentual_individual = percentual_grupo / len(integrantes)
        for indice, pessoa in integrantes:
            if indice in vistos:
                return []
            vistos.add(indice)
            distribuicao.append((pessoa, percentual_individual))

    if len(vistos) != len(adquirentes):
        return []
    if abs(sum(percentual for _, percentual in distribuicao) - 100.0) > 0.2:
        return []
    return distribuicao


def _distribuicao_percentual_por_areas(texto, adquirentes):
    """Lê a distribuição individual declarada ao final do próprio título."""
    trecho = re.search(
        r'adquirid[oa]\s+da\s+seguinte\s+maneira\s*:\s*(.*?)'
        r'(?=\bO\s+referido\b|\bDOU\s+F[ÉE]\b|\Z)',
        texto,
        re.I | re.DOTALL,
    )
    if not trecho or len(adquirentes) < 2:
        return []

    texto_distribuicao = trecho.group(1)
    texto_busca = limpar_nome(texto_distribuicao)
    percentuais = []
    for indice, adquirente in enumerate(adquirentes):
        nome = re.escape(limpar_nome(adquirente['nome']))
        inicio = re.search(nome, texto_busca)
        if not inicio:
            percentuais = []
            break
        proximos = []
        for outro in adquirentes[indice + 1:]:
            encontrado = re.search(
                re.escape(limpar_nome(outro['nome'])),
                texto_busca[inicio.end():],
            )
            if encontrado:
                proximos.append(encontrado.start())
        fim = inicio.end() + min(proximos) if proximos else len(texto_distribuicao)
        bloco = texto_distribuicao[inicio.end():fim]
        percentual = re.search(r'(\d+(?:[.,]\d+)?)\s*%', bloco)
        if not percentual:
            percentuais = []
            break
        percentuais.append(
            float(percentual.group(1).replace('.', '').replace(',', '.'))
        )
    if (
        len(percentuais) == len(adquirentes)
        and abs(sum(percentuais) - 100.0) <= 0.2
    ):
        return list(zip(adquirentes, percentuais))

    unidades = {
        'ALQUEIRE': r'alqueires?',
        'HECTARE': r'hectares?',
        'METRO_QUADRADO': r'(?:m[²2]|metros?\s+quadrados?)',
    }
    for padrao_unidade in unidades.values():
        valores = []
        for indice, adquirente in enumerate(adquirentes):
            nome = re.escape(limpar_nome(adquirente['nome']))
            inicio = re.search(nome, texto_busca)
            if not inicio:
                valores = []
                break
            proximos = []
            for outro in adquirentes[indice + 1:]:
                encontrado = re.search(
                    re.escape(limpar_nome(outro['nome'])),
                    texto_busca[inicio.end():],
                )
                if encontrado:
                    proximos.append(encontrado.start())
            fim = inicio.end() + min(proximos) if proximos else len(texto_distribuicao)
            bloco = texto_distribuicao[inicio.end():fim]
            medida = re.search(rf'(\d+(?:[.,]\d+)?)\s*{padrao_unidade}\b', bloco, re.I)
            if not medida:
                valores = []
                break
            valores.append(float(medida.group(1).replace('.', '').replace(',', '.')))
        total = sum(valores)
        if len(valores) == len(adquirentes) and total > 0:
            return [
                (adquirente, valor / total * 100.0)
                for adquirente, valor in zip(adquirentes, valores)
            ]
    return []


def _nome_mencionado_no_grupo(nome, grupo):
    nome_normalizado = limpar_nome(nome)
    grupo_normalizado = limpar_nome(grupo)
    if nome_normalizado in grupo_normalizado:
        return True
    tokens = [token for token in nome_normalizado.split() if token not in {'DA', 'DE', 'DO', 'DAS', 'DOS', 'E'}]
    if len(tokens) < 2:
        return False
    tokens_grupo = grupo_normalizado.split()
    primeiro_compativel = any(
        SequenceMatcher(None, tokens[0], token).ratio() >= 0.78
        for token in tokens_grupo
    )
    return primeiro_compativel and all(token in tokens_grupo for token in tokens[1:])


def _percentuais_por_valores_em_trecho(texto, pessoas, marcador):
    """Distribui quinhões monetários explicitados depois de "sendo/vendido"."""
    inicio = re.search(marcador, texto, re.I)
    avaliacao = re.search(
        r'na\s+(?:avalia\S*|qualifica\S*)\s+de\s*(?:[A-Z]{1,3}\$?\s*)?([\d.,]+)',
        texto,
        re.I,
    )
    if not inicio or not avaliacao:
        return []
    total = parse_valor_monetario(avaliacao.group(1))
    if not total:
        return []

    trecho = re.split(
        r'\bO\s+referido\b|\bDOU\s+F[ÉE]\b',
        texto[inicio.end():],
        maxsplit=1,
        flags=re.I,
    )[0]
    resultados = []
    usados = set()
    cursor = 0
    for encontrado in re.finditer(
        r'(?:parte|porte)\s+ideal\s+de\s*(?:[A-Z]{1,3}\$?\s*)?([\d.,]+)',
        trecho,
        re.I,
    ):
        grupo = trecho[cursor:encontrado.start()]
        cursor = encontrado.end()
        correspondentes = [
            (indice, pessoa)
            for indice, pessoa in enumerate(pessoas)
            if indice not in usados and _nome_mencionado_no_grupo(pessoa['nome'], grupo)
        ]
        if not correspondentes:
            continue
        valor = parse_valor_monetario(encontrado.group(1))
        if valor is None or valor <= 0 or valor > total:
            continue
        percentual_individual = valor / total * 100.0 / len(correspondentes)
        for indice, pessoa in correspondentes:
            usados.add(indice)
            resultados.append((pessoa, percentual_individual))
    return resultados


def _aplicar_desquite(ato, estado):
    normalizado = limpar_nome(ato)
    if (
        not any(termo in normalizado for termo in ('DESQUITE', 'DIVORCIO'))
        or 'PASSARA A PERTENCER AOS REQUERENTES' not in normalizado
    ):
        return False
    partes = re.search(
        r'autos\s+de\s+(?:partilha\s+amig[áa]vel|div[óo]rcio\s+direto|'
        r'conver(?:s|[çc])[ãa]o\s+de\s+separa[çc][ãa]o\s+judicial.*?em\s+div[óo]rcio)'
        r'.*?\bde\s+'
        r'([^,;]+?)\s+e\s+([^,;]+?)[,;]\s+'
        r'(?:do\s+Cart[óo]rio|(?:pela\s+)?Escrivania)',
        ato,
        re.I | re.DOTALL,
    )
    if not partes:
        return False
    nomes = [partes.group(1).strip(), partes.group(2).strip()]
    chave_existente = next(
        (
            chave for chave, dados in estado.items()
            if any(nomes_compativeis(dados['nome'], nome) for nome in nomes)
        ),
        None,
    )
    if not chave_existente:
        return False
    proporcao = estado[chave_existente]['proporcao']
    documento = estado[chave_existente].get('cpf_original', 'CPF/CNPJ NÃO INFORMADO')
    del estado[chave_existente]
    for nome in nomes:
        pessoa = {'nome': nome, 'cpf': documento if nomes_compativeis(nome, partes.group(1)) else 'CPF/CNPJ NÃO INFORMADO'}
        chave = chave_para_incluir(pessoa, estado)
        estado[chave] = {
            'nome': nome,
            'cpf_original': pessoa['cpf'],
            'proporcao': proporcao / len(nomes),
        }
    return True


def _assinatura_partilha(texto):
    normalizado = limpar_nome(texto)
    if not (
        any(termo in normalizado for termo in (
            "FORMAL DE PARTILHA", "FORMAL DE PARTICULA", "INVENTARIO E PARTILHA",
            "INVENTARIO/PARTILHA", "ARROLAMENTO E PARTILHA", "ARROLAMENTO DOS BENS",
            "ARROLAMENTO COMUM",
        ))
        or ("INVENTARIO" in normalizado and "BENS DEIXADOS" in normalizado and "COUBE" in normalizado)
    ):
        return None
    instrumento = re.search(
        r"\bL[º°O]\s*([\d.]+[,;.\s]+FLS?[.\s]*[\d./V]+)",
        normalizado[:1400],
    )
    if instrumento:
        return "INSTRUMENTO:" + instrumento.group(1)
    autor_heranca = re.search(
        r"BENS\s+(?:DEIXADOS\s+POR(?:\s+FALECIMENTOS?)?(?:\s+DE|\s+DO|\s+DA)?|DE)\s+"
        r"([^,;.]{3,140}?)(?=\s+LAVRADA\b|\s+JULGAD[OA]\b|\s+PEL[OA]\s+ESCRIVANIA\b|[,;.])",
        normalizado[:1400],
    )
    if autor_heranca:
        return "AUTOR DA HERANCA:" + autor_heranca.group(1).strip()
    espolio_transmitente = re.search(
        r"TRANSMITENTE\s*:\s*(?:O\s+)?ESPOLIO\s+DE\s+"
        r"([^,;.]{3,140}?)(?=\s+CPF\b|\s+ADQUIRENTE\b|[,;.])",
        normalizado[:1400],
    )
    if espolio_transmitente:
        return "ESPOLIO TRANSMITENTE:" + espolio_transmitente.group(1).strip()
    padroes = (
        r"FORMAL DE PARTILHA DE\s+(\d{1,2}\s+DE\s+[A-Z]+\s+DE\s+[\d.]{4,5})",
        r"ESCRITURA PUBLICA DE INVENTARIO E PARTILHA.*?LAVRADA EM\s+"
        r"(\d{1,2}\s+DE\s+[A-Z]+\s+DE\s+[\d.]{4,5})",
        r"PROTOCOLO\s+N?[.\sº°O]*([\d.]+)",
    )
    for padrao in padroes:
        encontrado = re.search(padrao, normalizado[:900], re.DOTALL)
        if encontrado:
            return encontrado.group(1)
    return None


def _assinaturas_partilha_compativeis(assinatura_a, assinatura_b):
    if not assinatura_a or not assinatura_b:
        return False
    if assinatura_a == assinatura_b:
        return True
    prefixo = 'AUTOR DA HERANCA:'
    if assinatura_a.startswith(prefixo) and assinatura_b.startswith(prefixo):
        autor_a = assinatura_a[len(prefixo):].strip()
        autor_b = assinatura_b[len(prefixo):].strip()
        return (
            nomes_compativeis(autor_a, autor_b)
            or SequenceMatcher(None, autor_a, autor_b).ratio() >= 0.84
        )
    return False


def _grupos_partilha_integrais(atos):
    grupos = {}
    indice = 0
    while indice < len(atos):
        assinatura = _assinatura_partilha(atos[indice].descricao)
        if not assinatura:
            indice += 1
            continue
        fim = indice
        itens = []
        descricoes = []
        while fim < len(atos):
            assinatura_atual = _assinatura_partilha(atos[fim].descricao)
            compativel = _assinaturas_partilha_compativeis(assinatura_atual, assinatura)
            if not compativel and fim + 1 < len(atos):
                assinatura_seguinte = _assinatura_partilha(atos[fim + 1].descricao)
                compativel = (
                    _assinaturas_partilha_compativeis(assinatura_seguinte, assinatura)
                    and any(
                        termo in limpar_nome(atos[fim].descricao)
                        for termo in ('PARTILHA', 'INVENTARIO', 'ARROLAMENTO', 'BENS DEIXADOS')
                    )
                )
            if not compativel:
                break
            adquirentes = extrair_pessoas(extrair_bloco(atos[fim].descricao, "ADQUIRENTE"))
            if not adquirentes:
                break
            itens.append((adquirentes, parse_percent(atos[fim].descricao)))
            descricoes.append(atos[fim].descricao)
            fim += 1
        total = sum(percentual for _, percentual in itens)
        valores_partes = []
        avaliacoes = []
        for descricao in descricoes:
            parte = re.search(
                r'(?:parte|porte)\s+(?:ideal|inicial)\s+de\s*'
                r'(?:[A-Z]{1,3}\$?\s*)?([\d.,]+)',
                descricao,
                re.I,
            )
            avaliacao = re.search(
                r'na\s+(?:avalia\S*|qualifica\S*)\s+de\s*'
                r'(?:[A-Z]{1,3}\$?\s*)?([\d.,]+)',
                descricao,
                re.I,
            )
            valores_partes.append(parse_valor_monetario(parte.group(1)) if parte else None)
            if avaliacao:
                valor_avaliacao = parse_valor_monetario(avaliacao.group(1))
                if valor_avaliacao:
                    avaliacoes.append(valor_avaliacao)
        if all(valor is not None for valor in valores_partes) and avaliacoes:
            avaliacao_referencia = max(set(avaliacoes), key=lambda valor: sum(abs(valor - item) <= max(.01, valor * .001) for item in avaliacoes))
            total_monetario = sum(valores_partes) / avaliacao_referencia * 100.0
            if abs(total_monetario - 100.0) <= 1.0:
                soma_partes = sum(valores_partes)
                itens = [
                    (adquirentes, valor / soma_partes * 100.0)
                    for (adquirentes, _), valor in zip(itens, valores_partes)
                ]
                total = 100.0
        quotas_declaradas = [
            parse_percentual_declarado(valor)
            for descricao in descricoes
            for valor in re.findall(
                r'\bquota\s*\(\s*(\d+(?:[,.]\d+)?)\s*%\s*\)',
                descricao,
                re.I,
            )
        ]
        quotas_compativeis = [
            quota for quota in quotas_declaradas
            if all(abs(quota - outra) <= 0.01 for outra in quotas_declaradas)
        ]
        referencias_integrais = (
            (100.0, *quotas_compativeis)
            if assinatura.startswith('ESPOLIO TRANSMITENTE:')
            else (100.0, 50.0, 25.0, 12.5, 6.25)
        )
        total_completo = next(
            (referencia for referencia in referencias_integrais
             if abs(total - referencia) <= 0.2),
            None,
        )
        if len(itens) >= 2 and total_completo is not None:
            if abs(total - 100.0) > 0.2:
                itens = [
                    (adquirentes, percentual / total * 100.0)
                    for adquirentes, percentual in itens
                ]
            grupos[indice] = (fim, itens, descricoes)
            indice = fim
        else:
            indice += 1
    return grupos

def encontrar_chave_no_estado(pessoa, estado):
    chave_pessoa = padronizar_chave(pessoa["cpf"], pessoa["nome"])
    nome_pessoa = pessoa["nome"]

    documento = re.sub(r'\D', '', pessoa.get("cpf", ""))
    chaves_mesmo_documento = []
    if len(documento) >= 9:
        chaves_mesmo_documento = [
            chave
            for chave, dados in estado.items()
            if re.sub(r'\D', '', dados.get("cpf_original", "")) == documento
        ]
        for chave in chaves_mesmo_documento:
            if nomes_compativeis(estado[chave]["nome"], nome_pessoa):
                return chave
        # O documento do casal aparece muitas vezes apenas uma vez ao fim da
        # qualificação. Se o nome não for compatível, não se pode atribuir o
        # CPF ao cônjuge e debitar o titular errado.

    if chave_pessoa in estado and nomes_compativeis(estado[chave_pessoa]["nome"], nome_pessoa):
        return chave_pessoa

    for chave_estado, dados_estado in estado.items():
        if nomes_compativeis(dados_estado["nome"], nome_pessoa):
            return chave_estado

    # Só usa o documento isoladamente depois de tentar o nome. Isso mantém a
    # tolerância a abreviações ("J. da Silva") sem confundir o CPF informado
    # uma única vez no fim da qualificação de um casal.
    if len(chaves_mesmo_documento) == 1:
        return chaves_mesmo_documento[0]

    return None


def _debitar_percentual(estado, chaves, percentual):
    """Debita a fração transmitida sem criar saldo negativo nos alienantes.

    Quando um casal ou vários coproprietários transmite uma única fração, o
    título nem sempre individualiza quanto saiu de cada quinhão. A distribuição
    proporcional preserva o total registral e, ao contrário da divisão igual,
    não elimina um titular que possua menos do que a parcela média.
    """
    chaves_validas = list(dict.fromkeys(
        chave for chave in chaves
        if chave in estado and estado[chave].get("proporcao", 0.0) > 0.0
    ))
    disponivel = sum(estado[chave]["proporcao"] for chave in chaves_validas)
    if not chaves_validas or disponivel <= 0.0:
        return 0.0

    debito_total = min(percentual, disponivel)
    restante = debito_total
    for indice, chave in enumerate(chaves_validas):
        saldo = estado[chave]["proporcao"]
        if indice == len(chaves_validas) - 1:
            debito = min(saldo, restante)
        else:
            debito = min(saldo, debito_total * saldo / disponivel)
        estado[chave]["proporcao"] -= debito
        estado[chave].pop("proporcao_texto", None)
        restante -= debito

    for chave in chaves_validas:
        if chave in estado and estado[chave]["proporcao"] < 0.01:
            del estado[chave]
    return debito_total - max(restante, 0.0)


def _debitos_individualizados_por_percentual(texto, estado):
    """Lê quanto cada coproprietário vendeu quando o título individualiza as quotas."""
    trecho = re.search(
        r'\b(?:o\s+im[óo]vel\s+)?(?:[ée]\s+)?vendid[oa]\s+'
        r'da\s+seguinte\s+maneira\s*:\s*(.*?)'
        r'(?=\bO\s+referido\b|\bDOU\s+F[ÉE]\b|\Z)',
        texto,
        re.I | re.DOTALL,
    )
    if not trecho:
        return []

    descricao = trecho.group(1)
    resultados = []
    for chave, dados in estado.items():
        nome = dados.get("nome", "").strip()
        if not nome:
            continue
        encontrado = re.search(re.escape(nome), descricao, re.I)
        if not encontrado:
            continue
        proximo_item = re.search(
            r';\s*(?:e\s*,?\s*)?\d{1,3}\s*\)',
            descricao[encontrado.end():],
            re.I,
        )
        fim = (
            encontrado.end() + proximo_item.start()
            if proximo_item else len(descricao)
        )
        bloco = descricao[encontrado.start():fim]
        percentual = re.search(
            r'\bvend(?:e|eu|em)\b.{0,100}?(\d+(?:[,.]\d+)?)\s*%',
            bloco,
            re.I | re.DOTALL,
        )
        if percentual:
            resultados.append(
                (chave, parse_percentual_declarado(percentual.group(1)))
            )
    return resultados


PADRAO_SUBATO_REGISTRAL_REPETIDO = re.compile(
    r'(?im)^[ \t-]*(?P<tipo>R|AV)\s*(?:[.\-]\s*)?'
    r'(?P<numero>[0-9OIL]+)\s*-\s*\d[\d.]*\b'
)


def _expandir_subatos_repetidos_para_cadeia(atos):
    """Separa lançamentos distintos que a fonte trouxe com o mesmo ordinal.

    O parser global preserva apenas um ordinal por matrícula para não confundir
    referências internas com atos. Alguns livros históricos, porém, realmente
    repetem o mesmo cabeçalho (por exemplo, dois ``R.03-4.860`` consecutivos).
    A cadeia precisa aplicar cada partilha, mas ônus e cancelamentos continuam
    recebendo a lista original e não são afetados por esta tolerância.
    """
    expandidos = []
    traducao_numerica = str.maketrans({"O": "0", "I": "1", "L": "1"})
    for ato in atos:
        descricao = str(getattr(ato, "descricao", ""))
        encontrados = list(PADRAO_SUBATO_REGISTRAL_REPETIDO.finditer(descricao))
        if len(encontrados) < 2:
            expandidos.append(ato)
            continue

        primeiro = encontrados[0]
        tipo = primeiro.group("tipo").upper()
        numero = (
            primeiro.group("numero").upper().translate(traducao_numerica).lstrip("0")
            or "0"
        )
        repetidos = [
            encontrado
            for encontrado in encontrados
            if (
                encontrado.group("tipo").upper() == tipo
                and (
                    encontrado.group("numero")
                    .upper()
                    .translate(traducao_numerica)
                    .lstrip("0")
                    or "0"
                )
                == numero
            )
        ]
        if len(repetidos) < 2:
            expandidos.append(ato)
            continue

        for indice, encontrado in enumerate(repetidos):
            inicio = encontrado.start("tipo")
            fim = (
                repetidos[indice + 1].start("tipo")
                if indice + 1 < len(repetidos)
                else len(descricao)
            )
            bloco = descricao[inicio:fim].strip()
            if bloco:
                expandidos.append(SimpleNamespace(descricao=bloco))
    return expandidos


def _formatar_resultado_cadeia(estado):
    """Converte o estado interno na lista pública de proprietários atuais.

    Descarta saldos residuais (<= 0,01%), trunca cada proporção para baixo em
    duas casas e devolve os centésimos perdidos no truncamento aos últimos da
    lista, para que a soma exibida feche 100% quando o total real já fechava.
    """
    ativos = [dados for dados in estado.values() if dados["proporcao"] > 0.01]
    proporcoes = [math.floor(dados["proporcao"] * 100 + 1e-9) / 100 for dados in ativos]
    total_original = sum(dados["proporcao"] for dados in ativos)
    if ativos and abs(total_original - 100.0) < 0.1:
        centesimos_residuais = int(round((100.0 - sum(proporcoes)) * 100))
        indice = len(proporcoes) - 1
        while centesimos_residuais > 0 and indice >= 0:
            proporcoes[indice] += 0.01
            centesimos_residuais -= 1
            indice -= 1

    resultado = []
    for dados, proporcao in zip(ativos, proporcoes):
        prop_formatada = dados.get("proporcao_texto")
        if not prop_formatada:
            prop_formatada = f"{proporcao:.2f}%".replace('.', ',')
            if prop_formatada.endswith(",00%"):
                prop_formatada = prop_formatada.replace(",00%", "%")

        resultado.append({
            "nome": dados["nome"],
            "cpf": dados["cpf_original"],
            "proporcao": prop_formatada,
            "proporcao_incerta": bool(dados.get("proporcao_incerta")),
        })

    return resultado


def _aplicar_proprietarios_iniciais(estado, texto_integral):
    """Semeia o estado com os proprietários declarados no cabeçalho da matrícula.

    Só usa os percentuais escritos no texto quando todos estão presentes e
    somam 100%; caso contrário divide o imóvel em partes iguais.
    """
    if not texto_integral:
        return

    atos_separados = separar_atos(texto_integral)
    if atos_separados:
        inicio_primeiro_ato = texto_integral.find(atos_separados[0]["texto"])
        cabecalho = texto_integral[:inicio_primeiro_ato] if inicio_primeiro_ato >= 0 else texto_integral
    else:
        cabecalho = texto_integral

    iniciais = extrair_proprietario_inicial(cabecalho)
    if not iniciais:
        return

    percentuais_iniciais = [pessoa.get("percentual") for pessoa in iniciais]
    usar_percentuais_declarados = (
        all(percentual is not None for percentual in percentuais_iniciais)
        and abs(sum(percentuais_iniciais) - 100.0) <= 0.2
    )
    fração = 100.0 / len(iniciais)
    for p in iniciais:
        chave = padronizar_chave(p["cpf"], p["nome"])
        estado[chave] = {
            "nome": p["nome"],
            "cpf_original": p["cpf"],
            "proporcao": (
                p["percentual"]
                if usar_percentuais_declarados else fração
            ),
        }


def _aplicar_retorno_status_quo_ante(estado, ato):
    """Cancelamento que devolve o imóvel aos titulares anteriores ao ato desfeito.

    Devolve True quando reconheceu o retorno e já reconstruiu o estado.
    """
    titulares_retorno = extrair_retorno_status_quo_ante(ato.descricao)
    if not titulares_retorno:
        return False

    estado.clear()
    proporcao_retorno = 100.0 / len(titulares_retorno)
    for titular in titulares_retorno:
        chave = padronizar_chave(titular["cpf"], titular["nome"])
        estado[chave] = {
            "nome": titular["nome"],
            "cpf_original": titular["cpf"],
            "proporcao": proporcao_retorno,
        }
    return True


def _aplicar_alteracao_de_nome(estado, ato):
    """Averbação que só troca o nome de um titular (casamento, razão social...).

    Não encerra o processamento do ato: o mesmo texto ainda pode conter
    transmissão, por isso não devolve nada.
    """
    novo_nome = extrair_alteracao_nome(ato.descricao)
    if not novo_nome:
        return

    compativeis = [
        chave for chave, dados in estado.items()
        if nomes_compativeis(dados["nome"], novo_nome)
    ]
    if not compativeis:
        documento_alteracao = re.search(
            r'\b(?:CPF|CNPJ|CGC)(?:/MF)?\b[^\d]{0,30}([\d.\-/]{9,20})',
            ato.descricao,
            re.I,
        )
        documento_limpo = (
            re.sub(r'\D', '', documento_alteracao.group(1))
            if documento_alteracao else ""
        )
        if documento_limpo:
            compativeis = [
                chave for chave, dados in estado.items()
                if re.sub(r'\D', '', dados.get("cpf_original", "")) == documento_limpo
            ]
    if len(compativeis) == 1:
        estado[compativeis[0]]["nome"] = novo_nome


def _aplicar_indicacao_titularidade(estado, ato):
    """Ato que declara explicitamente a titularidade completa e atual do imóvel.

    Só substitui o estado quando os percentuais declarados fecham 100%.
    Devolve True quando assumiu a titularidade declarada.
    """
    indicados = extrair_indicacao_titularidade(ato.descricao)
    total_indicado = sum(item["percentual"] for item in indicados)
    if not indicados or abs(total_indicado - 100.0) > 0.2:
        return False

    estado_anterior = estado.copy()
    estado.clear()
    for indicado in indicados:
        chave_anterior = encontrar_chave_no_estado(indicado, estado_anterior)
        documento_anterior = (
            estado_anterior[chave_anterior].get("cpf_original")
            if chave_anterior else None
        )
        chave = chave_para_incluir(indicado, estado)
        estado[chave] = {
            "nome": indicado["nome"],
            "cpf_original": documento_anterior or indicado["cpf"],
            "proporcao": indicado["percentual"],
            "proporcao_texto": indicado["proporcao_texto"],
        }
    return True


def _aplicar_consolidacao_fiduciaria(estado, ato):
    """Consolidação da propriedade fiduciária: o credor passa a ser dono pleno.

    Devolve True quando reconheceu a consolidação.
    """
    credores_consolidados = extrair_credor_consolidacao(ato.descricao)
    if not credores_consolidados:
        return False

    estado.clear()
    proporcao = 100.0 / len(credores_consolidados)
    for credor in credores_consolidados:
        chave = padronizar_chave(credor["cpf"], credor["nome"])
        estado[chave] = {
            "nome": credor["nome"],
            "cpf_original": credor["cpf"],
            "proporcao": proporcao
        }
    return True


def _aplicar_retificacoes_cpf(estado, ato):
    """Averbação que corrige/completa o documento de um titular já cadastrado.

    Não encerra o processamento do ato, por isso não devolve nada.
    """
    for pessoa in extrair_retificacoes_cpf(ato.descricao):
        nome_retificado = limpar_nome(pessoa["nome"])
        chave_encontrada = None
        for chave, dados in estado.items():
            nome_atual = limpar_nome(dados["nome"])
            if (
                nome_retificado == nome_atual
                or nome_retificado in nome_atual
                or nome_atual in nome_retificado
                or nomes_compativeis(pessoa["nome"], dados["nome"])
            ):
                chave_encontrada = chave
                break
        if not chave_encontrada:
            continue
        dados = estado.pop(chave_encontrada)
        dados["cpf_original"] = pessoa["cpf"]
        nova_chave = padronizar_chave(pessoa["cpf"], dados["nome"])
        if nova_chave in estado:
            estado[nova_chave]["proporcao"] += dados["proporcao"]
            estado[nova_chave]["cpf_original"] = pessoa["cpf"]
        else:
            estado[nova_chave] = dados


def _aplicar_estremacao(estado, ato, descricao_normalizada):
    """Estremação: a parte de um condômino sai para matrícula autônoma.

    O titular estremado deixa esta matrícula; se o texto indicar que o que
    ficou é o remanescente, os saldos restantes são renormalizados para 100%.
    Devolve True quando o ato é uma estremação (mesmo sem titular localizado).
    """
    if not (
        "ESTREMACAO" in descricao_normalizada
        and "MATRICULA AUTONOMA" in descricao_normalizada
    ):
        return False

    titular_extremado = re.search(
        r'pertencente\s+exclusivamente\s+a\s+([^,;]+)',
        ato.descricao,
        re.I,
    )
    if titular_extremado:
        nome_extremado = titular_extremado.group(1).strip()
        chave_extremada = next(
            (
                chave for chave, dados in estado.items()
                if nomes_compativeis(dados["nome"], nome_extremado)
            ),
            None,
        )
        if chave_extremada:
            del estado[chave_extremada]
            if "REMANESCENTE" in descricao_normalizada and estado:
                total_remanescente = sum(
                    dados["proporcao"] for dados in estado.values()
                )
                if total_remanescente > 0:
                    fator_remanescente = 100.0 / total_remanescente
                    for dados in estado.values():
                        dados["proporcao"] *= fator_remanescente
                        dados.pop("proporcao_texto", None)
    return True


def _renormalizar_remanescente(estado):
    total = sum(dados["proporcao"] for dados in estado.values())
    if total <= 0:
        return
    fator = 100.0 / total
    for dados in estado.values():
        dados["proporcao"] *= fator
        dados.pop("proporcao_texto", None)


def _aplicar_desmembramento_por_divisao(estado, ato, descricao_normalizada):
    """Retira o condômino cuja gleba foi levada para matrícula autônoma.

    Nas divisões antigas, a averbação diz que se desmembrou "uma gleba ...
    pertencente a Fulano". Isso não transfere a gleba a Fulano: ela já era
    dele e deixa a matrícula originária. O remanescente passa a representar
    100% apenas entre os titulares que ficaram.
    """
    if not (
        "EM VIRTUDE DE DIVISAO" in descricao_normalizada
        and re.search(r"\bDESMEMBROU-SE\s+DESTA\s+MATRICULA\b", descricao_normalizada)
        and "MATRICULAD" in descricao_normalizada
        and "PERTENCENTE A" in descricao_normalizada
    ):
        return False

    trecho = re.search(
        r"\bpertencente\s+(?:a|ao|aos|as)\s+(.+?)"
        r"(?=\bO\s+referido\s+e\s+verdade\b|\bDou\s+fe\b|$)",
        ato.descricao,
        re.I | re.DOTALL,
    )
    if trecho:
        titulares_destacados = trecho.group(1).strip(" .;:-")
        chaves = [
            chave
            for chave, dados in estado.items()
            if nomes_compativeis(dados["nome"], titulares_destacados)
            or limpar_nome(dados["nome"]) in limpar_nome(titulares_destacados)
        ]
        for chave in chaves:
            del estado[chave]
        if chaves and estado:
            _renormalizar_remanescente(estado)
    # Mesmo quando o nome antigo não foi localizado, a averbação não é
    # uma aquisição no remanescente e não deve cair no fluxo de transmissão.
    return True


def _divisao_abre_sucessoras_e_encerra_origem(descricao_normalizada):
    return bool(
        "DIVISAO" in descricao_normalizada
        and len(re.findall(r"\bMATRICULAD[AO]\s+SOB\b", descricao_normalizada)) >= 2
        and re.search(r"\bENCERRAD[AO]\s+(?:ESTA|A\s+PRESENTE)\s+MATRICULA\b", descricao_normalizada)
        and not re.search(
            r"\bCOUBE\s+EXCLUSIVAMENTE\b.{0,300}\b(?:PRESENTE\s+MATRICULA|QUINHAO\s+CONSTANTE)\b",
            descricao_normalizada,
        )
    )


def _aplicar_partilha_integral_agrupada(estado, grupo):
    """Partilha cujos quinhões estão espalhados em vários atos consecutivos.

    _grupos_partilha_integrais() já reuniu os atos do mesmo inventário. Aqui
    decide-se de quem sai o imóvel partilhado: quando dá para identificar o
    autor da herança/espólio/meeiro entre os titulares atuais, só o quinhão
    dessa pessoa é redistribuído (escalado pela fração que ela tinha); caso
    contrário a partilha alcança o imóvel inteiro e o estado é zerado.
    """
    _, itens, descricoes = grupo
    escala = 1.0
    chave_substituida = None
    assinatura = _assinatura_partilha(descricoes[0]) or ''
    prefixo_autor = 'AUTOR DA HERANCA:'
    prefixo_espolio = 'ESPOLIO TRANSMITENTE:'
    percentuais_declarados = [
        parse_percent(descricao) for descricao in descricoes
    ]
    percentuais_sobre_imovel = (
        abs(sum(percentuais_declarados) - 100.0) <= 0.2
        and all(
            (
                re.search(
                    r'\bparte\s+(?:ideal|correspondente)\s+(?:a|de)\s*'
                    r'\d+(?:[,.]\d+)?\s*%.{0,800}?'
                    r'\b(?:sobre|do)\s+(?:o\s+)?im[óo]vel\b',
                    descricao,
                    re.I | re.DOTALL,
                )
                or re.search(
                    r'\bparte\s+ideal\s+de\s*(?:[A-Z]{1,3}\$?\s*)?'
                    r'[\d.,]+.{0,120}?\b(?:avalia[çc][ãa]o|avaliad[oa])'
                    r'\s+(?:de|em)\s*(?:[A-Z]{1,3}\$?\s*)?[\d.,]+'
                    r'.{0,180}?\b(?:no|sobre\s+o)\s+im[óo]vel\b',
                    descricao,
                    re.I | re.DOTALL,
                )
            )
            for descricao in descricoes
        )
    )
    percentuais_das_partes_do_autor = all(
        re.search(
            r'\d+(?:[,.]\d+)?\s*%\s+das\s+partes?\s+a\s+saber\b',
            descricao,
            re.I,
        )
        for descricao in descricoes
    )
    if (
        (not percentuais_sobre_imovel or percentuais_das_partes_do_autor)
        and assinatura.startswith((prefixo_autor, prefixo_espolio))
    ):
        prefixo = (
            prefixo_autor
            if assinatura.startswith(prefixo_autor)
            else prefixo_espolio
        )
        autor = assinatura[len(prefixo):].strip()
        chave_substituida = next(
            (
                chave for chave, dados in estado.items()
                if nomes_compativeis(dados['nome'], autor)
            ),
            None,
        )
    if (
        not percentuais_sobre_imovel
        and not chave_substituida
        and assinatura.startswith(prefixo_espolio)
    ):
        quota = next(
            (
                parse_percentual_declarado(valor)
                for valor in re.findall(
                    r'\bquota\s*\(\s*(\d+(?:[,.]\d+)?)\s*%\s*\)',
                    ' '.join(descricoes),
                    re.I,
                )
            ),
            None,
        )
        chaves_adquirentes = {
            encontrar_chave_no_estado(adquirente, estado)
            for adquirentes, _ in itens
            for adquirente in adquirentes
        }
        candidatos = [
            chave for chave in chaves_adquirentes
            if (
                chave in estado
                and quota is not None
                and abs(estado[chave]['proporcao'] - quota) <= 0.02
            )
        ]
        if len(candidatos) == 1:
            chave_substituida = candidatos[0]
        if not chave_substituida and quota is not None:
            nomes_adquirentes = [
                limpar_nome(adquirente["nome"])
                for adquirentes, _ in itens
                for adquirente in adquirentes
            ]
            candidatos_por_nome_e_quota = [
                chave for chave, dados in estado.items()
                if (
                    abs(dados["proporcao"] - quota) <= 0.02
                    and any(
                        limpar_nome(dados["nome"]).split()[:2]
                        == nome_adquirente.split()[:2]
                        for nome_adquirente in nomes_adquirentes
                    )
                )
            ]
            if len(candidatos_por_nome_e_quota) == 1:
                chave_substituida = candidatos_por_nome_e_quota[0]
    if not percentuais_sobre_imovel and not chave_substituida:
        meeiro = re.search(
            r'coube\s+ao\s+vi[úu]vo\s+meeiro\s+([^,;]+)',
            descricoes[0],
            re.I,
        )
        if meeiro:
            nome_meeiro = meeiro.group(1).strip()
            chave_substituida = next(
                (
                    chave for chave, dados in estado.items()
                    if nomes_compativeis(dados['nome'], nome_meeiro)
                ),
                None,
            )
    if chave_substituida:
        escala = estado[chave_substituida]['proporcao'] / 100.0
        del estado[chave_substituida]
    else:
        estado.clear()
    for adquirentes, percentual in itens:
        percentual_individual = percentual * escala / len(adquirentes)
        for adquirente in adquirentes:
            chave = chave_para_incluir(adquirente, estado)
            if chave not in estado:
                estado[chave] = {
                    "nome": adquirente["nome"],
                    "cpf_original": adquirente["cpf"],
                    "proporcao": 0.0,
                }
            estado[chave]["proporcao"] += percentual_individual


# Naturezas de ato que efetivamente transferem domínio. Um ato cuja descrição
# não cite nenhuma delas (nem adjudicação) não altera a titularidade.
ATOS_TRANSMISSAO = (
    "VENDA E COMPRA", "COMPRA E VENDA", "INVENTARIO", "PARTILHA",
    "SOBREPARTILHA", "DOACAO", "REFORMA AGRARIA", "TITULO DE DOMINIO",
    "USUCAPIAO", "ARREMATACAO", "DACAO", "INTEGRALIZACAO", "PERMUTA",
    "DIVISAO", "REGULARIZACAO FUNDIARIA", "LEGITIMACAO FUNDIARIA",
)


def _substituir_estado_por_distribuicao(estado, distribuicao):
    """Zera o estado e o reconstrói a partir de pares (adquirente, percentual)."""
    estado.clear()
    for adquirente, percentual_individual in distribuicao:
        chave = chave_para_incluir(adquirente, estado)
        estado[chave] = {
            "nome": adquirente["nome"],
            "cpf_original": adquirente["cpf"],
            "proporcao": percentual_individual,
        }


def _aplicar_distribuicao_explicita(estado, ato, adquirentes):
    """Aquisições em que o próprio ato já diz a fração final de cada adquirente.

    Cobre três redações: distribuição por grupos, por áreas e a fórmula
    "passaram a ser os únicos proprietários (...) na proporção de X% para cada
    um". Em todas o ato define a titularidade inteira, então o estado anterior
    é substituído. Devolve True quando alguma delas foi reconhecida.
    """
    distribuicao_grupos = _distribuicao_percentual_por_grupos(
        ato.descricao, adquirentes
    )
    if distribuicao_grupos:
        _substituir_estado_por_distribuicao(estado, distribuicao_grupos)
        return True

    distribuicao_areas = _distribuicao_percentual_por_areas(
        ato.descricao, adquirentes
    )
    if distribuicao_areas:
        _substituir_estado_por_distribuicao(estado, distribuicao_areas)
        return True

    percentual_final_cada = re.search(
        r'passaram\s+a\s+ser\s+os\s+[úu]nicos\s+propriet[áa]rios.*?'
        r'propor[çc][ãa]o\s+de\s*(\d+(?:[,.]\d+)?)\s*%\s+para\s+cada\s+um',
        ato.descricao,
        re.I | re.DOTALL,
    )
    if percentual_final_cada:
        percentual_cada = float(percentual_final_cada.group(1).replace(',', '.'))
        if abs(percentual_cada * len(adquirentes) - 100.0) <= 0.2:
            _substituir_estado_por_distribuicao(
                estado,
                [(adquirente, percentual_cada) for adquirente in adquirentes],
            )
            return True

    return False


def _medir_aquisicao(ato, bloco_adq, adquirentes, percentual_ato,
                     percentual_presumido, distribuicao_valores_adquirentes):
    """Reúne, num só lugar, tudo que decide como a aquisição será aplicada.

    Define de onde sai a fração de cada adquirente (percentual próprio,
    distribuição por valores ou divisão igual do percentual do ato) e
    classifica a natureza da partilha -- meação, divórcio, quinhão de espólio
    e herdeiro que já constava integral --, casos em que o adquirente
    substitui o quinhão que já tinha em vez de somar a ele.
    """
    if (
        len(distribuicao_valores_adquirentes) == len(adquirentes)
        and abs(sum(percentual for _, percentual in distribuicao_valores_adquirentes) - percentual_ato) <= 0.2
    ):
        percentual_por_pessoa = {
            id(pessoa): percentual
            for pessoa, percentual in distribuicao_valores_adquirentes
        }
        percentuais_individuais = [percentual_por_pessoa.get(id(a)) for a in adquirentes]
    else:
        percentuais_individuais = [a.get("percentual") for a in adquirentes]
    usar_individual = all(p is not None for p in percentuais_individuais)
    if usar_individual:
        percentual_ato = sum(percentuais_individuais)

    descricao_limpa = limpar_nome(ato.descricao)
    adquirente_limpo = limpar_nome(bloco_adq)
    adquirente_e_meeiro = (
        "MEACAO" in adquirente_limpo
        or "MEEIR" in adquirente_limpo
        or bool(re.search(
            r'\bcoube\s+ao\s+vi[úu]vo\s+meeiro\b',
            ato.descricao,
            re.I,
        ))
    )
    de_inventario_ou_partilha = (
        "INVENTARIO" in descricao_limpa or "PARTILHA" in descricao_limpa
    )
    return SimpleNamespace(
        percentual=percentual_ato,
        percentual_presumido=percentual_presumido,
        percentuais_individuais=percentuais_individuais,
        usar_individual=usar_individual,
        percent_por_adquirente=percentual_ato / len(adquirentes),
        meacao=(
            any(
                termo in descricao_limpa
                for termo in ("INVENTARIO", "PARTILHA", "ADJUDICACAO")
            )
            and adquirente_e_meeiro
        ),
        divorcio=(
            "DIVORCIO" in descricao_limpa
            and ("ATRIBUID" in descricao_limpa or "PERTENCENDO" in descricao_limpa)
        ),
        espolio_com_quinhao=(
            de_inventario_ou_partilha
            and "ESPOLIO" in descricao_limpa
            and "TRANSMITENTE" in descricao_limpa
            and percentual_ato < 99.0
        ),
        herdeiro_ja_integral=(
            de_inventario_ou_partilha
            and "BENS DEIXADOS POR FALECIMENTO" in descricao_limpa
            and percentual_ato < 99.0
        ),
    )


def _debitar_alienantes(estado, ato, adquirentes, transmitentes, aquisicao):
    """Retira dos titulares atuais a fração que este ato transmitiu.

    Acima de 99% a transmissão alcança o imóvel inteiro e o estado é
    zerado. Abaixo disso é preciso descobrir de quem sai a fração, em
    ordem de confiança: débitos individualizados por percentual, débitos
    por valores declarados, transmitentes nomeados no ato e, por fim,
    algumas inferências para redações antigas que omitem o alienante.
    Devolve True quando algum saldo foi efetivamente debitado.
    """
    houve_debito = False
    if aquisicao.percentual >= 99.0:
        estado.clear()
    else:
        chaves_debito = []
        estado_com_chaves = [
            {"nome": dados["nome"], "_chave": chave}
            for chave, dados in estado.items()
        ]
        debitos_por_valor = _percentuais_por_valores_em_trecho(
            ato.descricao,
            estado_com_chaves,
            r'vendid[oa]\s+da\s+seguinte\s+maneira\s*:',
        )
        debitos_individualizados = _debitos_individualizados_por_percentual(
            ato.descricao,
            estado,
        )
        if (
            debitos_individualizados
            and abs(
                sum(percentual for _, percentual in debitos_individualizados)
                - aquisicao.percentual
            ) <= 0.2
        ):
            for chave, percentual in debitos_individualizados:
                houve_debito = (
                    _debitar_percentual(estado, [chave], percentual) > 0.0
                ) or houve_debito
        elif (
            debitos_por_valor
            and abs(sum(percentual for _, percentual in debitos_por_valor) - aquisicao.percentual) <= 0.2
        ):
            for pessoa_estado, percentual in debitos_por_valor:
                houve_debito = (
                    _debitar_percentual(
                        estado,
                        [pessoa_estado["_chave"]],
                        percentual,
                    ) > 0.0
                ) or houve_debito
        elif transmitentes:
            for t in transmitentes:
                chave_encontrada = encontrar_chave_no_estado(t, estado)
                if chave_encontrada and chave_encontrada not in chaves_debito:
                    chaves_debito.append(chave_encontrada)

        if (
            not houve_debito
            and not chaves_debito
            and aquisicao.espolio_com_quinhao
            and not aquisicao.meacao
            and re.search(
                r'\b100\s*%\s+da\s+quota\s*\(',
                ato.descricao,
                re.I,
            )
            and len(adquirentes) == 1
        ):
            chave_adquirente = chave_para_incluir(adquirentes[0], estado)
            candidatos_quinhao = [
                chave for chave, dados in estado.items()
                if (
                    chave != chave_adquirente
                    and abs(dados["proporcao"] - aquisicao.percentual) <= 0.02
                )
            ]
            if len(candidatos_quinhao) == 1:
                chaves_debito = candidatos_quinhao

        if not houve_debito and not chaves_debito and len(estado) == 1:
            unica_chave = next(iter(estado))
            if (
                abs(estado[unica_chave]["proporcao"] - 100.0) <= 0.2
                and estado[unica_chave]["proporcao"] + 0.1 >= aquisicao.percentual
                and not any(
                    nomes_compativeis(estado[unica_chave]["nome"], adquirente["nome"])
                    for adquirente in adquirentes
                )
            ):
                chaves_debito = [unica_chave]

        # Em alguns traslados antigos o transmitente ficou apenas no título
        # antecedente. Quando um coproprietário já cadastrado adquire a parte
        # exata que completa seus 100%, a contrapartida só pode sair dos
        # demais saldos atuais, que juntos continuam totalizando 100%.
        if (
            not houve_debito
            and not chaves_debito
            and len(adquirentes) == 1
            and not (aquisicao.meacao or aquisicao.divorcio)
        ):
            chave_adquirente = chave_para_incluir(adquirentes[0], estado)
            total_atual = sum(item["proporcao"] for item in estado.values())
            saldo_adquirente = estado.get(chave_adquirente, {}).get("proporcao", 0.0)
            outras_chaves = [chave for chave in estado if chave != chave_adquirente]
            if (
                chave_adquirente in estado
                and abs(total_atual - 100.0) <= 0.2
                and abs(saldo_adquirente + aquisicao.percentual - 100.0) <= 0.2
                and sum(estado[chave]["proporcao"] for chave in outras_chaves) + 0.1 >= aquisicao.percentual
            ):
                chaves_debito = outras_chaves

        if not houve_debito and chaves_debito:
            houve_debito = _debitar_percentual(
                estado, chaves_debito, aquisicao.percentual
            ) > 0.0
    return houve_debito


def _creditar_adquirentes(estado, adquirentes, aquisicao, houve_debito):
    """Lança a fração adquirida para cada adquirente do ato.

    Nos casos de meação, divórcio e herdeiro já integral o quinhão é
    substituído em vez de somado -- o texto está redescrevendo a parte
    que a pessoa passa a ter, não acrescentando outra.
    """
    for indice_adquirente, a in enumerate(adquirentes):
        chave_a = chave_para_incluir(a, estado)
        proporcao_adquirida = (
            aquisicao.percentuais_individuais[indice_adquirente]
            if aquisicao.usar_individual
            else aquisicao.percent_por_adquirente
        )
        # aquisicao.percentuais_individuais vem de fonte própria (percentual do
        # próprio adquirente ou distribuição por valores), não do
        # fallback cego de parse_percent -- só marca incerteza quando o
        # aquisicao.percent_por_adquirente (derivado de aquisicao.percentual) é quem está sendo
        # usado de fato.
        proporcao_adquirida_incerta = aquisicao.percentual_presumido and not aquisicao.usar_individual
        ajustar_quinhao_existente = (
            not houve_debito
            and chave_a in estado
            and (
                aquisicao.meacao
                or aquisicao.divorcio
                or (
                    aquisicao.herdeiro_ja_integral
                    and estado[chave_a]["proporcao"] >= 99.0
                )
            )
        )
        if ajustar_quinhao_existente:
            estado[chave_a]["nome"] = a["nome"]
            if re.sub(r'\D', '', a.get("cpf", "")):
                estado[chave_a]["cpf_original"] = a["cpf"]
            if not aquisicao.herdeiro_ja_integral:
                estado[chave_a]["proporcao"] = proporcao_adquirida
                estado[chave_a]["proporcao_incerta"] = proporcao_adquirida_incerta
            estado[chave_a].pop("proporcao_texto", None)
            continue
        if chave_a not in estado:
            estado[chave_a] = {"nome": a["nome"], "cpf_original": a["cpf"], "proporcao": 0.0}
        else:
            documento_novo = re.sub(r'\D', '', a.get("cpf", ""))
            documento_atual = re.sub(r'\D', '', estado[chave_a].get("cpf_original", ""))
            documento_atual_repetido = documento_atual and sum(
                re.sub(r'\D', '', item.get("cpf_original", "")) == documento_atual
                for item in estado.values()
            ) > 1
            if documento_novo and (not documento_atual or documento_atual_repetido):
                estado[chave_a]["cpf_original"] = a["cpf"]
            estado[chave_a]["nome"] = a["nome"]
        estado[chave_a]["proporcao"] += proporcao_adquirida
        estado[chave_a]["proporcao_incerta"] = proporcao_adquirida_incerta
        estado[chave_a].pop("proporcao_texto", None)

    if len(estado) == 1:
        unico = next(iter(estado.values()))
        if 100.0 < unico["proporcao"] <= 125.0:
            unico["proporcao"] = 100.0


def calcular_cadeia_dominial(atos, texto_integral=""):
    atos = _expandir_subatos_repetidos_para_cadeia(atos)
    estado = {}

    _aplicar_proprietarios_iniciais(estado, texto_integral)

    grupos_partilha = _grupos_partilha_integrais(atos)
    indices_agrupados = {
        indice_ato
        for inicio, (fim, _, _) in grupos_partilha.items()
        for indice_ato in range(inicio + 1, fim)
    }

    for indice_ato, ato in enumerate(atos):
        if indice_ato in indices_agrupados:
            continue
        if indice_ato in grupos_partilha:
            _aplicar_partilha_integral_agrupada(estado, grupos_partilha[indice_ato])
            continue

        if _aplicar_retorno_status_quo_ante(estado, ato):
            continue

        # Não encerra o ato: o mesmo texto ainda pode conter transmissão.
        _aplicar_alteracao_de_nome(estado, ato)

        if _aplicar_indicacao_titularidade(estado, ato):
            continue

        if _aplicar_consolidacao_fiduciaria(estado, ato):
            continue

        # Também não encerra o ato.
        _aplicar_retificacoes_cpf(estado, ato)

        if _aplicar_desquite(ato.descricao, estado):
            continue

        descricao_normalizada = limpar_nome(ato.descricao)
        if _aplicar_desmembramento_por_divisao(estado, ato, descricao_normalizada):
            continue
        if _divisao_abre_sucessoras_e_encerra_origem(descricao_normalizada):
            continue
        if _aplicar_estremacao(estado, ato, descricao_normalizada):
            continue

        if (
            not any(x in descricao_normalizada for x in ATOS_TRANSMISSAO)
            and "ADJUDICA" not in descricao_normalizada
            and "FOI ADQUIRIDO POR" not in descricao_normalizada
            and "FOI ADQUIRIDA POR" not in descricao_normalizada
        ):
            continue
        
        percentual_ato = parse_percent(ato.descricao)
        percentual_presumido = percentual_e_presumido(ato.descricao, percentual_ato)

        bloco_adq = extrair_bloco(ato.descricao, "ADQUIRENTE")
        bloco_transm = extrair_bloco(ato.descricao, "TRANSMITENTE")
        
        adquirentes = extrair_pessoas(bloco_adq)
        adquirentes = enriquecer_documentos_adquirentes(
            adquirentes,
            ato.descricao,
        )
        transmitentes = extrair_pessoas(bloco_transm)
        
        if not adquirentes:
            continue

        if _aplicar_distribuicao_explicita(estado, ato, adquirentes):
            continue

        distribuicao_valores_adquirentes = _percentuais_por_valores_em_trecho(
            ato.descricao,
            adquirentes,
            r'\bsendo\s*:',
        )

        aquisicao = _medir_aquisicao(
            ato, bloco_adq, adquirentes, percentual_ato,
            percentual_presumido, distribuicao_valores_adquirentes,
        )

        houve_debito = _debitar_alienantes(
            estado, ato, adquirentes, transmitentes, aquisicao
        )
        _creditar_adquirentes(estado, adquirentes, aquisicao, houve_debito)
            
    return _formatar_resultado_cadeia(estado)
