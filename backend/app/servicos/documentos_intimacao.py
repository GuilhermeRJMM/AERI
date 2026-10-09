"""Leitura temporária dos PDFs de origem usados na preparação de intimações.

Os documentos e seus dados pessoais permanecem em memória durante a requisição;
este módulo não grava conteúdo nem texto extraído no banco ou nos logs.
"""

from __future__ import annotations

import re
import html
import unicodedata
from datetime import date
from decimal import Decimal, InvalidOperation
from io import BytesIO

from pypdf import PdfReader
from backend.app.contratos_nucleo.extenso import reais


LIMITE_PDF_INTIMACAO = 8_000_000
LIMITE_PAGINAS_INTIMACAO = 30


class ErroDocumentoIntimacao(ValueError):
    pass


def _ler_pdf(conteudo: bytes, nome: str) -> str:
    if not conteudo.startswith(b"%PDF") or len(conteudo) > LIMITE_PDF_INTIMACAO:
        raise ErroDocumentoIntimacao(
            f"{nome}: selecione um PDF válido de até 8 MB."
        )
    try:
        leitor = PdfReader(BytesIO(conteudo), strict=True)
        if leitor.is_encrypted or len(leitor.pages) > LIMITE_PAGINAS_INTIMACAO:
            raise ErroDocumentoIntimacao(
                f"{nome}: PDF protegido ou com mais de 30 páginas."
            )
        texto = "\n".join(pagina.extract_text() or "" for pagina in leitor.pages)
    except ErroDocumentoIntimacao:
        raise
    except Exception:
        raise ErroDocumentoIntimacao(
            f"{nome}: não foi possível ler o texto do PDF."
        ) from None
    texto = texto.replace("\u00a0", " ").replace("\u200b", "")
    if len(texto.strip()) < 30:
        raise ErroDocumentoIntimacao(
            f"{nome}: o PDF parece ser imagem ou não contém texto legível."
        )
    return texto


def _digitos(valor: str | None) -> str:
    return re.sub(r"\D", "", valor or "")


def _nome_arquivo(valor: str) -> str:
    return re.sub(r"[\r\n\t]+", " ", valor).strip(" ,;.-")


def _nome_para_comparacao(valor: str) -> str:
    """Ignora apenas variações de acento, caixa e espaços na conferência do CPF."""
    sem_acentos = "".join(
        caractere
        for caractere in unicodedata.normalize("NFKD", valor)
        if not unicodedata.combining(caractere)
    )
    return re.sub(r"\s+", " ", sem_acentos).strip().casefold()


def _corrigir_indicador_numero(valor: str) -> str:
    # Alguns PDFs da Caixa mapeiam apenas o símbolo ordinal para U+FFFD.
    # Esta substituição é limitada a "n�" antes de algarismos, sem tentar
    # adivinhar letras faltantes em nomes próprios ou logradouros.
    return re.sub(r"\bn\ufffd\s*(?=\d)", "n.º ", valor, flags=re.IGNORECASE)


def _extrair_credor(texto: str) -> dict:
    linhas = texto.splitlines()
    for indice, linha in enumerate(linhas):
        if re.search(r"\bCNPJ\b", linha, re.IGNORECASE):
            documento = re.search(r"CNPJ\s*[:.]?\s*([\d./-]{14,20})", linha, re.IGNORECASE)
            if not documento:
                continue
            anterior = linha[:documento.start()].strip()
            anterior = re.sub(r"^\s*\d+\s*[.)-]?\s*", "", anterior)
            anterior = re.sub(r"[,;\s-]+$", "", anterior)
            if not anterior and indice:
                anterior = linhas[indice - 1].strip()
            nome = _nome_arquivo(anterior)
            if nome:
                return {"nome": nome, "cnpj": _digitos(documento.group(1))}
    return {"nome": "", "cnpj": ""}


