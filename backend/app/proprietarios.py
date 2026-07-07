import re
import unicodedata

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

def parse_percent(texto):
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
        m = re.search(r'OUTORGADO[S]?\s*:(.*?)(?=\bIM[ÓO]VEL\s*:|\bORIGEM\s*:|\bFORMA DO T[ÍI]TULO\b)', texto, re.I | re.DOTALL)
        if m: return m.group(1).strip().rstrip(';, ')

        m = re.search(r'ADQUIRENTE[S]?\s*:(.*?)(?=\bIMÓVEL\s*:|\bORIGEM\s*:|\bFORMA DO TÍTULO\b)', texto, re.I | re.DOTALL)
        if m: return m.group(1).strip().rstrip(';, ')

        m = re.search(r'DONAT[AÁ]RIO[S]?\s*:(.*?)(?=\bIM[ÓOÃ“]VEL\s*:|\bOBJETO\s*:|\bORIGEM\s*:|\bFORMA DO T[ÍI]TULO\b)', texto, re.I | re.DOTALL)
        if m: return m.group(1).strip().rstrip(';, ')

        m = re.search(r'adquirido por\s*:?\s*(.*?)(?=\bpor compra\b|\bpelo preço\b|\bem pagamento\b|\bpor doação\b)', texto, re.I | re.DOTALL)
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
        m = re.search(r'OUTORGANTE[S]?\s*:(.*?)(?=\bOUTORGADO[S]?\s*:|\bIM[ÓO]VEL\s*:)', texto, re.I | re.DOTALL)
        if m: return m.group(1).strip().rstrip(';, ')

        m = re.search(r'TRANSMITENTE[S]?\s*:(.*?)(?=\bADQUIRENTE[S]?\s*:|\bIMÓVEL\s*:)', texto, re.I | re.DOTALL)
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
        partes = re.split(r'(?:^|\s+|;)\s*(?:\d{1,3}|[IVX]+)\)\-?\s+', texto_bloco)
        partes = [p.strip() for p in partes if p.strip()]

        if len(partes) == 1:
            partes_sem_ponto_virgula = re.split(
                r';\s*(?:e\s*,?\s*)?(?=[A-ZÁÀÂÃÉÈÊÍÌÎÓÒÔÕÚÙÛÇ][A-ZÁÀÂÃÉÈÊÍÌÎÓÒÔÕÚÙÛÇa-záàâãéèêíìîóòôõúùûç]+(?:\s+[A-ZÁÀÂÃÉÈÊÍÌÎÓÒÔÕÚÙÛÇ][A-ZÁÀÂÃÉÈÊÍÌÎÓÒÔÕÚÙÛÇa-záàâãéèêíìîóòôõúùûç]+){1,})',
                partes[0],
            )
            if len(partes_sem_ponto_virgula) > 1:
                partes = [p.strip() for p in partes_sem_ponto_virgula if p.strip()]
    
    if not partes:
        sub_partes = re.split(r';\s*', texto_bloco)
        if len(sub_partes) > 1:
            partes = [p.strip() for p in sub_partes if len(p.strip()) > 10]
        else:
            partes = [texto_bloco]

    for parte in partes:
        nome_match = re.match(r'^([^,]+)', parte)
        
        # MEGA BRAIN: Agora aceita CNPJ, CGC e a barra "/" na leitura!
        cpf_match = re.search(r'(?:CPF|CIC|CNPJ|CGC|MF)[^\d]*([\d\.\-\/]{9,20})', parte, re.I)
        percentual_match = re.search(r'equivalente\s+a\s*(\d+(?:,\d+)?)%', parte, re.I)
        percentual = float(percentual_match.group(1).replace(',', '.')) if percentual_match else None

        nome = nome_match.group(1).strip() if nome_match else "DESCONHECIDO"
        cpf = cpf_match.group(1).strip().rstrip('.,;') if cpf_match else "CPF/CNPJ NÃO INFORMADO"

        # Limpeza visual (remove estado civil e termo "pessoa jurídica")
        nome = re.sub(r'\s+e\s+(?:seu\s+c[oô]njuge|sua\s+mulher|seu\s+marido|sua\s+esposa).*', '', nome, flags=re.I)
        nome = re.sub(r'\s*,?\s*casad[oa].*', '', nome, flags=re.I)
        nome = re.sub(r'\s*,?\s*pessoa jur[íi]dica.*', '', nome, flags=re.I)
        nome = re.sub(r'\s+', ' ', nome)
        nome = nome.strip(' ,.')
        
        pessoa = {"nome": nome, "cpf": cpf}
        if percentual is not None:
            pessoa["percentual"] = percentual
        pessoas.append(pessoa)

    return pessoas

def extrair_proprietario_inicial(texto_cabecalho):
    m = re.search(r'PROPRIET[AÁ]RI[OA]S?\s*:\s*(.*?)(?=\bORIGEM\b|\bT[IÍ]TULO AQUISITIVO\b|\bREGISTRO ANTERIOR\b|\bO referido [ée] verdade\b|\*NOTA\b|\bProtocolo\b|\bMATR[IÍ]CULA\b)', texto_cabecalho, re.I | re.DOTALL)
    if m:
        return extrair_pessoas(m.group(1).strip())
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

        if not any(x in ato.descricao.upper() for x in atos_transmissao):
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
        
        if percentual_ato >= 99.0:
            estado.clear()
        else:
            if transmitentes:
                percent_por_transm = percentual_ato / len(transmitentes)
                for t in transmitentes:
                    chave_t = padronizar_chave(t["cpf"], t["nome"])
                    nome_t_limpo = limpar_nome(t["nome"])
                    
                    debitou = False
                    
                    for chave_estado in list(estado.keys()):
                        if chave_t == chave_estado:
                            estado[chave_estado]["proporcao"] -= percent_por_transm
                            if estado[chave_estado]["proporcao"] < 0.01:
                                del estado[chave_estado]
                            debitou = True
                            break
                            
                    if not debitou:
                        for chave_estado, dados_estado in list(estado.items()):
                            nome_estado_limpo = limpar_nome(dados_estado["nome"])
                            
                            match = False
                            if chave_estado in chave_t or chave_t in chave_estado:
                                match = True
                            elif len(nome_estado_limpo) > 5 and len(nome_t_limpo) > 5:
                                if nome_estado_limpo in nome_t_limpo or nome_t_limpo in nome_estado_limpo:
                                    match = True
                                    
                            if match:
                                estado[chave_estado]["proporcao"] -= percent_por_transm
                                if estado[chave_estado]["proporcao"] < 0.01:
                                    del estado[chave_estado]
                                debitou = True
                                break
        
        for a in adquirentes:
            chave_a = padronizar_chave(a["cpf"], a["nome"])
            if chave_a not in estado:
                estado[chave_a] = {"nome": a["nome"], "cpf_original": a["cpf"], "proporcao": 0.0}
            estado[chave_a]["proporcao"] += a["percentual"] if usar_percentual_individual else percent_por_adq
            
    resultado = []
    for chave, dados in estado.items():
        if dados["proporcao"] > 0.01:
            prop_formatada = f"{dados['proporcao']:.2f}%".replace('.', ',')
            if prop_formatada.endswith(",00%"):
                prop_formatada = prop_formatada.replace(",00%", "%")
                
            resultado.append({
                "nome": dados["nome"],
                "cpf": dados["cpf_original"],
                "proporcao": prop_formatada
            })
            
    return resultado
