import re
import unicodedata
import math
from difflib import SequenceMatcher

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
        (r'\btr[eê]s\s+quart[oa]s?\s+do\s+im[óo]vel\b', 75.0),
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

def extrair_bloco(texto, tipo):
    if tipo == "ADQUIRENTE":
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
            r'\b(?:ADQUIRENTES?|OUTORGADOS?|DONAT[ÁA]RI[OA]S?|ADJUDICANTES?|'
            r'ARREMATANTES?|COMPRADOR(?:ES)?)\s*:\s*(.*?)'
            r'(?=\b(?:IM[ÓO]VEL|OBJETO|ORIGEM|FORMA\s+DO\s+T[ÍI]TULO|'
            r'TRANSMITENTES?|OUTORGANTES?|DOADORES?|INTERVENIENTES?(?:\s+ANUENTES?)?)\s*:|'
            r'\*NOTA|\bDOU\s+F[ÉE]\b|\Z)',
            texto,
            re.I | re.DOTALL,
        )
        if m: return m.group(1).strip().rstrip(';, ')

        m = re.search(r'\bvend(?:eu|eram)\s+.*?\bpara\s+(.*?)(?=\bpelo valor\b|\bpelo preço\b|;|\.\s*Dou|\.\s*O referido|\Z)', texto, re.I | re.DOTALL)
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
            r'\bação\s+de\s+usucapião\s+promovida\s+por\s+(.*?)'
            r'(?=\s+em\s+desfavor\b|\s+contra\b|\*NOTA|\bCOTAÇÃO\b|\.\s*Dou|\.\s*DOU|\Z)',
            texto,
            re.I | re.DOTALL,
        )
        if m: return m.group(1).strip().rstrip(';, ')

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
            r'lavrada\b.*?,\s*(.*?)(?=[;,]\s*adquiri(?:u|do)\s+por\s+compra\b)',
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

        m = re.search(r'adquirido\s+(?:por|pel[oa])\s*:?\s*(.*?)(?=\bpor compra\b|\bpelo preço\b|\bem pagamento\b|\bpor doação\b)', texto, re.I | re.DOTALL)
        if m:
            bloco = re.split(
                r'\bneste\s+ato\s+representad[oa]\b|\bdevidamente\s+representad[oa]\b',
                m.group(1),
                maxsplit=1,
                flags=re.I,
            )[0]
            return bloco.strip().rstrip(';, ')

        m = re.search(
            r'coube\s+(?:a|ao|aos|à|às|á|ás)\s+(.*?)'
            r'(?=\bem pagamento\b|\bem virtude\b|\bparte\s+ideal\b|\ba totalidade\b|'
            r',\s*\d+(?:[,.]\d+)?\s*%|\bpor aquisi[çc][ãa]o\b|\bconforme\b)',
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

        m = re.search(r'TRANSMITENTE[S]?\s*:(.*?)(?=\bADQUIRENTE[S]?\s*:|\bIM[ÓO]VEL\s*:)', texto, re.I | re.DOTALL)
        if m: return m.group(1).strip().rstrip(';, ')

        m = re.search(r'DOADOR(?:A|ES|AS)?\s*:(.*?)(?=\bINTERVENIENTE\s*:|\bDONAT[AÁ]RIO[S]?\s*:|\bOBJETO\s*:|\bIM[ÓOÃ“]VEL\s*:)', texto, re.I | re.DOTALL)
        if m: return m.group(1).strip().rstrip(';, ')

        m = re.search(r'por compra feita(?:\s+feita)? (?:a|à|ao|aos|às)\s+(.*?)(?=\bpelo preço\b|\bpelo valor\b|;|\.\s*O referido)', texto, re.I | re.DOTALL)
        if m: return m.group(1).strip().rstrip(';, ')
        
        m = re.search(
            r'por\s+doa[çc][ãa]o\s+que\s+(?:lhe|lhes)\s+(?:fez|fizeram)\s+(.*?)'
            r'(?=\bno\s+valor\b|\bpelo\s+valor\b|\bsem\s+condi[çc][õo]es\b|;|\.\s*O\s+referido)',
            texto,
            re.I | re.DOTALL,
        )
        if m: return m.group(1).strip().rstrip(';, ')

        m = re.search(
            r'por\s+doa[çc][ãa]o\s+feita\s+por\s+(.*?)'
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

    # Em atos com casal, cada cônjuge pode ter nome e CPF próprios no mesmo bloco.
    # Se não separarmos aqui, a limpeza abaixo remove o segundo cônjuge inteiro.
    partes_numeradas = re.split(
        r'(?:^|\s+|;)\s*(?:\d{1,3}|[IVX]+)(?:\)\s*-?|-)\s*',
        texto_bloco,
    )
    partes_numeradas = [p.strip() for p in partes_numeradas if p.strip()]

    if len(partes_numeradas) > 1:
        partes = partes_numeradas
    else:
        partes_sem_ponto_virgula = re.split(
            r';\s*(?:e\s*,?\s*)?(?=[A-ZÁÀÂÃÉÈÊÍÌÎÓÒÔÕÚÙÛÇ]'
            r'[A-ZÁÀÂÃÉÈÊÍÌÎÓÒÔÕÚÙÛÇa-záàâãéèêíìîóòôõúùûç]+'
            r'(?:\s+[A-ZÁÀÂÃÉÈÊÍÌÎÓÒÔÕÚÙÛÇ]'
            r'[A-ZÁÀÂÃÉÈÊÍÌÎÓÒÔÕÚÙÛÇa-záàâãéèêíìîóòôõúùûç]+){1,})',
            texto_bloco,
        )
        if len(partes_sem_ponto_virgula) > 1:
            partes = [p.strip() for p in partes_sem_ponto_virgula if p.strip()]
        else:
            partes_conjuges = re.split(
                r'\s*,?\s*e\s+(?:seu|sua)\s+(?:c[oô]njuge|mulher|marido|esposa)\s+',
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
        subdivisoes = re.split(
            r'(?<!\bDr)(?<!\bDra)(?<!\bSr)(?<!\bSra)\.\s+'
            r'(?=[A-ZÀ-Ú][^,;]{2,100},\s*brasileir[oa])',
            parte,
        )
        if len(re.findall(r'\b(?:CPF|CIC|CNPJ|CGC)\b', parte, re.I)) >= 2:
            expandidas = []
            for subdivisao in subdivisoes:
                padrao_nova_pessoa = re.compile(
                    r'\s+e\s+(?=[A-ZÀ-Ú][^,;]{2,100},[^;]{0,420}?\b(?:CPF|CIC|CNPJ|CGC)\b)'
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
        nome_match = re.match(r'^([^,]+)', parte)
        
        # MEGA BRAIN: Agora aceita CNPJ, CGC e a barra "/" na leitura!
        cpf_match = re.search(r'(?:CPF|CIC|CNPJ|CGC|MF)[^\d]*([\d\.\-\/]{9,20})', parte, re.I)
        percentual_match = re.search(
            r'(?:equivalente\s+a|na\s+propor[çc][ãa]o\s+de|parte\s+correspondente\s+a)'
            r'\s*(\d+(?:,\d+)?)%',
            parte,
            re.I,
        )
        percentual = parse_percentual_declarado(percentual_match.group(1)) if percentual_match else None

        nome = nome_match.group(1).strip() if nome_match else "DESCONHECIDO"
        nome = re.sub(r'^\d+(?:\)\s*-?|-)\s*', '', nome)
        nome = re.sub(r'^(?:Dr\.?|Dra\.?|Doutor(?:a)?)\s+', '', nome, flags=re.I)
        cpf = cpf_match.group(1).strip().rstrip('.,;') if cpf_match else "CPF/CNPJ NÃO INFORMADO"

        # Limpeza visual (remove estado civil e termo "pessoa jurídica")
        nome = re.sub(r'\s+e\s+(?:seu\s+c[oô]njuge|sua\s+mulher|seu\s+marido|sua\s+esposa).*', '', nome, flags=re.I)
        nome = re.sub(
            r'^(?:(?:e\s+)?(?:(?:a|o|as|os)\s+)?(?:meeir[oa]|vi[úu]v[oa]|'
            r'herdeir[oa]\s+e\s+cession[áa]ri[oa]|herdeir[oa]\s+(?:filh[oa]|net[oa])|'
            r'herdeir[oa]|cession[áa]ri[oa]|net[oa])\s*:?\s*)+',
            '', nome, flags=re.I,
        )
        nome = re.sub(r'\s*,?\s*casad[oa].*', '', nome, flags=re.I)
        nome = re.sub(r'\s*,?\s*pessoa jur[íi]dica.*', '', nome, flags=re.I)
        nome = re.sub(r'\s+', ' ', nome)
        nome = nome.strip(' ,.()')
        
        if re.match(r'^(?:CPF|CNPJ|CIC|RG)\b', nome, re.I):
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

def extrair_proprietario_inicial(texto_cabecalho):
    m = re.search(r'(?:P?R[OÓ]PRIET)[AÁ]RI[OA]S?\s*[:;]\s*(.*?)(?=\bORIGEM\b|\bT[IÍ]TULO AQUISITIVO\b|\bREGISTRO ANTERIOR\b|\bO referido [ée] verdade\b|\*NOTA\b|\bProtocolo\b|\Z)', texto_cabecalho, re.I | re.DOTALL)
    if m:
        proprietarios = extrair_pessoas(m.group(1).strip())
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
        if proprietario_singular and conjuge_qualificacao and proprietarios:
            return proprietarios[:1]
        return proprietarios
    return []

def extrair_retificacoes_cpf(texto):
    if not re.search(r'RETIFICA[ÇC][ÃA]O', texto, re.I):
        return []

    padrao = re.compile(
        r'([A-ZÀ-Ú][A-ZÀ-Úa-zà-ú\s]+?)\s*,?\s*'
        r'(?:permanece|est[áa])\s+inscrit[oa]\s+no\s+CPF(?:/MF)?\s+sob\s+o\s+n[.º°o]*\s*'
        r'([\d.\-]{9,18})',
        re.I
    )

    pessoas = []
    for nome, cpf in padrao.findall(texto):
        nome = re.sub(r'^.*?\ba\s+saber\s*:\s*', '', nome, flags=re.I).strip(' ,.;:')
        nome = re.sub(r'^e\s+(?:seu|sua)\s+c[oô]njuge\s+', '', nome, flags=re.I).strip()
        pessoas.append({"nome": nome, "cpf": cpf.strip()})
    return pessoas


def extrair_alteracao_nome(texto):
    if not re.search(r'ALTERA[ÇC][ÃA]O\s+(?:DO\s+)?NOME|ALTERA[ÇC][ÃA]O\s+DE\s+ESTADO\s+CIVIL', texto, re.I):
        return ""
    encontrado = re.search(
        r'(?:altera[çc][ãa]o\s+d[oa]\s+nome|nome\s+d[oa]\s+propriet[áa]ri[oa])'
        r'.{0,180}?\bpara\s+([^,;.]+)',
        texto,
        re.I | re.DOTALL,
    )
    return encontrado.group(1).strip() if encontrado else ""

def extrair_credor_consolidacao(texto):
    if not re.search(r'CONSOLIDA[ÇC][ÃA]O\s+DA\s+PROPRIEDADE', texto, re.I):
        return []

    m = re.search(
        r'em\s+favor\s+d[oa]\s+credor[ao]\s+fiduci[áa]ri[oa]\s+([^,]+),'
        r'.*?(?:CNPJ|CPF)(?:/MF)?\s+sob\s+o\s+n[.º°o]*\s*([\d.\-/]{9,20})',
        texto,
        re.I | re.DOTALL
    )
    if not m:
        return []
    return [{"nome": m.group(1).strip(), "cpf": m.group(2).strip()}]

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
        nome = re.sub(r'^(?:(?:e\s*)?(?:Matr[ií]cula|R\.?\s*\d+|AV\.?\s*\d+)[\s,.;/-]*)+', '', nome, flags=re.I).strip(" \t-")
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
    if len(curto) < 2 or SequenceMatcher(None, curto[0], longo[0]).ratio() < 0.9:
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
    """Converte a divisão física declarada no próprio título em percentuais."""
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
        r'autos\s+de\s+(?:partilha\s+amig[áa]vel|div[óo]rcio\s+direto).*?\bde\s+'
        r'([^,;]+?)\s+e\s+([^,;]+?),\s+(?:do\s+Cart[óo]rio|pela\s+Escrivania)',
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
        referencias_integrais = (
            (100.0,)
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

def calcular_cadeia_dominial(atos, texto_integral=""):
    estado = {}
    
    if texto_integral:
        atos_separados = separar_atos(texto_integral)
        if atos_separados:
            inicio_primeiro_ato = texto_integral.find(atos_separados[0]["texto"])
            cabecalho = texto_integral[:inicio_primeiro_ato] if inicio_primeiro_ato >= 0 else texto_integral
        else:
            cabecalho = texto_integral
        
        iniciais = extrair_proprietario_inicial(cabecalho)
        if iniciais:
            fração = 100.0 / len(iniciais)
            for p in iniciais:
                chave = padronizar_chave(p["cpf"], p["nome"])
                estado[chave] = {"nome": p["nome"], "cpf_original": p["cpf"], "proporcao": fração}

    atos_transmissao = [
        "VENDA E COMPRA", "COMPRA E VENDA", "INVENTÁRIO", "PARTILHA",
        "SOBREPARTILHA", "DOAÇÃO", "REFORMA AGRÁRIA", "TÍTULO DE DOMÍNIO",
        "USUCAPIÃO", "ARREMATAÇÃO", "DAÇÃO", "INTEGRALIZAÇÃO", "PERMUTA",
    ]
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
            _, itens, descricoes = grupos_partilha[indice_ato]
            escala = 1.0
            chave_substituida = None
            assinatura = _assinatura_partilha(descricoes[0]) or ''
            prefixo_autor = 'AUTOR DA HERANCA:'
            if assinatura.startswith(prefixo_autor):
                autor = assinatura[len(prefixo_autor):].strip()
                chave_substituida = next(
                    (
                        chave for chave, dados in estado.items()
                        if nomes_compativeis(dados['nome'], autor)
                    ),
                    None,
                )
            if not chave_substituida:
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
            continue

        novo_nome = extrair_alteracao_nome(ato.descricao)
        if novo_nome:
            compativeis = [
                chave for chave, dados in estado.items()
                if nomes_compativeis(dados["nome"], novo_nome)
            ]
            if len(compativeis) == 1:
                estado[compativeis[0]]["nome"] = novo_nome

        indicados = extrair_indicacao_titularidade(ato.descricao)
        total_indicado = sum(item["percentual"] for item in indicados)
        if indicados and abs(total_indicado - 100.0) <= 0.2:
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
            continue

        credores_consolidados = extrair_credor_consolidacao(ato.descricao)
        if credores_consolidados:
            estado.clear()
            proporcao = 100.0 / len(credores_consolidados)
            for credor in credores_consolidados:
                chave = padronizar_chave(credor["cpf"], credor["nome"])
                estado[chave] = {
                    "nome": credor["nome"],
                    "cpf_original": credor["cpf"],
                    "proporcao": proporcao
                }
            continue

        retificados = extrair_retificacoes_cpf(ato.descricao)
        if retificados:
            chaves_encontradas = []
            for pessoa in retificados:
                nome_retificado = limpar_nome(pessoa["nome"])
                for chave, dados in estado.items():
                    nome_atual = limpar_nome(dados["nome"])
                    if nome_retificado == nome_atual or nome_retificado in nome_atual or nome_atual in nome_retificado:
                        chaves_encontradas.append(chave)
                        break

            chaves_encontradas = list(dict.fromkeys(chaves_encontradas))
            if chaves_encontradas:
                proporcao_total = sum(estado[chave]["proporcao"] for chave in chaves_encontradas)
                for chave in chaves_encontradas:
                    del estado[chave]

                proporcao_individual = proporcao_total / len(retificados)
                for pessoa in retificados:
                    chave = padronizar_chave(pessoa["cpf"], pessoa["nome"])
                    estado[chave] = {
                        "nome": pessoa["nome"],
                        "cpf_original": pessoa["cpf"],
                        "proporcao": proporcao_individual
                    }

        if _aplicar_desquite(ato.descricao, estado):
            continue

        if not any(x in ato.descricao.upper() for x in atos_transmissao) and "ADJUDICA" not in ato.descricao.upper():
            continue
        
        percentual_ato = parse_percent(ato.descricao)
        
        bloco_adq = extrair_bloco(ato.descricao, "ADQUIRENTE")
        bloco_transm = extrair_bloco(ato.descricao, "TRANSMITENTE")
        
        adquirentes = extrair_pessoas(bloco_adq)
        transmitentes = extrair_pessoas(bloco_transm)
        
        if not adquirentes:
            continue

        distribuicao_grupos = _distribuicao_percentual_por_grupos(
            ato.descricao, adquirentes
        )
        if distribuicao_grupos:
            estado.clear()
            for adquirente, percentual_individual in distribuicao_grupos:
                chave = chave_para_incluir(adquirente, estado)
                estado[chave] = {
                    "nome": adquirente["nome"],
                    "cpf_original": adquirente["cpf"],
                    "proporcao": percentual_individual,
                }
            continue

        distribuicao_areas = _distribuicao_percentual_por_areas(
            ato.descricao, adquirentes
        )
        if distribuicao_areas:
            estado.clear()
            for adquirente, percentual_individual in distribuicao_areas:
                chave = chave_para_incluir(adquirente, estado)
                estado[chave] = {
                    "nome": adquirente["nome"],
                    "cpf_original": adquirente["cpf"],
                    "proporcao": percentual_individual,
                }
            continue

        distribuicao_valores_adquirentes = _percentuais_por_valores_em_trecho(
            ato.descricao,
            adquirentes,
            r'\bsendo\s*:',
        )

        percentual_final_cada = re.search(
            r'passaram\s+a\s+ser\s+os\s+[úu]nicos\s+propriet[áa]rios.*?'
            r'propor[çc][ãa]o\s+de\s*(\d+(?:[,.]\d+)?)\s*%\s+para\s+cada\s+um',
            ato.descricao,
            re.I | re.DOTALL,
        )
        if percentual_final_cada:
            percentual_cada = float(percentual_final_cada.group(1).replace(',', '.'))
            if abs(percentual_cada * len(adquirentes) - 100.0) <= 0.2:
                estado.clear()
                for adquirente in adquirentes:
                    chave = chave_para_incluir(adquirente, estado)
                    estado[chave] = {
                        "nome": adquirente["nome"],
                        "cpf_original": adquirente["cpf"],
                        "proporcao": percentual_cada,
                    }
                continue
            
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
        usar_percentual_individual = all(p is not None for p in percentuais_individuais)
        if usar_percentual_individual:
            percentual_ato = sum(percentuais_individuais)
        percent_por_adq = percentual_ato / len(adquirentes)
        descricao_limpa = limpar_nome(ato.descricao)
        partilha_meacao = (
            ("INVENTARIO" in descricao_limpa or "PARTILHA" in descricao_limpa)
            and ("MEACAO" in descricao_limpa or "MEEIR" in descricao_limpa)
        )
        partilha_divorcio = (
            "DIVORCIO" in descricao_limpa
            and ("ATRIBUID" in descricao_limpa or "PERTENCENDO" in descricao_limpa)
        )
        partilha_de_espolio_com_quinhao = (
            ("INVENTARIO" in descricao_limpa or "PARTILHA" in descricao_limpa)
            and "ESPOLIO" in descricao_limpa
            and "TRANSMITENTE" in descricao_limpa
            and percentual_ato < 99.0
        )
        partilha_herdeiro_ja_integral = (
            ("INVENTARIO" in descricao_limpa or "PARTILHA" in descricao_limpa)
            and "BENS DEIXADOS POR FALECIMENTO" in descricao_limpa
            and percentual_ato < 99.0
        )
        houve_debito = False
        
        if percentual_ato >= 99.0:
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
            if (
                debitos_por_valor
                and abs(sum(percentual for _, percentual in debitos_por_valor) - percentual_ato) <= 0.2
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

            if not houve_debito and not chaves_debito and len(estado) == 1:
                unica_chave = next(iter(estado))
                if (
                    abs(estado[unica_chave]["proporcao"] - 100.0) <= 0.2
                    and estado[unica_chave]["proporcao"] + 0.1 >= percentual_ato
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
                and not (partilha_meacao or partilha_divorcio)
            ):
                chave_adquirente = chave_para_incluir(adquirentes[0], estado)
                total_atual = sum(item["proporcao"] for item in estado.values())
                saldo_adquirente = estado.get(chave_adquirente, {}).get("proporcao", 0.0)
                outras_chaves = [chave for chave in estado if chave != chave_adquirente]
                if (
                    chave_adquirente in estado
                    and abs(total_atual - 100.0) <= 0.2
                    and abs(saldo_adquirente + percentual_ato - 100.0) <= 0.2
                    and sum(estado[chave]["proporcao"] for chave in outras_chaves) + 0.1 >= percentual_ato
                ):
                    chaves_debito = outras_chaves

            if not houve_debito and chaves_debito:
                houve_debito = _debitar_percentual(
                    estado, chaves_debito, percentual_ato
                ) > 0.0
        
        for indice_adquirente, a in enumerate(adquirentes):
            chave_a = chave_para_incluir(a, estado)
            proporcao_adquirida = (
                percentuais_individuais[indice_adquirente]
                if usar_percentual_individual
                else percent_por_adq
            )
            ajustar_quinhao_existente = (
                not houve_debito
                and chave_a in estado
                and (
                    partilha_meacao
                    or partilha_divorcio
                    or (
                        partilha_herdeiro_ja_integral
                        and estado[chave_a]["proporcao"] >= 99.0
                    )
                )
            )
            if ajustar_quinhao_existente:
                estado[chave_a]["nome"] = a["nome"]
                if re.sub(r'\D', '', a.get("cpf", "")):
                    estado[chave_a]["cpf_original"] = a["cpf"]
                if not partilha_herdeiro_ja_integral:
                    estado[chave_a]["proporcao"] = proporcao_adquirida
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
            estado[chave_a].pop("proporcao_texto", None)

        if len(estado) == 1:
            unico = next(iter(estado.values()))
            if 100.0 < unico["proporcao"] <= 125.0:
                unico["proporcao"] = 100.0
            
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
            "proporcao": prop_formatada
        })
            
    return resultado