def _extrair_devedores(texto: str) -> list[dict]:
    inicio = re.search(r"Fiduciante(?:\(s\)|s)?\s*:\s*", texto, re.IGNORECASE)
    if not inicio:
        return []
    fim = re.search(r"\n\s*Matr[ií]cula(?:\(s\)|s)?\s*:", texto[inicio.end():], re.IGNORECASE)
    bloco = texto[inicio.end():inicio.end() + fim.start()] if fim else texto[inicio.end():inicio.end() + 6000]
    encontrados = []
    padrao = re.compile(
        r"([A-ZÀ-ÖØ-Þ][A-ZÀ-ÖØ-Þ .'-]{2,100}?)\s*[-–—,]\s*(CPF|CNPJ)\s*[:.]?\s*([\d./-]{11,20})",
        re.IGNORECASE,
    )
    for correspondencia in padrao.finditer(bloco):
        nome = _nome_arquivo(correspondencia.group(1))
        tipo = correspondencia.group(2).lower()
        cpf = _digitos(correspondencia.group(3))
        if len(cpf) == (11 if tipo == "cpf" else 14) and nome:
            registro = {"nome": nome, tipo: cpf}
            if registro not in encontrados:
                encontrados.append(registro)
    return encontrados


def _extrair_cnpj_credor_rtd(texto: str) -> str:
    """Localiza CNPJ identificado como credor, sem confundi-lo com o do cartório."""
    candidatos = set()
    padrao = re.compile(
        r"(?m)^[ \t]*(?:\d{1,2}[.)][ \t]*)?[^\r\n]{3,120}?[ \t]*(?:[-–—]|\()[ \t]*CNPJ[ \t]*:?[ \t]*([\d./-]{14,20})"
    )
    for match in padrao.finditer(texto):
        cnpj = _digitos(match.group(1))
        if len(cnpj) != 14:
            continue
        contexto = texto[max(0, match.start() - 160):min(len(texto), match.end() + 550)]
        if re.search(r"\bcredor(?:a|\(a\))?\b|\brequer\b", contexto, re.IGNORECASE):
            candidatos.add(cnpj)
    return next(iter(candidatos)) if len(candidatos) == 1 else ""


def _extrair_matricula(texto: str) -> str:
    match = re.search(r"Matr[ií]cula(?:\(s\)|s)?\s*:\s*([^\r\n]+)", texto, re.IGNORECASE)
    if not match:
        return ""
    valor = match.group(1).strip()
    return re.split(r"\s{2,}|\s+Endere[cç]o\b", valor, maxsplit=1, flags=re.IGNORECASE)[0].strip(" ,;.")


def _extrair_contrato(texto: str) -> dict:
    match = re.search(
        r"Contrato\s*:\s*([^,\r\n]+),?\s*(?:firmado\s+em\s*:?\s*(\d{2}/\d{2}/\d{4}))?",
        texto,
        re.IGNORECASE,
    )
    return {"numero": match.group(1).strip() if match else "", "data": match.group(2) if match else ""}


def _extrair_enderecos(texto: str) -> list[str]:
    linhas = texto.splitlines()
    enderecos: list[str] = []
    # Preferimos o endereço explicitamente indicado para intimação na projeção.
    rotulos = re.compile(r"^\s*Endere[cç]o\s+de\s+Intima[cç][aã]o\s*:\s*(.*)$", re.IGNORECASE)
    for indice, linha in enumerate(linhas):
        rotulo = rotulos.match(linha)
        if not rotulo:
            continue
        valor = rotulo.group(1).strip()
        if not valor and indice + 1 < len(linhas):
            valor = linhas[indice + 1].strip()
        # Alguns PDFs quebram um endereço em várias linhas; paramos na próxima seção.
        if indice + 1 < len(linhas) and rotulo.group(1).strip():
            pass
        else:
            partes = [valor] if valor else []
            for proxima in linhas[indice + 2:indice + 7]:
                trecho = proxima.strip()
                if not trecho or re.match(r"^(?:Rela[cç][aã]o|Valor|Contrato|Devedores|Endere[cç]o)\b", trecho, re.IGNORECASE):
                    break
                partes.append(trecho)
            valor = " ".join(partes)
        valor = _corrigir_indicador_numero(re.sub(r"\s+", " ", valor)).strip(" ,;.")
        if valor and valor not in enderecos:
            enderecos.append(valor)
    if enderecos:
        return enderecos

    # Fallback: captura endereços rotulados no requerimento. Não coleta o endereço
    # do remetente nem tenta adivinhar a qual pessoa pertence cada endereço.
    for indice, linha in enumerate(linhas):
        match = re.match(r"^\s*Endere[cç]o\s*:\s*(.*)$", linha, re.IGNORECASE)
        if not match:
            continue
        valor = match.group(1).strip()
        if valor and valor not in enderecos:
            enderecos.append(_corrigir_indicador_numero(re.sub(r"\s+", " ", valor)).strip(" ,;."))
    # O requerimento também lista endereços sem rótulo entre os itens 3 e 3.1.
    # Só consideramos linhas iniciadas por logradouro depois da qualificação,
    # excluindo o cabeçalho do credor e as instruções das diligências.
    inicio = re.search(r"Fiduciante(?:\(s\)|s)?\s*:", texto, re.IGNORECASE)
    bloco = texto[inicio.end():] if inicio else ""
    bloco = re.split(r"\n\s*(?:3\.1|4\.)\s", bloco, maxsplit=1)[0]
    for match in re.finditer(
        r"(?m)^\s*(?:\d+[.)]\s*)?((?:Rua|Avenida|Av\.|Alameda|Praça|Estrada|Rodovia)\b[^\n]+)",
        bloco, re.IGNORECASE,
    ):
        valor = _corrigir_indicador_numero(re.sub(r"\s+", " ", match.group(1))).strip(" ,;.")
        if valor not in enderecos:
            enderecos.append(valor)
    return enderecos


