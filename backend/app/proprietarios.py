import re
import unicodedata
import math

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

def parse_percent(texto):
    m_valor = re.search(
        r'parte\s+(?:ideal|correspondente\s+a)\s+(?:de\s*)?(?:[A-Z]{1,3}\$?\s*)?([\d\.,]+).*?'
        r'na\s+(?:avalia\S*|qualifica\S*)\s+de\s*(?:[A-Z]{1,3}\$?\s*)?([\d\.,]+)',
        texto,
        re.IGNORECASE | re.DOTALL
    )
    if m_valor:
        parte = parse_valor_monetario(m_valor.group(1))
        total = parse_valor_monetario(m_valor.group(2))
        if parte is not None and total:
            return (parte / total) * 100.0

    m0 = re.search(r'IM[ÓOÃ“]VEL\s*:\s*(?:equivalente\s+a\s*)?(\d+(?:,\d+)?)%', texto, re.IGNORECASE)
    if m0: return float(m0.group(1).replace(',', '.'))

    m1 = re.search(r'IMÓVEL\s*:\s*(\d+(?:,\d+)?)%', texto, re.IGNORECASE)
    if m1: return float(m1.group(1).replace(',', '.'))
    
    m2 = re.search(r'proporção de\s*(\d+(?:,\d+)?)%', texto, re.IGNORECASE)
    if m2: return float(m2.group(1).replace(',', '.'))

    m3 = re.search(r'parte\s+correspondente\s+a\s*(\d+(?:,\d+)?)%', texto, re.IGNORECASE)
    if m3: return float(m3.group(1).replace(',', '.'))
        
    if re.search(r'(totalidade|integralidade|100%|o imóvel constante|o imóvel objeto)', texto, re.IGNORECASE):
        return 100.0
        
    return 100.0

def extrair_bloco(texto, tipo):
    if tipo == "ADQUIRENTE":
        m = re.search(r'\bvendeu\s+.*?\bpara\s+(.*?)(?=\bpelo valor\b|\bpelo preÃ§o\b|;|\.\s*Dou|\.\s*O referido|\Z)', texto, re.I | re.DOTALL)
        if m: return m.group(1).strip().rstrip(';, ')

        m = re.search(r'\badjudicante\s*:\s*(.*?)(?=\*NOTA|;|\.\s*Dou|\.\s*DOU|\Z)', texto, re.I | re.DOTALL)
        if m: return m.group(1).strip().rstrip(';, ')

        m = re.search(r';\s*(.*?)(?=,?\s*adquiriu\s+por\s+compra\b)', texto, re.I | re.DOTALL)
        if m and m.group(1).strip().rstrip(';, '): return m.group(1).strip().rstrip(';, ')

        m = re.search(r'lavrada\b.*?,\s*(.*?)(?=;\s*adquiriu\s+por\s+compra\b)', texto, re.I | re.DOTALL)
        if m:
            t = m.group(1).strip().rstrip(';, ')
            t = re.sub(r'^.*\bfls?\.\s*[\w\-\/]+,\s*', '', t, flags=re.I | re.DOTALL)
            return t

        m = re.search(r'OUTORGADO[S]?\s*:(.*?)(?=\bIM[ÓO]VEL\s*:|\bORIGEM\s*:|\bFORMA DO T[ÍI]TULO\b)', texto, re.I | re.DOTALL)
        if m: return m.group(1).strip().rstrip(';, ')

        m = re.search(r'ADQUIRENTE[S]?\s*:(.*?)(?=\bIM[ÓO]VEL\s*:|\bORIGEM\s*:|\bFORMA DO TÍTULO\b)', texto, re.I | re.DOTALL)
        if m: return m.group(1).strip().rstrip(';, ')

        m = re.search(r'DONAT[AÁ]RIO[S]?\s*:(.*?)(?=\bIM[ÓOÃ“]VEL\s*:|\bOBJETO\s*:|\bORIGEM\s*:|\bFORMA DO T[ÍI]TULO\b)', texto, re.I | re.DOTALL)
        if m: return m.group(1).strip().rstrip(';, ')

        m = re.search(r'adquirido\s+(?:por|pel[oa])\s*:?\s*(.*?)(?=\bpor compra\b|\bpelo preço\b|\bem pagamento\b|\bpor doação\b)', texto, re.I | re.DOTALL)
        if m: return m.group(1).strip().rstrip(';, ')

        m = re.search(r'coube\s+(?:a|ao|aos|à|às)\s+(.*?)(?=\bem pagamento\b|\ba totalidade\b|\bpor aquisi[çc][ãa]o\b|\bconforme\b)', texto, re.I | re.DOTALL)
        if m:
            t = m.group(1).strip().rstrip(';, ')
            t = re.sub(
                r'^(?:o\s+|a\s+|os\s+|as\s+)?'
                r'(?:(?:únic[oa]s?|herdeir[oa]s?|cessionári[oa]s?|filh[oa]s?|viúv[oa]s?)\s+)*'
                r'(?:e\s+cessionári[oa]s?\s+)?[:\-]?\s*',
                '',
                t,
                flags=re.I
            ).strip()
            return t

    elif tipo == "TRANSMITENTE":
        m = re.search(r'por compra feita a[os]?\s+(.*?)(?=\bpelo valor\b|;|\.|\Z)', texto, re.I | re.DOTALL)
        if m: return m.group(1).strip().rstrip(';, ')

        m = re.search(r'OUTORGANTE[S]?\s*:(.*?)(?=\bOUTORGADO[S]?\s*:|\bIM[ÓO]VEL\s*:)', texto, re.I | re.DOTALL)
        if m: return m.group(1).strip().rstrip(';, ')

        m = re.search(r'TRANSMITENTE[S]?\s*:(.*?)(?=\bADQUIRENTE[S]?\s*:|\bIM[ÓO]VEL\s*:)', texto, re.I | re.DOTALL)
        if m: return m.group(1).strip().rstrip(';, ')

        m = re.search(r'DOADOR(?:A|ES|AS)?\s*:(.*?)(?=\bINTERVENIENTE\s*:|\bDONAT[AÁ]RIO[S]?\s*:|\bOBJETO\s*:|\bIM[ÓOÃ“]VEL\s*:)', texto, re.I | re.DOTALL)
        if m: return m.group(1).strip().rstrip(';, ')

        m = re.search(r'por compra feita a[os]?\s+(.*?)(?=\bpelo preço\b|\bpelo valor\b|;|\.\s*O referido)', texto, re.I | re.DOTALL)
        if m: return m.group(1).strip().rstrip(';, ')
        
        m = re.search(r'por doação que lhes fizeram\s+(.*?)(?=\bno valor\b|\bpelo valor\b|\bsem condições\b|;|\.\s*O referido)', texto, re.I | re.DOTALL)
        if m: return m.group(1).strip().rstrip(';, ')

        m = re.search(r'deixados por falecimento\s+(?:de\s+)?(.*?)(?=,|\s+julgado|;)', texto, re.I | re.DOTALL)
        if m: return m.group(1).strip().rstrip(';, ')

    return ""

