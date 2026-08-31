"""Valor por extenso, em reais.

O ato escreve "R$156.800,00 (cento e cinquenta e seis mil e oitocentos reais)",
e o contrato nem sempre traz o extenso: a caixa B6, do valor da dívida, vem só
em algarismo. Por isso isto aqui é gerador, não copiador.
"""

from decimal import Decimal

UNIDADES = [
    "zero", "um", "dois", "três", "quatro", "cinco", "seis", "sete", "oito",
    "nove", "dez", "onze", "doze", "treze", "catorze", "quinze", "dezesseis",
    "dezessete", "dezoito", "dezenove",
]
DEZENAS = ["", "", "vinte", "trinta", "quarenta", "cinquenta", "sessenta",
           "setenta", "oitenta", "noventa"]
CENTENAS = ["", "cento", "duzentos", "trezentos", "quatrocentos", "quinhentos",
            "seiscentos", "setecentos", "oitocentos", "novecentos"]
ESCALAS = {2: ("milhão", "milhões"), 3: ("bilhão", "bilhões")}


def _grupo(n: int) -> str:
    """1 a 999."""
    if n == 100:
        return "cem"
    partes = []
    centena, resto = divmod(n, 100)
    if centena:
        partes.append(CENTENAS[centena])
    if resto:
        if resto < 20:
            partes.append(UNIDADES[resto])
        else:
            dezena, unidade = divmod(resto, 10)
            partes.append(
                f"{DEZENAS[dezena]} e {UNIDADES[unidade]}" if unidade else DEZENAS[dezena]
            )
    return " e ".join(partes)


def _liga_com_e(valor: int) -> bool:
    """O "e" antes do último grupo entra quando ele é menor que cem ou centena
    redonda: "cento e cinquenta e seis mil E oitocentos", mas "mil cento e
    sessenta e cinco" — 165 não é nenhum dos dois."""
    return valor < 100 or valor % 100 == 0


def inteiro(n: int) -> str:
    if n == 0:
        return "zero"

    grupos = []
    resto = n
    while resto > 0:
        resto, g = divmod(resto, 1000)
        grupos.append(g)

    partes = []
    for ordem in range(len(grupos) - 1, -1, -1):
        valor = grupos[ordem]
        if valor == 0:
            continue
        if ordem == 0:
            texto = _grupo(valor)
        elif ordem == 1:
            texto = "mil" if valor == 1 else f"{_grupo(valor)} mil"
        else:
            singular, plural = ESCALAS[ordem]
            texto = f"{_grupo(valor)} {singular if valor == 1 else plural}"
        partes.append((ordem, valor, texto))

    saida = partes[0][2]
    for ordem, valor, texto in partes[1:]:
        saida += (" e " if ordem == 0 and _liga_com_e(valor) else " ") + texto
    return saida


def _precisa_de_preposicao(valor: int) -> bool:
    """R$1.000.000,00 se diz "um milhão DE reais", não "um milhão reais"."""
    return valor >= 1_000_000 and valor % 1_000_000 == 0


def reais(valor) -> str:
    centavos_totais = int((Decimal(str(valor)) * 100).quantize(Decimal("1")))
    parte_inteira, centavos = divmod(abs(centavos_totais), 100)

    partes = []
    if parte_inteira:
        if _precisa_de_preposicao(parte_inteira):
            moeda_ = " de reais"
        else:
            moeda_ = " real" if parte_inteira == 1 else " reais"
        partes.append(inteiro(parte_inteira) + moeda_)
    if centavos:
        partes.append(inteiro(centavos) + (" centavo" if centavos == 1 else " centavos"))
    if not partes:
        return "zero real"
    return " e ".join(partes)


def moeda(valor) -> str:
    """A serventia escreve "R$196.000,00", sem espaço depois do cifrão."""
    centavos_totais = int((Decimal(str(valor)) * 100).quantize(Decimal("1")))
    sinal = "-" if centavos_totais < 0 else ""
    parte_inteira, centavos = divmod(abs(centavos_totais), 100)
    # O separador de milhar sai formatado com vírgula e vira ponto ANTES de
    # entrar a vírgula dos centavos — senão o replace comeria as duas.
    milhar = f"{parte_inteira:,}".replace(",", ".")
    return f"{sinal}R${milhar},{centavos:02d}"


def moeda_com_extenso(valor) -> str:
    """R$196.000,00 (cento e noventa e seis mil reais)"""
    return f"{moeda(valor)} ({reais(valor)})"
