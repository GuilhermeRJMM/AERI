"""Extrator: contrato da CAIXA -> ficha.

O contrato não é prosa livre — é formulário de versão fixa, com o código do
modelo no rodapé de toda página (`MO30173Av120`) e as caixas rotuladas. Por isso
a âncora é o TEXTO DO RÓTULO, nunca a posição: mudou o preenchimento, o rótulo
continua lá.

**A âncora é a frase, não o código da caixa.** "B11" são três caracteres de
algarismos que parecem letras, e o OCR os entrega como "Bll", "BI 1" ou "B1l"
conforme a resolução da digitalização — cada variação faz a extração inteira
falhar. Ao lado deles está "Vencimento do Primeiro Encargo Mensal", que nenhum
motor erra. Ancorar na frase custa nada e não quebra.

O que não for reconhecido fica vazio e vira pendência no gerador. Este módulo
não inventa e não completa.
"""

from __future__ import annotations

import re

from . import documento as doc
from .ficha import (Contrato, Credora, Empresa, Ficha, Financiamento, Juros,
                    Pessoa, Documento as DocumentoIdentidade, Procuracao, Valores)

# Cabeçalho do contrato -> descrição como o ato a escreve. Dicionário, e não
# transformação automática: a redação registral tem maiúsculas e pontuação
# próprias ("Minha Casa Minha Vida", sem a vírgula que o contrato usa).
DESCRICOES = {
    "DE VENDA E COMPRA DE IMOVEL RESIDENCIAL, MUTUO COM OBRIGACOES E ALIENACAO "
    "FIDUCIARIA EM GARANTIA NO SFH - PROGRAMA MINHA CASA, MINHA VIDA":
        "de Venda e Compra de Imóvel Residencial, mútuo com Obrigações e "
        "Alienação Fiduciária em Garantia no SFH - Programa Minha Casa Minha Vida",
    # A mesma família, mas o cabeçalho acrescenta de onde vem o dinheiro. O ato
    # registrado não repete esse trecho — para no nome do programa.
    "DE VENDA E COMPRA DE IMOVEL RESIDENCIAL, MUTUO COM OBRIGACOES E ALIENACAO "
    "FIDUCIARIA EM GARANTIA NO SFH - PROGRAMA MINHA CASA, MINHA VIDA COM USO "
    "DOS RECURSOS DA CONTA VINCULADA DO FGTS DO(S) DEVEDOR(ES)":
        "de Venda e Compra de Imóvel Residencial, mútuo com Obrigações e "
        "Alienação Fiduciária em Garantia no SFH - Programa Minha Casa Minha Vida",
    "DE VENDA E COMPRA DE IMOVEL RESIDENCIAL, MUTUO COM OBRIGACOES E ALIENACAO "
    "FIDUCIARIA EM GARANTIA - CARTA DE CREDITO INDIVIDUAL - CCFGTS - PROGRAMA "
    "CASA VERDE E AMARELA":
        "de Venda e Compra de Imóvel, Mútuo e Alienação Fiduciária em Garantia - "
        "Carta de Crédito Individual - CCFGTS - Programa Casa Verde e Amarela",
    "DE VENDA E COMPRA DE TERRENO RESIDENCIAL, MUTUO PARA OBRAS COM OBRIGACOES "
    "E ALIENACAO FIDUCIARIA EM GARANTIA NO SFH - CARTA DE CREDITO INDIVIDUAL - "
    "PROGRAMA MINHA CASA MINHA VIDA":
        "de Venda e Compra de Terreno Residencial, mútuo para Obras com "
        "obrigações e Alienação Fiduciária em Garantia no SFH - Carta de "
        "Crédito Individual - Programa Minha Casa Minha Vida",
}

TIPOS_DOCUMENTO = {
    "CNH": "CNH",
    "CARTEIRA NACIONAL DE HABILITACAO": "CNH",
    "CARTEIRA DE IDENTIDADE": "RG",
    "RG": "RG",
    # Engenheiro, médico, advogado: a carteira do conselho de classe vale como
    # identidade, e o ato a nomeia por inteiro.
    "CARTEIRA DE IDENTIDADE PROFISSIONAL": "PROFISSIONAL",
    "IDENTIDADE PROFISSIONAL": "PROFISSIONAL",
    # A CAIXA chama de "Carteira Funcional" e também de "Carteira de Identidade
    # funcional"; o ato registra "Carteira de Identidade Profissional". É a
    # carteira do conselho de classe ou da corporação — a do contrato
    # 8.4444.4460043-3 é do CBM/GO. Sem esta linha o valor cru ia para o ato, e
    # o seletor da tela, que não tinha opção correspondente, exibia outra coisa.
    "CARTEIRA FUNCIONAL": "PROFISSIONAL",
    "CARTEIRA DE IDENTIDADE FUNCIONAL": "PROFISSIONAL",
}

ROTULOS_VALOR = {
    "recursos_proprios": "Recursos Próprios",
    "fgts": "Recursos da conta vinculada do FGTS",
    "desconto_fgts": "Desconto/subsídio concedido pelo FGTS/União",
    "financiamento": "Financiamento CAIXA",
    # família terreno-com-obras
    "obra": "Recursos próprios aplicados/a aplicar na obra",
}


def _limpa(texto: str) -> str:
    """Junta as quebras de linha do PDF sem colar palavras."""
    return re.sub(r"\s+", " ", texto or "").strip()


