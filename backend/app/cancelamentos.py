import re
import unicodedata


REFERENCIA_ATO = re.compile(
    r"\b(R|AV)\s*[.\-,]*\s*(\d+)(?!\d|\.\d)"
    r"(?:\s*-\s*(\d{1,10}))?",
    re.IGNORECASE,
)
CATEGORIAS_CANCELAVEIS = {"ÔNUS", "PUBLICIDADE"}
TIPOS_CANCELAVEIS = (
    ("ALIENACAO FIDUCIARIA", "ALIENACAO FIDUCIARIA"),
    ("HIPOTECA", "HIPOTECA"),
    ("USUFRUTO", "USUFRUTO"),
    ("PENHORA", "PENHORA"),
    ("PENHOR", "PENHOR"),
    ("INDISPONIBILIDADE", "INDISPONIBILIDADE"),
    ("SERVIDAO", "SERVIDAO"),
    ("CAUCAO", "CAUCAO"),
)


def _sem_acentos(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii").upper()


def _codigo_normalizado(tipo: str, numero: str) -> str:
    return f"{tipo.upper()}.{int(numero)}"


def _codigo_exibicao(tipo: str, numero: str) -> str:
    return f"{tipo.upper()}.{int(numero):02d}"


def _codigo_ato_exibicao(codigo: str) -> str:
    match = re.search(r"\b(R|AV)\s*[.\-,]*\s*0*(\d+)", codigo, re.IGNORECASE)
    return _codigo_exibicao(match.group(1), match.group(2)) if match else codigo


def _registrar_alvo_cancelado(ato_cancelamento, codigo: str) -> None:
    if not hasattr(ato_cancelamento, "cancela_atos"):
        ato_cancelamento.cancela_atos = []
    if codigo not in ato_cancelamento.cancela_atos:
        ato_cancelamento.cancela_atos.append(codigo)


def _numero_matricula(atos) -> str | None:
    for ato in atos:
        cabecalho = ato.descricao[:100]
        encontrado = re.match(
            r"\s*(?:R|AV)\s*[.\-]?\s*\d+\s*-\s*([\d.]+)",
            cabecalho,
            re.IGNORECASE,
        )
        if encontrado:
            return str(int(encontrado.group(1).replace(".", "")))
    return None


def _referencias(texto: str, matricula: str | None) -> list[str]:
    referencias = []
    ocorrencias = list(REFERENCIA_ATO.finditer(texto))
    for referencia in ocorrencias:
        sufixo = referencia.group(3)
        if sufixo and matricula and str(int(sufixo)) != matricula:
            continue
        codigo = _codigo_normalizado(referencia.group(1), referencia.group(2))
        if codigo not in referencias:
            referencias.append(codigo)

    # Redações antigas omitem o segundo "R": "os R-26 e 29-27". O
    # sufixo da matrícula permite recuperar apenas o registro local, sem
    # confundir atos pertencentes a outra matrícula.
    if matricula:
        for referencia in ocorrencias:
            if referencia.group(1).upper() != "R":
                continue
            trecho = texto[referencia.end():referencia.end() + 120]
            for abreviada in re.finditer(r"(?:,|;|\be\b)\s*0*(\d+)\s*-\s*(\d{1,10})\b", trecho, re.IGNORECASE):
                if str(int(abreviada.group(2))) == matricula:
                    codigo = _codigo_normalizado("R", abreviada.group(1))
                    if codigo not in referencias:
                        referencias.append(codigo)
    return referencias


def _e_cancelavel(ato) -> bool:
    return ato.categoria in CATEGORIAS_CANCELAVEIS


def _cancelar(alvo, cancelamento) -> None:
    if alvo.status == "ATIVO":
        alvo.status = "CANCELADO"
        alvo.cancelado_por = cancelamento.codigo
        alvo.impacta_resultado = False
    _registrar_alvo_cancelado(cancelamento, _codigo_ato_exibicao(alvo.codigo))


def _tipo_cancelado(texto_normalizado: str) -> str | None:
    for marcador, tipo in TIPOS_CANCELAVEIS:
        if marcador in texto_normalizado:
            return tipo
    return None


def _ato_do_tipo(ato, tipo: str) -> bool:
    return tipo in _sem_acentos(ato.descricao)


def _registros_legados(texto: str) -> set[str]:
    normalizado = _sem_acentos(texto)
    encontrados = set()
    for trecho in re.finditer(
        r"(?:INSCRIT[AO]S?|REGISTRAD[AO]S?)\s+SOB\s+(?:OS?\s+)?"
        r"N[^0-9]{0,8}([^;]{0,220}?)(?=\bFLS?\b|\bLIVRO\b|$)",
        normalizado,
    ):
        for numero in re.findall(r"(?<!\d)(\d{1,3}\.\d{3})(?!\d)", trecho.group(1)):
            encontrados.add(numero.replace(".", ""))
    return encontrados


def _registro_legado_mencionado(numero: str, texto: str) -> bool:
    padrao = r"(?<!\d)" + r"[.\s]?".join(map(re.escape, numero)) + r"(?!\d)"
    return bool(re.search(padrao, texto))


def aplicar_cancelamentos(atos):
    indice = {}
    matricula = _numero_matricula(atos)
    legados_por_codigo = {}
    legados_cancelados = {}

    for posicao, ato in enumerate(atos):
        match = re.search(r"\b(R|AV)\s*[.\-,]*\s*0*(\d+)", ato.codigo, re.IGNORECASE)
        if match:
            codigo = _codigo_normalizado(match.group(1), match.group(2))
            indice[codigo] = (posicao, ato)
            if _e_cancelavel(ato):
                registros = _registros_legados(ato.descricao)
                if registros:
                    legados_por_codigo[codigo] = registros
                    legados_cancelados[codigo] = set()

    for posicao, ato in enumerate(atos):
        texto_normalizado = _sem_acentos(ato.descricao)
        tem_cancelamento_expresso = (
            ato.categoria == "CANCELAMENTO"
            or "CANCELAD" in texto_normalizado
            or "CANCELAMENT" in texto_normalizado
        )
        if not tem_cancelamento_expresso:
            continue

        def cancelar_com_vinculados(alvo) -> None:
            _cancelar(alvo, ato)
            titulo_alvo = _sem_acentos(alvo.descricao)[:320]
            if not any(expressao in titulo_alvo for expressao in (
                "ASSUNCAO DE DIVIDA",
                "ASSUNCAO DE DIVIDAS",
                "CONFISSAO E ASSUNCAO",
            )):
                return
            for referencia_anterior in _referencias(alvo.descricao, matricula):
                vinculado = indice.get(referencia_anterior)
                if vinculado and vinculado[0] < posicao and _e_cancelavel(vinculado[1]):
                    _cancelar(vinculado[1], ato)

        def cancelar_referencia(codigo_alvo: str, alvo) -> None:
            registros = legados_por_codigo.get(codigo_alvo)
            if registros:
                mencionados = {
                    numero for numero in registros
                    if _registro_legado_mencionado(numero, texto_normalizado)
                }
                if mencionados:
                    legados_cancelados[codigo_alvo].update(mencionados)
                    _registrar_alvo_cancelado(ato, _codigo_ato_exibicao(alvo.codigo))
                    if legados_cancelados[codigo_alvo] != registros:
                        return
            cancelar_com_vinculados(alvo)

        cancelou_alvo_explicito = False
        for codigo_legado, registros in legados_por_codigo.items():
            posicao_legado, alvo_legado = indice[codigo_legado]
            if posicao_legado >= posicao:
                continue
            mencionados = {
                numero for numero in registros
                if _registro_legado_mencionado(numero, texto_normalizado)
            }
            if not mencionados:
                continue
            legados_cancelados[codigo_legado].update(mencionados)
            _registrar_alvo_cancelado(ato, _codigo_ato_exibicao(alvo_legado.codigo))
            if legados_cancelados[codigo_legado] == registros:
                cancelar_com_vinculados(alvo_legado)
            cancelou_alvo_explicito = True

        for chave_buscada in _referencias(ato.descricao, matricula):
            encontrado = indice.get(chave_buscada)
            if encontrado and encontrado[0] < posicao and _e_cancelavel(encontrado[1]):
                cancelar_referencia(chave_buscada, encontrado[1])
                cancelou_alvo_explicito = True
                continue

            # A inversão R/AV só é tolerada quando encontra um ato anterior
            # materialmente cancelável. Nunca se cancela outra averbação de
            # cancelamento por causa de um erro de digitação no texto.
            tipo, numero = chave_buscada.split(".", 1)
            chave_inversa = _codigo_normalizado("AV" if tipo == "R" else "R", numero)
            inverso = indice.get(chave_inversa)
            if inverso and inverso[0] < posicao and _e_cancelavel(inverso[1]):
                cancelar_referencia(chave_inversa, inverso[1])
                cancelou_alvo_explicito = True

        # Quando a referência foi digitada errada ou omitida, o próprio
        # título do cancelamento identifica o ônus anterior correspondente.
        if not cancelou_alvo_explicito:
            tipo_cancelado = _tipo_cancelado(texto_normalizado)
            if tipo_cancelado:
                candidatos = [
                    anterior for anterior in atos[:posicao]
                    if _e_cancelavel(anterior) and _ato_do_tipo(anterior, tipo_cancelado)
                ]
                ativos = [anterior for anterior in candidatos if anterior.status == "ATIVO"]
                if ativos or candidatos:
                    cancelar_com_vinculados((ativos or candidatos)[-1])
                    cancelou_alvo_explicito = True

        # Nos leilões fiduciários negativos, a matrícula pode declarar a
        # extinção da dívida sem repetir o número do registro da garantia.
        if (
            not cancelou_alvo_explicito
            and "LEIL" in texto_normalizado
            and "NEGATIV" in texto_normalizado
            and "DIVIDA ORIGINARIA" in texto_normalizado
            and "EXTINT" in texto_normalizado
        ):
            for ato_anterior in reversed(atos[:posicao]):
                if (
                    ato_anterior.status == "ATIVO"
                    and "ALIENACAO FIDUCIARIA" in _sem_acentos(ato_anterior.descricao)
                    and ato_anterior.categoria == "ÔNUS"
                ):
                    cancelar_com_vinculados(ato_anterior)
                    break

    return atos