def extrair_pessoas(texto_bloco):
    pessoas = []
    if not texto_bloco: return pessoas

    conjuge_casamento = re.search(
        r'\bcasad[oa]\s+sob\s+o\s+regime\b.*?\bcom\s+'
        r'([A-ZÁÀÂÃÉÈÊÍÌÎÓÒÔÕÚÙÛÇ][^,]+?)\s*,'
        r'.*?(?:CPF|CIC|CNPJ|CGC|MF)[^\d]*([\d\.\-\/]{9,20})',
        texto_bloco,
        re.I | re.DOTALL
    )

    # Em atos com casal, cada cônjuge pode ter nome e CPF próprios no mesmo bloco.
    # Se não separarmos aqui, a limpeza abaixo remove o segundo cônjuge inteiro.
    partes_conjuges = re.split(
        r'\s+e\s+(?:seu|sua)\s+(?:c[oô]njuge|mulher|marido|esposa)\s+',
        texto_bloco,
        flags=re.I
    )

    if len(partes_conjuges) > 1:
        partes = [p.strip() for p in partes_conjuges if p.strip()]
    else:
        partes = re.split(r'(?:^|\s+|;)\s*(?:\d{1,3}|[IVX]+)\)\-?\s*', texto_bloco)
        partes = [p.strip() for p in partes if p.strip()]
        partes = [re.sub(r'\s+e\s+d[oa]\s+CPF', ' CPF', p, flags=re.I) for p in partes]
        partes_sem_ponto_virgula = []

        if len(partes) == 1:
            partes_sem_ponto_virgula = re.split(
                r';\s*(?:e\s*,?\s*)?(?=[A-ZÁÀÂÃÉÈÊÍÌÎÓÒÔÕÚÙÛÇ][A-ZÁÀÂÃÉÈÊÍÌÎÓÒÔÕÚÙÛÇa-záàâãéèêíìîóòôõúùûç]+(?:\s+[A-ZÁÀÂÃÉÈÊÍÌÎÓÒÔÕÚÙÛÇ][A-ZÁÀÂÃÉÈÊÍÌÎÓÒÔÕÚÙÛÇa-záàâãéèêíìîóòôõúùûç]+){1,})',
                partes[0],
            )
        if len(partes_sem_ponto_virgula) > 1:
            partes = [p.strip() for p in partes_sem_ponto_virgula if p.strip()]
        elif re.search(r'\s+e\s+[A-ZÃÃ€Ã‚ÃƒÃ‰ÃˆÃŠÃÃŒÃŽÃ“Ã’Ã”Ã•ÃšÃ™Ã›Ã‡][^,]+,\s*brasileir[oa]', partes[0], re.I):
            partes_por_e = re.split(
                r'\s+e\s+(?=[A-ZÃÃ€Ã‚ÃƒÃ‰ÃˆÃŠÃÃŒÃŽÃ“Ã’Ã”Ã•ÃšÃ™Ã›Ã‡][^,]+,\s*brasileir[oa])',
                partes[0],
                flags=re.I
            )
            if len(partes_por_e) > 1:
                partes = [p.strip() for p in partes_por_e if p.strip()]
    
    if not partes:
        sub_partes = re.split(r';\s*', texto_bloco)
        if len(sub_partes) > 1:
            partes = [p.strip() for p in sub_partes if len(p.strip()) > 10]
        else:
            partes = [texto_bloco]

    for parte in partes:
        parte = re.sub(r'^\s*(?:meeir[oa]|vi[Ãºu]v[oa])\s*,\s*', '', parte, flags=re.I)
        nome_match = re.match(r'^([^,]+)', parte)
        
        # MEGA BRAIN: Agora aceita CNPJ, CGC e a barra "/" na leitura!
        cpf_match = re.search(r'(?:CPF|CIC|CNPJ|CGC|MF)[^\d]*([\d\.\-\/]{9,20})', parte, re.I)
        percentual_match = re.search(r'equivalente\s+a\s*(\d+(?:,\d+)?)%', parte, re.I)
        percentual = float(percentual_match.group(1).replace(',', '.')) if percentual_match else None

        nome = nome_match.group(1).strip() if nome_match else "DESCONHECIDO"
        nome = re.sub(r'^(?:Dr\.?|Dra\.?|Doutor(?:a)?)\s+', '', nome, flags=re.I)
        cpf = cpf_match.group(1).strip().rstrip('.,;') if cpf_match else "CPF/CNPJ NÃO INFORMADO"

        # Limpeza visual (remove estado civil e termo "pessoa jurídica")
        nome = re.sub(r'\s+e\s+(?:seu\s+c[oô]njuge|sua\s+mulher|seu\s+marido|sua\s+esposa).*', '', nome, flags=re.I)
        nome = re.sub(r'^(?:(?:meeir[oa]|vi[Ãºu]v[oa]|herdeir[oa]\s+filh[oa]|herdeir[oa])\s+)+', '', nome, flags=re.I)
        nome = re.sub(r'\s*,?\s*casad[oa].*', '', nome, flags=re.I)
        nome = re.sub(r'\s*,?\s*pessoa jur[íi]dica.*', '', nome, flags=re.I)
        nome = re.sub(r'\s+', ' ', nome)
        nome = nome.strip(' ,.')
        
        pessoa = {"nome": nome, "cpf": cpf}
        if percentual is not None:
            pessoa["percentual"] = percentual
        pessoas.append(pessoa)

    if conjuge_casamento and len(pessoas) > 1:
        nome_conjuge = re.sub(r'\s+', ' ', conjuge_casamento.group(1)).strip(' ,.')
        cpf_conjuge = conjuge_casamento.group(2).strip().rstrip('.,;')
        for pessoa in pessoas:
            if padronizar_chave(pessoa["cpf"], pessoa["nome"]) == padronizar_chave(cpf_conjuge, nome_conjuge):
                pessoa["nome"] = nome_conjuge
                pessoa["cpf"] = cpf_conjuge
                break

    return pessoas