def _extrair_endereco_imovel(texto: str) -> str:
    linhas = texto.splitlines()
    for indice, linha in enumerate(linhas):
        match = re.match(r"^\s*Endere[cç]o\s+do\s+im[oó]vel\s*:\s*(.*)$", linha, re.IGNORECASE)
        if not match:
            continue
        valor = match.group(1).strip()
        if not valor and indice + 1 < len(linhas):
            valor = linhas[indice + 1].strip()
        return _corrigir_indicador_numero(re.sub(r"\s+", " ", valor)).strip(" ,;.")
    return ""


def estruturar_endereco(endereco: str) -> dict:
    """Estrutura o endereço quando há separadores convencionais, sem inferir CEP."""
    bruto = re.sub(r"\s+", " ", endereco or "").strip()
    cep_match = re.search(r"\bCEP\s*:?\s*(\d{2})\.?\s*(\d{3})[-.]?(\d{3})\b", bruto, re.IGNORECASE)
    cep = "".join(cep_match.groups()) if cep_match else ""
    texto_sem_cep = (bruto[:cep_match.start()] if cep_match else bruto).strip(" ,")
    cidade_uf = re.search(r"[, ]+([^,]+?)\s*[/,-]\s*([A-Z]{2})\s*$", texto_sem_cep, re.IGNORECASE)
    cidade = cidade_uf.group(1).strip(" ,") if cidade_uf else ""
    uf = cidade_uf.group(2).upper() if cidade_uf else ""
    prefixo = texto_sem_cep[:cidade_uf.start()] if cidade_uf else texto_sem_cep
    prefixo = re.sub(r"\s+", " ", prefixo).strip(" ,")

    numero_match = re.search(r"(?:,\s*(?:n\s*[.º°]*\s*)?|\s+n\s*[.º°]*\s*)(\d{1,6}[A-Za-z]?(?:[-/][A-Za-z0-9]+)?)\b", prefixo, re.IGNORECASE)
    logradouro = prefixo[:numero_match.start()].strip(" ,") if numero_match else ""
    numero = numero_match.group(1) if numero_match else ""
    complemento = prefixo[numero_match.end():].strip(" ,") if numero_match else ""
    if not numero_match:
        partes_sem_numero = [parte.strip() for parte in prefixo.split(",") if parte.strip()]
        if partes_sem_numero:
            logradouro = partes_sem_numero[0]
            complemento = ", ".join(partes_sem_numero[1:])
    logradouro = re.sub(r",\s*", " ", logradouro)
    componentes = [parte.strip() for parte in complemento.split(",") if parte.strip()]
    bairro = componentes[-1] if componentes else ""
    if bairro:
        complemento = ", ".join(componentes[:-1])
    return {
        "original": bruto,
        "cep": cep,
        "logradouro": logradouro,
        "numero": numero,
        "complemento": complemento,
        "bairro": bairro,
        "cidade": cidade,
        "uf": uf,
        "revisaoObrigatoria": True,
    }