def _sem_acento_maiusculo(texto: str) -> str:
    import unicodedata
    decomposto = unicodedata.normalize("NFD", texto or "")
    limpo = "".join(c for c in decomposto if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", limpo).strip().upper()


def _data_pontuada(bruto: str) -> str:
    """"12 de Agosto de 2026" -> "12.08.2026"."""
    from . import normaliza as nz
    return nz.data(bruto, nz.Coletor(), "contrato")


def _valor(texto: str) -> float:
    """"210.000,00" -> 210000.0"""
    if not texto:
        return 0.0
    limpo = texto.strip().replace(".", "").replace(",", ".")
    try:
        return float(limpo)
    except ValueError:
        return 0.0


# Sobra de rótulo no fim de um trecho: cortar em "COMPRADOR(ES)" deixa para trás
# o "A2 -" que vinha antes dele. É lixo do formulário, não conteúdo.
SOBRA_DE_ROTULO = re.compile(r"\s*[AB][0-9lIO]{0,2}(?:\.[0-9lIO]{1,2})?\s*[-–]\s*$")


def _mais_repetido(leituras: list[str]) -> str:
    """A leitura que mais se repete, entre várias do mesmo campo.

    Serve para o que o formulário escreve em toda página. Empate resolve pela
    primeira, que é o comportamento de antes — nunca inventa uma terceira forma.
    """
    from collections import Counter
    limpos = [l.strip() for l in leituras if l and l.strip()]
    if not limpos:
        return ""
    return Counter(limpos).most_common(1)[0][0]


def _fatia(texto: str, inicio: str, *fins: str) -> str:
    """Trecho entre um rótulo e o próximo — o corte que o formulário permite."""
    i = texto.find(inicio)
    if i == -1:
        return ""
    i += len(inicio)
    corte = len(texto)
    for fim in fins:
        j = texto.find(fim, i)
        if j != -1:
            corte = min(corte, j)
    return SOBRA_DE_ROTULO.sub("", texto[i:corte])


# ----------------------------------------------------------------- pessoas
# O contrato quase sempre usa a forma genérica — "nascido(a)", "portador(a)",
# "solteiro(a)" — que não diz nada sobre o sexo. Mas no bloco de pessoa
# jurídica, e às vezes no do representante, ele escreve a forma flexionada.
# Onde isso acontece, o sexo sai de graça e uma pendência a menos aparece.
# O "nº" entre o tipo do documento e o número às vezes não é escrito
# ("portador(a) de CNH 07556069449"), e o OCR pode comê-lo de todo jeito.
PADRAO_DOCUMENTO = re.compile(
    r"portador(?:\(a\)|a)?\s+d[ae]\s+(?P<tipo>.+?)\s*(?:n[ºo°]\s*)?"
    # Carteira de conselho vem com a sigla do estado antes do número
    # ("PR- 160029 D"), então a captura aceita letras — mas exige ao menos um
    # algarismo, para não engolir a palavra seguinte quando faltar o número.
    # A vírgula antes de "expedida" é opcional: o modelo MO30809v016 escreve
    # "carteira de identidade nº 4.379.715 expedida por DGPC/GO", sem ela.
    r"(?P<numero>(?=[0-9A-Za-z.\- ]*\d)[0-9A-Za-z][0-9A-Za-z.\- ]*?)\s*,?\s*"
    r"expedid[ao]\s+por\s+(?P<orgao>.+?)\s+em\s+\d{2}/\d{2}/\d{4}", re.I)

# O PDF do modelo MO30809v016 larga um espaço dentro do número: "do CPF
# 003.381.471- 60". Sem tolerar isso, o representante da CAIXA saía sem CPF.
PADRAO_CPF = re.compile(
    r"\bdo\s+CPF\s+(?P<cpf>\d{3}\s*\.?\s*\d{3}\s*\.?\s*\d{3}\s*-?\s*\d{2})", re.I)
PADRAO_NASCIMENTO = re.compile(
    r"nascid[ao](?:\(a\))?\s+em\s+(\d{2}/\d{2}/\d{4})", re.I)
PADRAO_ESTADO_CIVIL = re.compile(
    r"\b(solteir|casad|divorciad|viúv|viuv|separad)[oa](?:\(a\))?\s*,", re.I)

# Formas flexionadas que revelam o sexo. A genérica com "(a)" nunca casa.
FLEXOES_SEXO = [
    (re.compile(r"\bnascido\s+em\b", re.I), "M"),
    (re.compile(r"\bnascida\s+em\b", re.I), "F"),
    (re.compile(r"\bportadora\s+d[ae]\b", re.I), "F"),
    (re.compile(r"\bportador\s+d[ae]\b", re.I), "M"),
    (re.compile(r"\bdomiciliado\s+em\b", re.I), "M"),
    (re.compile(r"\bdomiciliada\s+em\b", re.I), "F"),
    (re.compile(r"\b(?:solteira|casada|divorciada|viúva|separada)\s*,", re.I), "F"),
    (re.compile(r"\b(?:solteiro|casado|divorciado|viúvo|separado)\s*,", re.I), "M"),
]


def _sexo_das_flexoes(texto: str) -> str:
    """Só devolve sexo quando as flexões concordam entre si. Duas formas em
    desacordo significam que o texto é genérico ou que o OCR errou — e nesses
    casos é melhor perguntar ao conferente do que arriscar a concordância."""
    achados = {sexo for padrao, sexo in FLEXOES_SEXO if padrao.search(texto)}
    return achados.pop() if len(achados) == 1 else ""


PADRAO_REGIME = re.compile(
    r"casad[oa]\(a\)\s+n[oa]\s+regime\s+d[eo]\s+(?P<regime>[^,]+?)\s*,\s*"
    r"na\s+vigência\s+da\s+Lei\s+6\.515/77", re.I)
PADRAO_ENDERECO = re.compile(
    r"residentes?\s+e\s+domiciliad[oa]s?(?:\(a\))?\s+em\s+(?P<endereco>.+?)\s*\.?\s*$",
    re.I)

ESTADOS_CIVIS = {"solteir": "solteiro", "casad": "casado", "divorciad": "divorciado",
                 "viúv": "viúvo", "viuv": "viúvo", "separad": "separado"}


def _pessoa(trecho: str) -> Pessoa:
    """Uma pessoa da caixa A1, A2 ou A3.

    O contrato entrega mais do que o ato usa (nascimento, filiação, e-mail).
    Só é lido o que a qualificação registral pede.
    """
    texto = _limpa(trecho)
    pessoa = Pessoa()

    casou = re.match(r"^(?P<nome>[^,]+?)\s*,\s*nacionalidade\s+\w+", texto, re.I)
    if casou:
        pessoa.nome = casou.group("nome").strip()
    else:
        pessoa.nome = texto.split(",")[0].strip()

    casou = PADRAO_NASCIMENTO.search(texto)
    if casou:
        pessoa.nascimento = casou.group(1)
        # A profissão vem logo depois da data de nascimento e vai até "filho de:"
        depois = texto[casou.end():]
        profissao = _fatia(depois, ", ", ", filho de:", ", filha de:", ", e-mail:")
        pessoa.profissao = profissao.strip(" ,")

    casou = PADRAO_DOCUMENTO.search(texto)
    if casou:
        tipo = TIPOS_DOCUMENTO.get(_sem_acento_maiusculo(casou.group("tipo")), "")
        pessoa.documento = DocumentoIdentidade(
            tipo=tipo or casou.group("tipo").strip(),
            numero=casou.group("numero").strip(),
            orgao=casou.group("orgao").strip())

    casou = PADRAO_CPF.search(texto)
    if casou:
        pessoa.cpf = re.sub(r"\s+", "", casou.group("cpf"))

    casou = PADRAO_ESTADO_CIVIL.search(texto)
    if casou:
        pessoa.estado_civil = ESTADOS_CIVIS.get(casou.group(1).lower(), "")

    casou = PADRAO_REGIME.search(texto)
    if casou:
        pessoa.regime_bens = _limpa(casou.group("regime"))
        # O contrato diz "na vigência da Lei 6.515/77"; o ato escreve assim:
        pessoa.marco_lei = "posteriormente ao advento da Lei Federal n.º 6.515/77"
        # Quem tem regime de bens é casado, e a frase do regime já o diz —
        # "casado(a) no regime de...". O padrão do estado civil exige vírgula
        # logo depois da palavra, e aqui vem " no": sem isto, o titular de um
        # bloco que termina no regime ficava sem estado civil nenhum, e o ato
        # saía com a pendência de um dado que estava escrito no contrato.
        if not pessoa.estado_civil:
            pessoa.estado_civil = "casado"

    casou = PADRAO_ENDERECO.search(texto)
    if casou:
        pessoa.endereco = _limpa(casou.group("endereco"))

    pessoa.sexo = _sexo_das_flexoes(texto)
    return pessoa


# Onde começa a qualificação de uma pessoa: NOME EM CAIXA ALTA seguido de
# ", nacionalidade". É a forma que a CAIXA usa para toda parte.
COMECO_DE_PESSOA = r"[A-ZÀ-Ý][A-ZÀ-Ý\s'’\-]{3,},\s*nacionalidade"

# O que separa DUAS PARTES é o ponto final antes do nome — com ou sem "e". O
# cônjuge vem depois de VÍRGULA, e é essa diferença de pontuação que distingue
# "dois vendedores" de "um casal".
SEPARA_PARTES = re.compile(
    r"(?<=\.)\s+(?:e\s+)?(?=" + COMECO_DE_PESSOA + ")")


def _divide_partes(bloco: str) -> list[str]:
    """Separa pessoas distintas dentro de A1 ou A2.

    A forma antiga só reconhecia ". e FULANO". O contrato 8.4444.4460043-3
    separa os dois vendedores com **ponto final e nada mais** — e aí a
    ferramenta lia uma pessoa só: o endereço do primeiro engolia a qualificação
    do segundo, e o estado civil que sobrava era o do último nome do bloco.

    O que ancora o corte é o começo de uma qualificação nova, "NOME,
    nacionalidade", precedido de ponto. O cônjuge não casa: vem depois de
    vírgula.
    """
    texto = _limpa(bloco)
    pedacos = SEPARA_PARTES.split(texto)
    return [p.strip() for p in pedacos if p.strip()]


# ", e seu cônjuge FULANA" e também ", e seu cônjuge, que comparece neste ato
# como interveniente anuente, FULANA" — a oração entre o rótulo e o nome fazia
# o cônjuge sumir da ficha inteira.
ROTULO_DE_CONJUGE = re.compile(r",\s*e\s+seu\(?a?\)?\s*c[ôo]njuge\b", re.I)


def _parte_com_conjuge(trecho: str) -> Pessoa:
    """Um bloco que pode ser uma pessoa ou um casal."""
    rotulo = ROTULO_DE_CONJUGE.search(trecho)
    if not rotulo:
        return _pessoa(trecho)

    # Do rótulo até o nome pode haver uma oração ("que comparece neste ato como
    # interveniente anuente"). O nome é que marca onde o cônjuge começa.
    depois = re.search(COMECO_DE_PESSOA, trecho[rotulo.end():])
    if not depois:
        return _pessoa(trecho)

    titular = _pessoa(trecho[:rotulo.start()])
    conjuge = _pessoa(trecho[rotulo.end() + depois.start():])

    # A oração entre o rótulo e o nome diz o papel dele no ato.
    conjuge.anuente = bool(re.search(
        r"anuente", trecho[rotulo.end():rotulo.end() + depois.start()], re.I))

    # Endereço, regime e estado civil vêm uma vez só, no fim do bloco do casal.
    if not titular.endereco:
        titular.endereco = conjuge.endereco
    if not conjuge.estado_civil:
        conjuge.estado_civil = titular.estado_civil
    if not conjuge.regime_bens:
        conjuge.regime_bens = titular.regime_bens
        conjuge.marco_lei = titular.marco_lei
    titular.conjuge = conjuge
    return titular


PADRAO_EMPRESA = re.compile(r"inscrit[ao]\s+no\s+CNPJ", re.I)
PADRAO_CNPJ = re.compile(r"CNPJ\s*n?[ºo°]?\s*(\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2})", re.I)
PADRAO_NIRE = re.compile(r"NIRE\s*n?[ºo°]?\s*(\w+)", re.I)
PADRAO_CLAUSULA = re.compile(r"na\s+conformidade\s+da\s+(cláusula\s+\S+)", re.I)
PADRAO_SESSAO = re.compile(r"em\s+sess[ãa]o\s+de\s+(\d{2}/\d{2}/\d{4})", re.I)


def _empresa(trecho: str) -> Empresa:
    """A caixa A1 quando o vendedor é construtora ou incorporadora.

    O contrato dá razão social, CNPJ, sede, NIRE, a cláusula que confere poderes
    e quem assina. NÃO dá a data do ato constitutivo nem a certidão específica
    da Junta — o ato registrado exige as duas, e elas vêm de documento próprio.
    """
    texto = _limpa(trecho)
    empresa = Empresa()

    casou = re.match(r"^(?P<razao>.+?)\s*,\s*inscrit[ao]\s+no\s+CNPJ", texto, re.I)
    empresa.razao_social = casou.group("razao").strip() if casou \
        else texto.split(",")[0].strip()

    casou = PADRAO_CNPJ.search(texto)
    if casou:
        empresa.cnpj = casou.group(1)

    # a sede vem depois de "situada em" e vai até o próximo rótulo do formulário
    sede = _fatia(texto, "situada em ", ", e-mail:", ", com seus atos",
                  ", representada")
    empresa.endereco = _limpa(sede).rstrip(".,")

    casou = PADRAO_NIRE.search(texto)
    if casou:
        empresa.juceg_numero = casou.group(1)

    casou = PADRAO_CLAUSULA.search(texto)
    if casou:
        empresa.clausula_representacao = _limpa(casou.group(1))

    casou = PADRAO_SESSAO.search(texto)
    if casou:
        empresa.juceg_data = casou.group(1).replace("/", ".")

    # quem assina pela empresa vem depois de ", por NOME, nacionalidade..."
    casou = re.search(r",\s*por\s+(?=[A-ZÀ-Ý][^,]{3,},\s*nacionalidade)", texto, re.I)
    if casou:
        empresa.representante = _pessoa(texto[casou.end():])

    return empresa


def _pessoas_do_bloco(bloco: str) -> list:
    partes = []
    for pedaco in _divide_partes(bloco):
        if PADRAO_EMPRESA.search(pedaco):
            partes.append(_empresa(pedaco))
        else:
            partes.append(_parte_com_conjuge(pedaco))
    return partes


# ------------------------------------------------------------- procurações
PADRAO_PROCURACAO = re.compile(
    r"(?P<especie>procuração|substabelecimento)\s*(?:lavrad[ao])?\s*"
    r"às\s+folhas\s+(?P<folhas>[0-9A-Za-z/]+)\s*,\s*"
    r"do\s+livro\s+(?P<livro>[0-9A-Za-z-]+)\s*,\s*"
    r"em\s+(?P<data>\d{2}/\d{2}/\d{4})\s*,\s*"
    r"no\s+(?P<serventia>.+?)\s*(?=,\s*substabelecimento|\s+e\s+substabelecimento|\.\s*,|\.,|$)",
    re.I)


def _procuracoes(bloco: str) -> list[Procuracao]:
    texto = _limpa(bloco)
    saida = []
    for casou in PADRAO_PROCURACAO.finditer(texto):
        especie = ("Procuração" if casou.group("especie").lower().startswith("procura")
                   else "Substabelecimento")
        serventia = casou.group("serventia").strip().rstrip(".,")
        # "2º Ofício de Notas e Protesto de Brasília/DF" -> "...Brasília-DF"
        serventia = re.sub(r"\s*/\s*([A-Z]{2})\b", r"-\1", serventia)
        serventia = re.sub(r"\bda\s+Comarca\s+de\s+", "da Comarca de ", serventia)
        saida.append(Procuracao(
            especie=especie,
            data=casou.group("data").replace("/", "."),
            folhas=casou.group("folhas"),
            livro=casou.group("livro"),
            serventia=serventia))
    return saida


# ----------------------------------------------------------------- extração
def extrai(caminho, permitir_ocr: bool = True) -> Ficha:
    """Ponto de entrada único: decide sozinho se lê o texto ou se chama o OCR.

    A decisão mora aqui, e não em quem chama, para que o servidor, as funções
    serverless e os testes percorram exatamente o mesmo caminho. Enquanto ela
    ficou duplicada, o teste lia um contrato digitalizado como se fosse vazio.
    """
    documento = doc.abre(caminho)
    from . import ocr

    # Documento fotografado passa SEMPRE pelo OCR, mesmo quando já traz camada
    # de texto. Scanner costuma embutir um OCR próprio, de motor desconhecido e
    # sem ninguém ter conferido; aproveitá-lo seria herdar erro de terceiro sem
    # saber. Decisão da serventia (25/08/2026).
    if documento.eh_foto:
        if not (permitir_ocr and ocr.disponivel()):
            # Sem OCR não há o que ler por rótulo. A ficha volta vazia, e a tela
            # diz por quê — em vez de fingir que leu.
            ficha = Ficha()
            ficha.origens["_natureza"] = "digitalizado"
            return ficha

        motor = ocr.motor()
        ficha = extrai_do_texto(ocr.texto_de(caminho))
        ficha.origens["_natureza"] = f"digitalizado, lido por OCR ({motor})"
        if documento.tem_camada_de_texto:
            ficha.origens["_camada_ignorada"] = (
                "o arquivo já vinha com camada de texto, provavelmente do "
                "scanner; foi relida por OCR próprio")
        return ficha

    if documento.tem_camada_de_texto:
        ficha = extrai_do_texto(documento.texto)
        ficha.origens["_natureza"] = "nato-digital"
        return ficha

    ficha = Ficha()
    ficha.origens["_natureza"] = "sem texto e sem imagem de página"
    return ficha


def extrai_do_texto(texto: str) -> Ficha:
    ficha = Ficha()
    ficha.origens["_natureza"] = "nato-digital"
    linear = _limpa(texto)

    # ---- contrato
    # O rodapé se repete em todas as páginas, e o OCR não erra sempre no mesmo
    # lugar: numa página lê "8.4444.4209651-9" e noutra "8.4444.4209651 9".
    # Votar entre as leituras aproveita uma redundância que o documento já tem
    # e custa nada — é a defesa mais barata contra erro de reconhecimento.
    numero = _mais_repetido(re.findall(r"CONTRATO\s+N[ºo°P]?\s*([0-9.\-]+)", linear))
    if numero:
        ficha.contrato.numero = numero.strip(" .")
        ficha.origens["contrato.numero"] = f"rodapé (repetido em toda página)"

    modelo = _mais_repetido(re.findall(r"\b(MO\d+Av\d+)\b", linear))
    if modelo:
        ficha.contrato.modelo = modelo
        ficha.origens["contrato.modelo"] = "rodapé"

    # O cabeçalho vem depois da referência à lei; uns contratos põem vírgula
    # depois do ano, outros não, e o OCR ainda pode comer o espaço.
    # O OCR troca o ponto do milhar por vírgula; a correção já tenta consertar,
    # mas a âncora aceita as duas formas para não depender só dela.
    casou = re.search(r"da Lei 4[.,]380/1964", linear)
    inicio = casou.group(0) if casou else "da Lei 4.380/1964"
    cabecalho = _fatia(linear, inicio,
                       " A - QUALIFICAÇÃO", "A1 -", "A - QUALIFICA",
                       "QUALIFICAÇÃO DAS PARTES")
    chave = _sem_acento_maiusculo(cabecalho).strip(" ,.").rstrip(". ")
    if chave in DESCRICOES:
        ficha.contrato.descricao = DESCRICOES[chave]
        ficha.origens["contrato.descricao"] = "cabeçalho da p.1"
    elif cabecalho.strip():
        # Cabeçalho que a tabela não conhece NÃO pode virar `[[falta:]]`: o
        # dado está escrito no contrato, e sai como está. Foi o que aconteceu
        # com o modelo MO30809v016 ("... no SFH - CCSBPE"), cujo cabeçalho não
        # estava na tabela: os DOIS atos saíam sem a forma do título.
        #
        # Decisão da serventia (25/08/2026): a forma do título sai IGUAL AO
        # CONTRATO. Não há redação a confirmar — o que a tela diz é só de onde
        # o texto veio.
        ficha.contrato.descricao = _limpa(cabecalho).strip(" ,.")
        ficha.origens["contrato.descricao"] = "cabeçalho da p.1 (forma nova)"
    ficha.brutos["contrato.descricao"] = cabecalho.strip()

    casou = re.search(r"assinam o presente em .*?vias\.\s*(.+?)\s+(\d{1,2} de "
                      r"[A-Za-zç]+ de \d{4})", linear, re.I)
    if casou:
        ficha.contrato.data = _data_pontuada(casou.group(2))
        ficha.origens["contrato.data"] = "fecho, antes das assinaturas"

    casou = re.search(r"OUTORGA\s+DE\s+PROCURA[ÇC](?:[ÕO]ES|[ÃA]O)", linear, re.I)
    if casou:
        # o número da cláusula vem imediatamente antes do título
        antes = linear[max(0, casou.start() - 12):casou.start()]
        numero = re.findall(r"(\d{1,2})\s*$", antes.strip())
        if numero:
            ficha.contrato.item_outorga = numero[0]
            ficha.origens["contrato.item_outorga"] = "corpo do contrato"

    # "Conforme item 4" numa família, "De acordo com item 6" na outra.
    # O valor nem sempre vem colado ao rótulo: no modelo MO30809v016 o rodapé
    # da página entra no meio ("B12 - Reajuste dos Encargos Mensais:
    # MO30809v016 CONTRATO Nº ... 3 23/09/2026 Conforme item 4"). Por isso o
    # corte é a caixa inteira, do rótulo até o B13.
    bloco_b12 = _fatia(linear, "Reajuste dos Encargos", "B13", "C - COMPOSIÇÃO")
    casou = re.search(r"(?:Conforme|De acordo com)\s+(?:o\s+)?item\s*(\d+)",
                      bloco_b12 or "", re.I)
    if casou:
        ficha.contrato.item_reajuste = f"{int(casou.group(1)):02d}"
        ficha.origens["contrato.item_reajuste"] = "caixa B12"

    casou = re.search(r"Modalidade:\s*([A-ZÇÃÕÁÉÍÓÚ ]+?)\s+B2\s*-", linear)
    if casou:
        ficha.contrato.modalidade = casou.group(1).strip()
        ficha.origens["contrato.modalidade"] = "caixa B1"

    # ---- partes
    bloco_a1 = _fatia(linear, "VENDEDOR(ES):", "COMPRADOR(ES)")
    if bloco_a1:
        ficha.vendedores = _pessoas_do_bloco(bloco_a1)
        ficha.origens["vendedores"] = "caixa A1"
        ficha.brutos["vendedores"] = bloco_a1.strip()

    bloco_a2 = _fatia(linear, "DEVEDOR(ES):", "A3 - CREDORA")
    if bloco_a2:
        ficha.compradores = _pessoas_do_bloco(bloco_a2)
        ficha.origens["compradores"] = "caixa A2"
        ficha.brutos["compradores"] = bloco_a2.strip()

    bloco_a3 = _fatia(linear, "CREDORA FIDUCIÁRIA:", "Agência responsável")
    if bloco_a3:
        ficha.credora = Credora()
        representante = _fatia(bloco_a3, "neste ato representada por ", "; conforme ",
                               ", conforme ")
        if representante:
            ficha.credora.representante = _representante(representante)
        ficha.credora.procuracoes = _procuracoes(bloco_a3)
        ficha.origens["credora"] = "caixa A3"
        ficha.brutos["credora"] = bloco_a3.strip()

    # ---- descrição do imóvel (caixa D), que a conferência prévia confronta
    # com o fólio. O gerador não usa: o ato escreve "O descrito na matrícula".
    bloco_d = _fatia(linear, "DESCRIÇÃO DO IMÓVEL OBJETO DESTE CONTRATO",
                     "E - ELEMENTOS", "F - TARIFAS", "ELEMENTOS IDENTIFICADORES")
    if bloco_d:
        ficha.brutos["imovel"] = bloco_d.strip()
        ficha.origens["imovel"] = "caixa D"
        _matricula_da_descricao(bloco_d, ficha)

    # ---- valores e financiamento
    _valores(linear, ficha)
    _financiamento(linear, ficha)
    return ficha


def _representante(trecho: str) -> Pessoa:
    """O representante da CAIXA vem qualificado em ordem diferente das partes:
    o estado civil vem solto, sem "(a)", e o endereço é comercial."""
    texto = _limpa(trecho)
    pessoa = Pessoa()
    pessoa.nome = texto.split(",")[0].strip()

    # O representante da CAIXA é o único que vem com as formas NÃO genéricas
    # ("casada", "economiária"), diferente das partes, que vêm com "casado(a)".
    #
    # CUIDADO: "nacionalidade brasileira" NÃO diz nada sobre o sexo — o
    # adjetivo concorda com "nacionalidade", que é palavra feminina, e aparece
    # assim até para homem. Ler o sexo dali dava mulher para todo mundo, e o
    # ato saía com "brasileira, casada, portadora" para um representante homem.
    # O sinal que presta é o estado civil, que concorda com a pessoa.
    casou = re.search(r"nacionalidade\s+brasileira?\s*,\s*(\w+)\s*,", texto, re.I)
    if casou:
        civil = casou.group(1).lower()
        for raiz, valor in (("casad", "casado"), ("solteir", "solteiro"),
                            ("divorciad", "divorciado"), ("viúv", "viúvo"),
                            ("viuv", "viúvo"), ("separad", "separado")):
            if civil.startswith(raiz):
                pessoa.estado_civil = valor
                pessoa.sexo = "F" if civil.endswith("a") else "M"
                break

    casou = PADRAO_NASCIMENTO.search(texto)
    if casou:
        pessoa.nascimento = casou.group(1)
        depois = texto[casou.end():]
        pessoa.profissao = _fatia(depois, ", ", ", portador").strip(" ,")

    # "carteira de identidade nº 4.379.715 expedida por DGPC/GO em 20/09/1999":
    # o "nº" entre o rótulo e o número, e a vírgula antes de "expedida", são
    # ambos opcionais — o modelo MO30809v016 escreve o primeiro e omite a
    # segunda, e o representante da CAIXA saía sem documento no ato.
    casou = re.search(r"carteira de identidade\s+(?:n[ºo°]\.?\s*)?"
                      r"(?P<numero>[0-9A-Za-z.\-]+)\s*,?\s*"
                      r"expedida por\s+(?P<orgao>.+?)\s+em\s+\d{2}/\d{2}/\d{4}",
                      texto, re.I)
    if casou:
        pessoa.documento = DocumentoIdentidade(
            tipo="RG", numero=casou.group("numero"), orgao=casou.group("orgao").strip())

    casou = PADRAO_CPF.search(texto)
    if casou:
        pessoa.cpf = re.sub(r"\s+", "", casou.group("cpf"))

    casou = re.search(r"endereço comercial na\s+(?P<endereco>.+?)\s*;?\s*$", texto, re.I)
    if casou:
        pessoa.endereco = _limpa(casou.group("endereco")).rstrip(".,")
    return pessoa


# A caixa D cita a matrícula do imóvel: "CUJOS LIMITES E CONFRONTAÇÕES
# ENCONTRAM-SE ANOTADOS NA MATRÍCULA 39.100", e de novo em "IMÓVEL HAVIDO
# CONFORME MATRÍCULA 39.100". Nos quatro pares do acervo o número citado é o da
# matrícula em que o ato foi registrado — não o da matrícula de origem.
MATRICULA_NA_DESCRICAO = re.compile(
    r"MATR[IÍ]CULA\s*(?:N?\.?\s*[ºo°]?\s*)?(\d{1,3}(?:\.\d{3})+|\d{3,7})", re.I)


def _matricula_da_descricao(bloco_d: str, ficha: Ficha) -> None:
    """O número da matrícula, lido da descrição do imóvel.

    Só preenche quando a descrição cita **um único** número: contrato que fala
    de mais de uma matrícula (desmembramento, unificação) não permite escolher
    sozinho qual é a do ato, e chutar poria o registro no fólio de outro imóvel.
    """
    if ficha.matricula.numero:
        return
    achados = {m.group(1) for m in MATRICULA_NA_DESCRICAO.finditer(bloco_d)}
    if len(achados) == 1:
        ficha.matricula.numero = achados.pop()
        ficha.origens["matricula.numero"] = "caixa D"
    elif len(achados) > 1:
        ficha.origens["matricula._alerta"] = (
            f"a descrição do imóvel cita mais de uma matrícula "
            f"({', '.join(sorted(achados))}); informe qual é a do ato")


def _valores(linear: str, ficha: Ficha) -> None:
    valores = Valores()

    # "venda e compra do imóvel" na família comum; "venda e compra do terreno e
    # construção do imóvel" na família com obras.
    casou = re.search(r"venda e compra d[oe].{0,40}?objeto deste contrato é de\s*"
                      r"R\$\s*([\d.,]+)", linear, re.I)
    if casou:
        valores.total = _valor(casou.group(1))
        ficha.origens["valores.total"] = "caixa B4"

    # Na família com obras o contrato destaca, dentro do B4, quanto do total é
    # o terreno. É ESSE valor que o R. de venda e compra registra — o resto é
    # construção, que ainda não existe e não se transmite.
    casou = re.search(r"Do valor total descrito acima,\s*R\$\s*([\d.,]+)\s*"
                      r"(?:\([^)]*\))?\s*correspondem ao valor de venda e compra "
                      r"do terreno", linear, re.I)
    if casou:
        valores.terreno = _valor(casou.group(1))
        ficha.origens["valores.terreno"] = "caixa B4"

    # A tabela do B4 nem sempre linexa rótulo-valor alternado: no Contrato 3 ela
    # sai "Financiamento CAIXA R$168.000,00 Recursos Próprios Desconto/subsídio
    # R$39.552,00 R$2.448,00" — dois rótulos seguidos e depois os dois valores.
    # Casar rótulo com o R$ mais próximo erra; parear pela ORDEM acerta os dois
    # formatos, porque a coluna de valores segue a mesma ordem da de rótulos.
    # Depois da lista de parcelas vem, em algumas famílias, uma frase com mais
    # um valor — a quitação do contrato anterior, ou quanto do total é terreno.
    # Ela precisa ficar FORA do bloco: um valor a mais que rótulos faz o
    # pareamento por ordem se recusar a adivinhar, e nada é lido.
    FIM_DAS_PARCELAS = ("B4.1", "B5 -", "Conta para crédito",
                        "Do valor total descrito acima", "Dos valores acima")
    bloco = _fatia(linear, "composto pelos valores:", *FIM_DAS_PARCELAS)
    if not bloco:
        # a família com obras diz "composto pela integralização dos valores abaixo"
        bloco = _fatia(linear, "integralização dos valores abaixo:", *FIM_DAS_PARCELAS)
    if bloco:
        achados = []
        for campo, rotulo in ROTULOS_VALOR.items():
            posicao = bloco.lower().find(rotulo.lower())
            if posicao != -1:
                achados.append((posicao, len(rotulo), campo))

        # "Recursos Próprios" é PREFIXO de "Recursos próprios aplicados/a
        # aplicar na obra": os dois casavam na mesma posição e criavam um
        # terceiro achado para uma coluna de dois valores. O pareamento por
        # ordem então se recusava a adivinhar, e a família terreno-com-obras
        # saía sem composição nenhuma — calada, porque o ato dessa família usa
        # só o valor do terreno e continuava correto. Na mesma posição, quem
        # vale é o rótulo mais longo: é ele que está escrito no contrato.
        maior_por_posicao: dict[int, tuple[int, str]] = {}
        for posicao, tamanho, campo in achados:
            if tamanho > maior_por_posicao.get(posicao, (0, ""))[0]:
                maior_por_posicao[posicao] = (tamanho, campo)
        achados = sorted((posicao, campo)
                         for posicao, (_, campo) in maior_por_posicao.items())

        quantias = re.findall(r"R\$\s*([\d.,]+)", bloco)

        if len(achados) == len(quantias):
            for (_, campo), quantia in zip(achados, quantias):
                setattr(valores, campo, _valor(quantia))
                ficha.origens[f"valores.{campo}"] = "caixa B4"
        else:
            ficha.origens["valores._alerta"] = (
                f"a caixa B4 trouxe {len(achados)} rótulo(s) e {len(quantias)} "
                f"valor(es); confira parcela por parcela")

    ficha.valores = valores


PADRAO_TAXA = re.compile(
    r"Nominal\s*%?\s*\(a\.a\.\)\s*(?P<nominal>[\d.,]+|Não se aplica)\s*"
    r"Efetiva\s*%?\s*\(a\.a\.\)\s*(?P<ano>[\d.,]+|Não se aplica)\s*"
    r"Efetiva\s*%?\s*\(a\.m\.\)\s*(?P<mes>[\d.,]+|Não se aplica)", re.I)


COLUNAS_DE_JUROS = ("Sem Desconto", "Com Desconto", "Com Redutor", "Taxa Contratada")


def _taxa_contratada(linear: str):
    """A taxa que vai para o ato, e só ela.

    O B9 mostra até quatro colunas — três são simulação, uma é o que foi
    contratado. Escolher a errada põe juros errado num registro, e nada acusa.

    São dois formatos:

    - **nato-digital**: os quatro rótulos vêm juntos e depois os quatro grupos
      de valores, na mesma ordem. O contratado é o último.
    - **digitalizado**: o OCR separa as colunas e pode largar o B9.4 muito
      depois, com o rótulo lido como "89.4". Aí o rótulo vem colado no valor.

    A conferência é a contagem: se há tantos grupos quantas colunas anunciadas,
    a ordem vale e o último é o contratado. Se não bate, procura-se o valor
    colado ao rótulo "Taxa Contratada". Não achando nenhum dos dois, devolve
    vazio — chutar taxa é pior que não ter.
    """
    regiao = _fatia(linear, "Taxa de Juros", "Encargo Mensal Inicial") or linear
    colunas = sum(1 for c in COLUNAS_DE_JUROS if c in regiao)
    grupos = PADRAO_TAXA.findall(regiao)

    if colunas and len(grupos) == colunas:
        nominal, ano, mes = grupos[-1]
        return (Juros(nominal_ao_ano=nominal, efetiva_ao_ano=ano,
                      efetiva_ao_mes=mes),
                f"caixa B9.4 (última de {colunas} colunas)")

    # O rótulo pode estar fora da região, jogado pelo OCR — procura no texto
    # todo. E aparece mais de uma vez ("Taxa Contratada" rotula também a coluna
    # do B10.1), então vale a que tiver o trio de valores GRUDADO nela: é a
    # única que carrega a taxa, e as outras são só cabeçalho de coluna.
    for marca in re.finditer(r"Taxa Contratada", linear):
        vizinhanca = linear[marca.end():marca.end() + 160]
        casou = PADRAO_TAXA.search(vizinhanca)
        if casou:
            return (Juros(nominal_ao_ano=casou.group("nominal"),
                          efetiva_ao_ano=casou.group("ano"),
                          efetiva_ao_mes=casou.group("mes")),
                    "caixa B9.4 (valor colado ao rótulo)")

    # Zero coluna anunciada e zero grupo não é divergência: é caixa B9 ausente —
    # PDF que não é contrato da CAIXA, ou digitalizado que o OCR não alcançou.
    # Dizer "0 colunas e 0 completas" era ruído com cara de diagnóstico, e ficou
    # visível quando os alertas passaram a chegar à tela.
    if not colunas and not grupos:
        return (None, "a caixa B9 (taxa de juros) não foi encontrada no "
                      "documento. Preencha a taxa contratada à mão.")

    return (None, f"o B9 anuncia {colunas} coluna(s) e só {len(grupos)} vieram "
                  f"completas; as outras são simulação e não podem ir para o "
                  f"ato. Preencha a taxa contratada à mão.")


def _financiamento(linear: str, ficha: Ficha) -> None:
    f = Financiamento()

    casou = re.search(r"Sistema de Amortização:\s*(\w+)", linear, re.I)
    if casou:
        f.amortizacao = casou.group(1).upper()
        ficha.origens["financiamento.amortizacao"] = "caixa B2"

    # "Valor da Dívida - Financiamento" numa família, "Valor da Dívida
    # (Financiamento)" na outra.
    casou = re.search(r"Valor da Dívida\s*[-(]\s*Financiamento\)?:\s*R\$\s*([\d.,]+)", linear, re.I)
    if casou:
        f.divida = _valor(casou.group(1))
        ficha.origens["financiamento.divida"] = "caixa B6"

    casou = re.search(r"Valor da Garantia Fiduciária.*?R\$\s*([\d.,]+)",
                      linear, re.I)
    if casou:
        f.garantia = _valor(casou.group(1))
        ficha.origens["financiamento.garantia"] = "caixa B7"

    # Os rótulos do B8 saem todos juntos e os valores vêm depois, na mesma
    # ordem. São dois na família comum (total, amortização) e três na família
    # com obras (total, amortização, construção).
    # No PDF digitalizado o OCR lê coluna por coluna, e os valores do B8 acabam
    # depois da tabela de juros — não colados no rótulo. Por isso a busca é pela
    # SEQUÊNCIA de inteiros soltos, do tamanho do número de rótulos: é a única
    # coisa que identifica o trio "total, amortização, construção" sem depender
    # de onde o OCR o largou. Números com casa decimal (as taxas) ficam de fora.
    bloco_b8 = _fatia(linear, "Prazo Total (meses):", "Encargo Mensal Inicial")
    if not bloco_b8:
        # O modelo MO30809v016 não tem "Prazo Total": traz só o da amortização,
        # e é esse que o ato registra.
        casou = re.search(r"Prazo\s+Amortiza[çc][ãa]o\s*\(meses\)\s*:?\s*(\d{1,4})",
                          linear, re.I)
        if casou:
            f.prazo_meses = casou.group(1)
            ficha.origens["financiamento.prazo_meses"] = "caixa B8"
    if bloco_b8:
        rotulos = len(re.findall(r"B8\.\d\s*-", bloco_b8)) + 1
        padrao = (r"(?<![\d.,])" + r"\s+".join([r"(\d{1,4})"] * rotulos) +
                  r"(?![\d.,])")
        casou = re.search(padrao, bloco_b8)
        if casou:
            f.prazo_meses = casou.group(2) if rotulos >= 2 else casou.group(1)
            ficha.origens["financiamento.prazo_meses"] = (
                "caixa B8.1" if rotulos >= 2 else "caixa B8")
            if rotulos >= 3:
                # o terceiro é a construção, que o ato registra em separado
                f.prazo_construcao = f"{int(casou.group(3)):02d}"
                ficha.origens["financiamento.prazo_construcao"] = "caixa B8.2"
        else:
            ficha.origens["financiamento._alerta"] = (
                f"a caixa B8 tem {rotulos} rótulo(s), mas os prazos não foram "
                f"achados junto deles; confira à mão")

    # A taxa que o ato registra é a CONTRATADA, e ela precisa ser identificada
    # pelo nome — nunca por posição.
    #
    # "Pegue o último grupo" parecia bastar e é perigoso: num contrato
    # digitalizado o OCR perdeu um valor do grupo B9.3, deixando-o incompleto, e
    # jogou o B9.4 para depois do B13 lendo o rótulo como "89.4". O último grupo
    # completo passou a ser o B9.2 — "Com Desconto" —, e o ato sairia com
    # 5,0000% no lugar de 4,5000%. Taxa errada num registro, sem nada acusando.
    #
    # Agora a âncora é a frase "Taxa Contratada". Não achando, não se escolhe
    # grupo nenhum: fica pendência, porque chutar taxa é pior que não ter.
    juros, origem = _taxa_contratada(linear)
    if juros:
        f.juros = juros
        ficha.origens["financiamento.juros"] = origem
    else:
        ficha.origens["financiamento._alerta_juros"] = origem

    # No PDF digitalizado o OCR separa os rótulos dos valores, então casar
    # "Total: R$ x" não funciona. O total é sempre o ÚLTIMO valor da caixa B10 —
    # depois da prestação, dos prêmios de seguro e da tarifa.
    # O corte vai até o B12 e SÓ até ele. No digitalizado o OCR larga a coluna
    # de valores fora de ordem — vêm depois do B11 e até depois do B13 — e
    # qualquer outro rótulo usado como limite decepa o total. B11 é data e B13
    # é texto, então incluí-los não atrapalha: o total é o último "R$" daqui.
    bloco_b10 = _fatia(linear, "Encargo Mensal Inicial", "B12 -")
    quantias = re.findall(r"R\$\s*([\d.,]+)", bloco_b10) if bloco_b10 else []
    if quantias:
        f.encargo_mensal_total = _valor(quantias[-1])
        ficha.origens["financiamento.encargo_mensal_total"] = "caixa B10.1"

    # Mesmo caso do B12: o rodapé pode separar o rótulo do valor.
    bloco_b11 = _fatia(linear, "Vencimento do Primeiro Encargo Mensal",
                       "B13", "C - COMPOSIÇÃO") or ""
    casou = re.search(r"(\d{2}/\d{2}/\d{4})", bloco_b11)
    if casou:
        f.primeiro_vencimento = casou.group(1).replace("/", ".")
        ficha.origens["financiamento.primeiro_vencimento"] = "caixa B11"

    ficha.financiamento = f