def extrair_proprietario_inicial(texto_cabecalho):
    m = re.search(r'PROPRIET[AÁ]RI[OA]S?\s*:\s*(.*?)(?=\bORIGEM\b|\bT[IÍ]TULO AQUISITIVO\b|\bREGISTRO ANTERIOR\b|\bO referido [ée] verdade\b|\*NOTA\b|\bProtocolo\b|\bMATR[IÍ]CULA\b)', texto_cabecalho, re.I | re.DOTALL)
    if m:
        proprietarios = extrair_pessoas(m.group(1).strip())
        cabecalho_limpo = limpar_nome(texto_cabecalho)
        bloco_limpo = limpar_nome(m.group(1))
        proprietario_singular = (
            re.search(r'PROPRIETARI[OA]\s*:', cabecalho_limpo)
            and not re.search(r'PROPRIETARI[OA]S\s*:', cabecalho_limpo)
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
    return len(nome_a) > 5 and len(nome_b) > 5 and (nome_a in nome_b or nome_b in nome_a)

def chave_para_incluir(pessoa, estado):
    chave = padronizar_chave(pessoa["cpf"], pessoa["nome"])
    if chave in estado and not nomes_compativeis(estado[chave]["nome"], pessoa["nome"]):
        return limpar_nome(pessoa["nome"])
    return chave

def encontrar_chave_no_estado(pessoa, estado):
    chave_pessoa = padronizar_chave(pessoa["cpf"], pessoa["nome"])
    nome_pessoa = pessoa["nome"]

    if chave_pessoa in estado and nomes_compativeis(estado[chave_pessoa]["nome"], nome_pessoa):
        return chave_pessoa

    for chave_estado, dados_estado in estado.items():
        if nomes_compativeis(dados_estado["nome"], nome_pessoa):
            return chave_estado

    return None

def calcular_cadeia_dominial(atos, texto_integral=""):
    estado = {}
    
    if texto_integral:
        partes = re.split(r'(?:R|AV)[\.\-]\s*0*1\b', texto_integral, maxsplit=1, flags=re.I)
        cabecalho = partes[0]
        
        iniciais = extrair_proprietario_inicial(cabecalho)
        if iniciais:
            fração = 100.0 / len(iniciais)
            for p in iniciais:
                chave = padronizar_chave(p["cpf"], p["nome"])
                estado[chave] = {"nome": p["nome"], "cpf_original": p["cpf"], "proporcao": fração}

    atos_transmissao = [
        "VENDA E COMPRA", "COMPRA E VENDA", "INVENTÁRIO", "PARTILHA",
        "SOBREPARTILHA", "DOAÇÃO", "REFORMA AGRÁRIA", "TÍTULO DE DOMÍNIO",
    ]
    
    for ato in atos:
        indicados = extrair_indicacao_titularidade(ato.descricao)
        if indicados:
            estado.clear()
            for indicado in indicados:
                chave = chave_para_incluir(indicado, estado)
                estado[chave] = {
                    "nome": indicado["nome"],
                    "cpf_original": indicado["cpf"],
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

        if not any(x in ato.descricao.upper() for x in atos_transmissao) and "ADJUDICA" not in ato.descricao.upper():
            continue
        
        percentual_ato = parse_percent(ato.descricao)
        
        bloco_adq = extrair_bloco(ato.descricao, "ADQUIRENTE")
        bloco_transm = extrair_bloco(ato.descricao, "TRANSMITENTE")
        
        adquirentes = extrair_pessoas(bloco_adq)
        transmitentes = extrair_pessoas(bloco_transm)
        
        if not adquirentes:
            continue
            
        percentuais_individuais = [a.get("percentual") for a in adquirentes]
        usar_percentual_individual = all(p is not None for p in percentuais_individuais)
        percent_por_adq = percentual_ato / len(adquirentes)
        descricao_limpa = limpar_nome(ato.descricao)
        partilha_meacao = (
            ("INVENTARIO" in descricao_limpa or "PARTILHA" in descricao_limpa)
            and ("MEACAO" in descricao_limpa or "MEEIR" in descricao_limpa)
        )
        houve_debito = False
        
        if percentual_ato >= 99.0:
            estado.clear()
        else:
            if transmitentes:
                chaves_debito = []
                for t in transmitentes:
                    chave_encontrada = encontrar_chave_no_estado(t, estado)
                    if chave_encontrada and chave_encontrada not in chaves_debito:
                        chaves_debito.append(chave_encontrada)

                if chaves_debito:
                    percent_por_transm = percentual_ato / len(chaves_debito)
                    for chave_estado in chaves_debito:
                        if chave_estado not in estado:
                            continue
                        estado[chave_estado]["proporcao"] -= percent_por_transm
                        estado[chave_estado].pop("proporcao_texto", None)
                        if estado[chave_estado]["proporcao"] < 0.01:
                            del estado[chave_estado]
                        houve_debito = True
        
        for a in adquirentes:
            chave_a = chave_para_incluir(a, estado)
            proporcao_adquirida = a["percentual"] if usar_percentual_individual else percent_por_adq
            if partilha_meacao and not houve_debito and chave_a in estado:
                estado[chave_a]["nome"] = a["nome"]
                estado[chave_a]["cpf_original"] = a["cpf"]
                estado[chave_a]["proporcao"] = proporcao_adquirida
                estado[chave_a].pop("proporcao_texto", None)
                continue
            if chave_a not in estado:
                estado[chave_a] = {"nome": a["nome"], "cpf_original": a["cpf"], "proporcao": 0.0}
            estado[chave_a]["proporcao"] += proporcao_adquirida
            estado[chave_a].pop("proporcao_texto", None)
            
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