def extrair_dados_documento_rtd(conteudo: bytes, protocolo_in: str) -> dict:
    """Lê o PDF que será enviado ao RTD, sem armazená-lo ou escolher dados incertos."""
    texto = _ler_pdf(conteudo, "Documentos RTD.pdf")
    identificadores = {item.upper() for item in re.findall(r"\bIN\d{8}C\b", texto, re.IGNORECASE)}
    if identificadores and identificadores != {protocolo_in.upper()}:
        raise ErroDocumentoIntimacao("O PDF contém outro número de IN. Confira o arquivo selecionado.")

    cnpj_credor = _extrair_cnpj_credor_rtd(texto)
    devedores = _extrair_devedores(texto)
    texto_corrente = re.sub(r"\s+", " ", texto)
    padroes = (
        r"Ao\s+Ilmo\.?\s+Sr\.?\s+([A-ZÀ-ÖØ-Þ][A-ZÀ-ÖØ-Þ .'-]{2,100}?)\s*\(\s*CPF\s*:?\s*([\d.\-]{11,14})\s*\)",
        r"intima[cç][aã]o\s+pessoal\s+de\s+([A-ZÀ-ÖØ-Þ][A-ZÀ-ÖØ-Þ .'-]{2,100}?)\s*[-–—,]\s*CPF\s*:?\s*([\d.\-]{11,14})",
        r"FIDUCIANTE\(S\)\s*([A-ZÀ-ÖØ-Þ][A-ZÀ-ÖØ-Þ .'-]{2,100}?)\s+Nome\s+([\d.\-]{11,14})\s+CPF",
    )
    for padrao in padroes:
        for match in re.finditer(padrao, texto_corrente, re.IGNORECASE):
            pessoa = {"nome": _nome_arquivo(match.group(1)), "cpf": _digitos(match.group(2))}
            if len(pessoa["cpf"]) != 11 or not pessoa["nome"]:
                continue
            if any(
                item.get("cpf") == pessoa["cpf"]
                and _nome_para_comparacao(item.get("nome", "")) != _nome_para_comparacao(pessoa["nome"])
                for item in devedores
            ):
                raise ErroDocumentoIntimacao("O PDF apresenta nomes diferentes para o mesmo CPF. Confira manualmente.")
            if not any(item.get("cpf") == pessoa["cpf"] for item in devedores):
                devedores.append(pessoa)

    enderecos = []
    bloco = re.search(
        r"(?ims)^\s*Endere[cç]os?\s+para\s+notifica[cç][aã]o\s*:\s*\n(.*?)(?=^\s*(?:OBSERVA[CÇ][ÕO]ES|Documento Certificado|MANIFESTO DE ASSINATURAS)\s*:|\Z)",
        texto,
    )
    if bloco:
        for match in re.finditer(r"(?m)^\s*\d+[.)-]\s*([^\r\n]+)", bloco.group(1)):
            endereco = _corrigir_indicador_numero(match.group(1).strip())
            if endereco and endereco not in enderecos:
                enderecos.append(endereco)
    if not enderecos:
        bloco_credor = re.search(
            r"(?is)devedor\(es\)\s+fiduciante\(s\)\s+pode\(m\)\s+ser\s+encontrado\(s\)\s+nos\s+seguintes\s+endere[cç]os\s*:\s*(.*?)(?=\n\s*\d+\.\s|\Z)",
            texto,
        )
        if bloco_credor:
            for match in re.finditer(r"(?ms)^\s*[a-z]\)\s*(.*?)(?=^\s*[a-z]\)\s*|\Z)", bloco_credor.group(1)):
                endereco = re.sub(r"\s+", " ", match.group(1)).strip(" ,;.")
                if endereco and endereco not in enderecos:
                    enderecos.append(endereco)
    if not enderecos:
        enderecos = _extrair_enderecos(texto)

    if not devedores or not enderecos:
        raise ErroDocumentoIntimacao(
            "Não foi possível identificar com segurança devedores e endereços no PDF. Preencha-os manualmente ou use a leitura dos PDFs originais."
        )
    estruturados = [estruturar_endereco(item) for item in enderecos]
    for endereco in estruturados:
        # O ofício confeccionado pode omitir "S/N", embora o requerimento do
        # credor o informe. Só completamos quando o mesmo logradouro o traz.
        if endereco["numero"] or not endereco["logradouro"]:
            continue
        logradouro = re.escape(endereco["logradouro"])
        if re.search(rf"\b{logradouro}\s*[,\-]?\s*[-,]?\s*S\s*/\s*N\b", texto, re.IGNORECASE):
            endereco["numero"] = "S/N"
    avisos = []
    if not identificadores:
        avisos.append("O número do IN não apareceu no texto extraído. Confirme que este PDF pertence ao processo selecionado.")
    if not cnpj_credor:
        avisos.append("Não foi possível identificar com segurança um único CNPJ do credor. Confira e preencha esse campo manualmente.")
    if any(not all(endereco[campo] for campo in ("cep", "logradouro", "numero", "bairro", "cidade", "uf")) for endereco in estruturados):
        avisos.append("Alguns componentes de endereço não foram separados com segurança. Complete os campos vazios antes do envio.")
    avisos.append("Confira cada nome, CPF e endereço no PDF; a extração não substitui a revisão antes do envio.")
    return {"cnpjCredor": cnpj_credor, "devedores": devedores, "enderecos": estruturados, "avisos": avisos}


def _extrair_processo(texto: str) -> str:
    padroes = (
        r"Of[ií]cio\s+n[ºo°.]?\s*(\d{3,10})\s*/\s*(\d{4})",
        r"PROCESSO\s+n[ºo°.]?\s*(\d{3,10})\s*/\s*(\d{4})",
    )
    for padrao in padroes:
        match = re.search(padrao, texto, re.IGNORECASE)
        if match:
            return f"{match.group(1)}/{match.group(2)}"
    return ""


def _extrair_valor_projecao(texto: str, referencia: date) -> dict:
    linhas = re.findall(
        r"(?<!\d)(\d{2}/\d{2}/\d{4})\s+(?:R\$\s*)?([\d.]+,\d{2})(?!\d)",
        texto,
    )
    valores: dict[date, Decimal] = {}
    divergentes: set[date] = set()
    for data_br, valor_br in linhas:
        try:
            dia, mes, ano = map(int, data_br.split("/"))
            dia_projecao = date(ano, mes, dia)
            valor = Decimal(valor_br.replace(".", "").replace(",", "."))
        except (ValueError, InvalidOperation):
            continue
        if dia_projecao in valores and valores[dia_projecao] != valor:
            divergentes.add(dia_projecao)
        valores[dia_projecao] = valor
    valor = None if referencia in divergentes else valores.get(referencia)
    return {
        "data": referencia.strftime("%d/%m/%Y") if valor is not None else "",
        "valor": f"{valor:.2f}" if valor is not None else "",
        "extenso": reais(valor) if valor is not None else "",
        "exatoNaDataDeHoje": valor is not None,
        "divergenciaNaData": referencia in divergentes,
        "datasDisponiveis": len(valores),
    }


def analisar_pdfs_intimacao(
    oficio_pdf: bytes,
    projecao_pdf: bytes,
    referencia: date,
    protocolo_in: str,
    protocolo_tri7: str = "",
    titulo_registrado: bytes | None = None,
) -> dict:
    texto_oficio = _ler_pdf(oficio_pdf, "Ofício/requerimento")
    texto_projecao = _ler_pdf(projecao_pdf, "Planilha de projeção")
    credor = _extrair_credor(texto_oficio)
    devedores = _extrair_devedores(texto_oficio) or _extrair_devedores(texto_projecao)
    enderecos = _extrair_enderecos(texto_oficio) or _extrair_enderecos(texto_projecao)
    endereco_imovel = _extrair_endereco_imovel(texto_projecao) or _extrair_endereco_imovel(texto_oficio)
    processo = _extrair_processo(texto_oficio)
    matricula = _extrair_matricula(texto_oficio) or _extrair_matricula(texto_projecao)
    contrato = _extrair_contrato(texto_oficio)
    if not contrato["numero"]:
        contrato = _extrair_contrato(texto_projecao)
    valor = _extrair_valor_projecao(texto_projecao, referencia)

    avisos: list[str] = []
    if not credor["nome"] or len(credor["cnpj"]) != 14:
        avisos.append("Confira manualmente o nome e o CNPJ do credor; não foi possível confirmar ambos no ofício.")
    if not devedores:
        avisos.append("Não foi possível identificar devedores e CPFs. Cadastre-os manualmente antes de preparar os textos ou enviar ao RTD.")
    if not enderecos:
        avisos.append("Não foi possível identificar endereços de intimação. Cadastre-os manualmente.")
    if not endereco_imovel:
        avisos.append("Endereço do imóvel não identificado; confira na matrícula antes de preparar a convocação.")
    if not processo:
        avisos.append("Número do processo do credor não identificado; confira o documento.")
    if not matricula:
        avisos.append("Número da matrícula não identificado; confira o documento.")
    if not contrato["numero"] or not contrato["data"]:
        avisos.append("Número ou data do contrato incompletos; confira o documento.")
    if not valor["exatoNaDataDeHoje"] and not valor["divergenciaNaData"]:
        avisos.append("A planilha não contém valor para a data de hoje. Informe a data e o valor de projeção manualmente; nenhum valor futuro foi escolhido automaticamente.")
    if valor["divergenciaNaData"]:
        avisos.append("A planilha apresenta valores diferentes para a data de hoje. Confira o original e informe manualmente o valor correto.")
    if any("\ufffd" in campo for campo in [credor["nome"], endereco_imovel, *enderecos]):
        avisos.append("O PDF contém caracteres ilegíveis em nomes ou endereços. Corrija os campos usando o documento visual antes de preparar textos ou notificações.")
    estruturas = [estruturar_endereco(item) for item in enderecos]
    avisos.extend(
        f"Revise o endereço {indice}: os campos separados foram apenas sugeridos a partir do texto original."
        for indice, item in enumerate(estruturas, 1)
    )
    resultado = {
        "protocoloIN": protocolo_in,
        "protocoloTri7": protocolo_tri7,
        "dataGeracao": referencia.strftime("%d/%m/%Y"),
        "processoCredor": processo,
        "matricula": matricula,
        "credor": credor,
        "devedores": devedores,
        "contrato": contrato,
        "enderecos": enderecos,
        "enderecoImovel": endereco_imovel,
        "enderecosEstruturados": estruturas,
        "projecao": valor,
        "avisos": avisos,
    }
    if titulo_registrado:
        complementar_titulo_registrado(resultado, _ler_pdf(titulo_registrado, "Título registrado"))
    return resultado


def complementar_titulo_registrado(dados: dict, texto: str) -> None:
    match = re.search(r"Título protocolado em\s*(\d{2}/\d{2}/\d{4})\s*sob o n[.º°\s]*([\d.]+)", texto, re.IGNORECASE)
    if not match:
        return
    numero = _digitos(match.group(2))
    if dados.get("protocoloTri7") and _digitos(dados["protocoloTri7"]) != numero:
        raise ErroDocumentoIntimacao("O título registrado pertence a outro protocolo da Tri7.")
    processo_titulo = _extrair_processo(texto)
    contrato_titulo = _extrair_contrato(texto)["numero"]
    if (processo_titulo and processo_titulo != dados["processoCredor"]) or (
        contrato_titulo and contrato_titulo != dados["contrato"]["numero"]
    ):
        raise ErroDocumentoIntimacao("O título registrado não corresponde ao requerimento do credor.")
    dados["dataProtocolo"] = match.group(1)
    dados["protocoloTri7"] = numero


def complementar_matricula(dados: dict, texto: str) -> None:
    """Usa apenas o ato com o número de contrato correspondente, sem escolher o último R."""
    texto = html.unescape(re.sub(r"<[^>]+>", " ", texto))
    atos = re.split(r"(?=\bR[.\s-]*\d+\s*[-–./])", texto, flags=re.IGNORECASE)
    contrato = _digitos(dados["contrato"]["numero"])
    def mesmo_contrato(encontrado: str) -> bool:
        numero = _digitos(encontrado)
        # A matrícula pode acrescentar o dígito verificador final ao número
        # sem máscara informado no requerimento do credor.
        return numero == contrato or (len(contrato) >= 10 and len(numero) == len(contrato) + 1
            and numero.startswith(contrato))
    candidatos = [ato for ato in atos if contrato and any(
        mesmo_contrato(m.group()) for m in re.finditer(r"\d[\d. -]{8,}\d", ato)
    ) and re.search(r"aliena[cç][aã]o fiduci[aá]ria", ato, re.IGNORECASE)]
    if len(candidatos) != 1:
        dados["avisos"].append("Confira o registro da garantia e a descrição do título na matrícula; o contrato não foi localizado de forma única.")
        return
    ato = candidatos[0]
    registro = re.match(r"R[.\s-]*(\d+)", ato, re.IGNORECASE)
    if registro:
        dados["registroGarantia"] = f"R.{int(registro.group(1)):02d}"
    titulo = re.search(
        r"((?:Contrato de (?:Compra e Venda|Financiamento)|Instrumento Particular(?: de)?|C[eé]dula de Cr[eé]dito Imobili[aá]rio).{0,220}?)"
        r"(?:\s+n[.º°\s]*\d|,?\s+(?:datado|firmado)\s+|,?\s+celebrado\s+)",
        ato, re.IGNORECASE | re.DOTALL,
    )
    if titulo:
        dados["titulo"] = re.sub(r"\s+", " ", titulo.group(1)).strip(" ,;.")
