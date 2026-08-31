"""Gerador da minuta: ficha -> texto do ato.

Duas regras que valem inteiras:
1. Nada é inventado. Campo exigido e ausente vira pendência com o motivo, e o
   texto sai com [[falta: ...]] no lugar — visível, nunca silencioso.
2. O que é boilerplate de lei fica no código; o que varia por contrato vem da
   ficha. Número de item de cláusula é do contrato, jamais fixado aqui.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from . import extenso as ex
from . import normaliza as nz
from .ficha import Empresa, Ficha, Pessoa

# Texto institucional da CAIXA: idêntico em todo contrato. O representante e a
# cadeia de procurações, não — esses vêm da caixa A3.
CAIXA_INSTITUCIONAL = (
    "Caixa Econômica Federal, instituição financeira constituída sob a forma de "
    "empresa pública, pessoa jurídica de direito privado, criada pelo Decreto-Lei "
    "n.º 759/1969, regendo-se pelo Estatuto vigente na data da contratação, com "
    "sede em Brasília-DF no Setor Bancário Sul, Quadra 04, Lotes 3/4, inscrita no "
    "CNPJ/MF sob n.º 00.360.305/0001-04"
)

# Exigido pelo §5º do art.61 da Lei 4.380/1964, que dá ao instrumento particular
# o caráter de escritura pública.
PREAMBULO_TITULO = (
    "Contrato por Instrumento Particular, com caráter de Escritura Pública, na "
    "forma do §5º do art.61 da Lei n.º 4.380/1964,"
)

NOMES_DOCUMENTO = {
    # A serventia escreve "CNH registro n.º" — a forma sem "registro" aparece
    # uma vez só, no R.06 da 34.163, e é a exceção.
    "CNH": "Carteira Nacional de Habilitação CNH registro",
    "RG": "Carteira de Identidade RG",
    "PROFISSIONAL": "Carteira de Identidade Profissional",
}


@dataclass
class Ato:
    texto: str
    pendencias: list


def _flexao(pessoa: Pessoa, masculino: str, feminino: str,
            coletor: nz.Coletor, dono: str) -> str:
    if pessoa.sexo == "F":
        return feminino
    if pessoa.sexo == "M":
        return masculino
    coletor.anota(
        f"sexo ({dono})",
        "o contrato da CAIXA não traz o campo, e dele dependem as concordâncias "
        'do ato ("portador/portadora", "inscrito/inscrita") e a flexão da '
        "profissão. Confirme antes de registrar.")
    return masculino


def _documento(pessoa: Pessoa, coletor: nz.Coletor, dono: str) -> str:
    if not pessoa.documento or not pessoa.documento.numero:
        return coletor.falta(f"documento ({dono})", "não consta do contrato.",
                             "documento de identidade")
    tipo = (pessoa.documento.tipo or "").upper()
    if tipo in NOMES_DOCUMENTO:
        nome = NOMES_DOCUMENTO[tipo]
    else:
        coletor.confirmar(f"documento ({dono})",
                          f'tipo "{tipo}" não é CNH nem RG; confira a redação.')
        nome = tipo
    orgao = nz.orgao_expedidor(pessoa.documento.orgao, coletor, dono)
    return f"{nome} n.º {pessoa.documento.numero}-{orgao}"


def _profissao(pessoa: Pessoa, coletor: nz.Coletor, dono: str) -> str:
    """Decisão da serventia (24/08/2026): copiar fielmente a do contrato.

    O acervo mostra a serventia substituindo a descrição do CBO pela profissão
    declarada, mas isso não é dedutível de nada — e pedir confirmação a cada
    pessoa enchia a tela sem ajudar. Agora só se manifesta o que o dicionário
    sabe: o acento que a CAIXA come. O resto passa como veio, e quem quiser
    trocar troca no campo."""
    bruta = nz.profissao(pessoa.profissao, coletor, dono)
    return nz.flexiona_profissao(bruta, pessoa.sexo)


def _cpf(pessoa: Pessoa, coletor: nz.Coletor, dono: str) -> str:
    formatado = nz.cpf(pessoa.cpf, coletor, dono)
    if formatado is None:
        return coletor.falta(f"CPF ({dono})",
                             "ausente ou com número de dígitos inválido.", "CPF")
    return formatado


def _miolo(pessoa: Pessoa, coletor: nz.Coletor, dono: str) -> str:
    """Profissão, documento e CPF — a parte que é de cada pessoa, mesmo no casal."""
    return ", ".join([
        _profissao(pessoa, coletor, dono),
        _flexao(pessoa, "portador", "portadora", coletor, dono) + " da " +
        _documento(pessoa, coletor, dono),
        _flexao(pessoa, "inscrito", "inscrita", coletor, dono) +
        " no CPF/MF sob o n.º " + _cpf(pessoa, coletor, dono),
    ])


ESTADOS_CIVIS = {
    "solteiro": ("solteiro", "solteira"),
    "casado": ("casado", "casada"),
    "divorciado": ("divorciado", "divorciada"),
    "viúvo": ("viúvo", "viúva"),
    "separado": ("separado", "separada"),
}


def _estado_civil(pessoa: Pessoa, coletor: nz.Coletor, dono: str) -> str:
    civil = (pessoa.estado_civil or "").lower()
    if civil in ESTADOS_CIVIS:
        masculino, feminino = ESTADOS_CIVIS[civil]
        return _flexao(pessoa, masculino, feminino, coletor, dono)
    if civil:
        coletor.confirmar(f"estado civil ({dono})",
                          f'"{civil}" não está na tabela de flexões; confira a '
                          f"concordância no texto.")
        return civil
    return coletor.falta(f"estado civil ({dono})", "não consta do contrato.",
                         "estado civil")


def qualifica_sozinho(pessoa: Pessoa, coletor: nz.Coletor, dono: str,
                      endereco_comercial: bool = False) -> str:
    """Nome, nacionalidade, estado civil, profissão, documento, CPF, endereço."""
    if pessoa.nome:
        nome = nz.nome_proprio(pessoa.nome)
        nz.confere_acentos(pessoa.nome, coletor, dono)
    else:
        nome = coletor.falta(f"nome ({dono})", "não consta do contrato.", "nome")

    partes = [
        nome,
        _flexao(pessoa, "brasileiro", "brasileira", coletor, dono),
        _estado_civil(pessoa, coletor, dono),
        _miolo(pessoa, coletor, dono),
    ]

    endereco = nz.endereco(pessoa.endereco, coletor, dono)
    if endereco_comercial:
        partes.append(f"com endereço comercial na {endereco}")
    else:
        partes.append(
            _flexao(pessoa, "residente e domiciliado", "residente e domiciliada",
                    coletor, dono) + f" na {endereco}")
    return ", ".join(partes)


def qualifica_casal(pessoa: Pessoa, coletor: nz.Coletor, dono: str) -> str:
    """O casal é um bloco só: cada um com sua profissão, documento e CPF, e ao
    final — no plural e uma vez só — nacionalidade, regime de bens e endereço.

    Note que não há vírgula antes de "e seu cônjuge": é como a serventia escreve.
    """
    conjuge = pessoa.conjuge
    nz.confere_acentos(pessoa.nome, coletor, dono)
    nz.confere_acentos(conjuge.nome, coletor, f"{dono} (cônjuge)")
    primeiro = nz.nome_proprio(pessoa.nome) + ", " + _miolo(pessoa, coletor, dono)
    segundo = (nz.nome_proprio(conjuge.nome) + ", " +
               _miolo(conjuge, coletor, f"{dono} (cônjuge)"))

    if pessoa.regime_bens:
        regime = f"casados sob o regime da {pessoa.regime_bens}"
        if pessoa.marco_lei:
            regime += f" {pessoa.marco_lei}"
    else:
        regime = coletor.falta(
            f"regime de bens ({dono})",
            "o contrato não declarou o regime, e ele muda a titularidade.",
            "regime de bens")

    endereco = nz.endereco(pessoa.endereco, coletor, dono)

    # O cônjuge que comparece "como interveniente anuente" outorga o
    # consentimento do art. 1.647 do Código Civil e NÃO transmite. Sem dizê-lo,
    # o ato o qualificava como se fosse cotitular — e o fólio, onde ele não
    # consta, passaria a divergir do que o registro afirma.
    rotulo = ("e seu cônjuge, que comparece neste ato como interveniente "
              "anuente," if conjuge.anuente else "e seu cônjuge")
    return (f"{primeiro} {rotulo} {segundo}, brasileiros, {regime}, "
            f"residentes e domiciliados na {endereco}")


def qualifica_empresa(empresa: Empresa, coletor: nz.Coletor, dono: str) -> str:
    """A qualificação de pessoa jurídica é outra frase, não a de pessoa com
    campos trocados. Calibrada sobre o R.03 da 38.963.

    Três blocos, separados por ponto e vírgula:
      1. quem é — razão social, sede e foro, CNPJ;
      2. quem a representa e com que poderes;
      3. a prova dos poderes — ato constitutivo e certidão da Junta.

    O bloco 3 **não vem do contrato da CAIXA**: sai da certidão específica que a
    serventia exige à parte. Sem ela, o ato não fecha.
    """
    razao = (nz.nome_proprio(empresa.razao_social) if empresa.razao_social
             else coletor.falta(f"razão social ({dono})",
                                "não consta do contrato.", "razão social"))
    # "Ltda" leva ponto: é abreviatura. E "Imobiliários" não é partícula.
    razao = re.sub(r"\bLtda\.?$", "Ltda.", razao)

    cnpj = nz.cnpj(empresa.cnpj)
    if not cnpj:
        cnpj = coletor.falta(f"CNPJ ({dono})",
                             "ausente ou com número de dígitos inválido.", "CNPJ")

    identificacao = (
        f"{razao}, pessoa jurídica de direito privado, com sede e foro na "
        f"{nz.endereco(empresa.endereco, coletor, dono)}, "
        f"inscrita no CNPJ/MF sob o n.º {cnpj}")

    if empresa.representante:
        representacao = ("; no ato representada por " +
                         qualifica_sozinho(empresa.representante, coletor,
                                           f"representante de {dono}"))
    else:
        representacao = "; " + coletor.falta(
            f"representante ({dono})",
            "o contrato não disse quem assina pela empresa.", "representante")

    ato = empresa.ato_constitutivo_data or coletor.falta(
        f"ato constitutivo ({dono})",
        "a data não está no contrato da CAIXA — sai da certidão específica da "
        "Junta Comercial, que precisa ser apresentada.", "data do ato constitutivo")
    juceg_data = empresa.juceg_data or coletor.falta(
        f"registro na Junta ({dono})", "a data do registro não foi lida.",
        "data do registro na Junta")
    juceg_numero = empresa.juceg_numero or coletor.falta(
        f"NIRE ({dono})", "o número do registro na Junta não foi lido.", "NIRE")

    prova = (f", nos termos do Ato Constitutivo, datado de {ato}, devidamente "
             f"registrado na Junta Comercial do Estado de Goiás - JUCEG em "
             f"{juceg_data}, sob o n.º {juceg_numero}")

    emissao = empresa.certidao_emissao or coletor.falta(
        f"certidão da JUCEG ({dono})",
        "a certidão específica da Junta não vem do contrato e precisa ser "
        "apresentada; sem ela não se prova quem representa a empresa hoje.",
        "emissão da certidão")
    arquivamento = empresa.certidao_arquivamento or "[[falta: último arquivamento]]"
    numero_certidao = empresa.certidao_numero or "[[falta: n.º da certidão]]"

    certidao = (f"; Certidão Específica da JUCEG emitida em {emissao}, com "
                f"último arquivamento datado de {arquivamento}, sob o n.º "
                f"{numero_certidao}")

    return identificacao + representacao + prova + certidao


def qualifica_parte(pessoas: list, coletor: nz.Coletor,
                    dono: str) -> tuple[str, bool]:
    """Devolve o texto da parte e se o rótulo vai no plural.

    Um casal é uma parte só, sem numeração. Duas pessoas que não são cônjuges
    saem numeradas: "1)- Fulano...; e, 2)- Beltrana...".
    """
    if not pessoas:
        return coletor.falta(dono, "nenhuma pessoa informada.", dono), False

    if len(pessoas) == 1:
        return _qualifica_uma(pessoas[0], coletor, dono), pessoas[0].eh_casal

    blocos = []
    for indice, parte in enumerate(pessoas, start=1):
        texto = _qualifica_uma(parte, coletor, f"{dono} {indice}")
        blocos.append(f"{indice})- {texto}")
    return "; e, ".join(blocos), True


def _qualifica_uma(parte, coletor: nz.Coletor, dono: str) -> str:
    if isinstance(parte, Empresa):
        return qualifica_empresa(parte, coletor, dono)
    if parte.eh_casal:
        return qualifica_casal(parte, coletor, dono)
    return qualifica_sozinho(parte, coletor, dono)


def _forma_do_titulo(ficha: Ficha, coletor: nz.Coletor) -> str:
    contrato = ficha.contrato
    if not contrato.descricao:
        return coletor.falta("forma do título",
                             "o cabeçalho do contrato não foi lido.",
                             "forma do título")
    numero = contrato.numero or coletor.falta(
        "número do contrato", "não foi lido.", "número do contrato")
    data = contrato.data or coletor.falta(
        "data do contrato", "não foi lida.", "data do contrato")
    return f"{PREAMBULO_TITULO} {contrato.descricao}, n.º {numero}, datado de {data}"


def _valor_da_venda(ficha: Ficha, coletor: nz.Coletor) -> str:
    """A frase do valor, que muda de forma conforme a família do contrato.

    Na família comum o ato escreve o valor por extenso e detalha a composição.
    Na família terreno-com-obras ele registra **só o valor do terreno** — o
    resto é construção, que ainda não existe e não se transmite — e usa a forma
    curta "pagos mediante financiamento", sem extenso. Calibrado sobre o R.03
    da 38.963.
    """
    v = ficha.valores
    proximo = ficha.matricula.proximo_ato or coletor.falta(
        "ato seguinte", "o R. da alienação fiduciária não foi apontado.",
        "ato seguinte")

    if v.tem_construcao:
        return (f"{ex.moeda_com_extenso(v.terreno)}, pagos mediante "
                f"financiamento concedido pela CAIXA, conforme {proximo} seguinte")

    return (f"{ex.moeda_com_extenso(v.total)}, integralizados da seguinte forma: "
            f"{_composicao_do_valor(ficha, coletor)}")


def _composicao_do_valor(ficha: Ficha, coletor: nz.Coletor) -> str:
    """Parcela zerada não é escrita: há contrato sem FGTS e sem desconto."""
    v = ficha.valores
    proximo = ficha.matricula.proximo_ato or coletor.falta(
        "ato seguinte", "o R. da alienação fiduciária não foi apontado.",
        "ato seguinte")

    itens = []
    if v.recursos_proprios > 0:
        itens.append(f"{ex.moeda(v.recursos_proprios)} de recursos próprios")
    if v.fgts > 0:
        itens.append(f"{ex.moeda(v.fgts)} de recursos da conta vinculada do FGTS")
    if v.desconto_fgts > 0:
        itens.append(f"{ex.moeda(v.desconto_fgts)} de desconto concedido pelo FGTS/União")
    if v.financiamento > 0:
        itens.append(f"{ex.moeda(v.financiamento)} mediante financiamento concedido "
                     f"pela CAIXA, conforme {proximo} seguinte")

    soma = v.recursos_proprios + v.fgts + v.desconto_fgts + v.financiamento
    if round(soma, 2) != round(v.total, 2):
        coletor.anota("composição do valor",
                      f"as parcelas somam {ex.moeda(soma)} e o contrato declara "
                      f"{ex.moeda(v.total)}.")

    if not itens:
        return coletor.falta("composição do valor",
                             "nenhuma parcela foi lida (caixa B4).",
                             "composição do valor")
    if len(itens) == 1:
        return itens[0]
    return "; ".join(itens[:-1]) + "; e, " + itens[-1]


# Campos sem nenhuma redundância interna: um número pequeno, solto, que não tem
# dígito verificador nem repetição em outro lugar do contrato. Se o OCR errar um
# algarismo aqui, nada acusa — nem o sistema, nem quem lê o ato depois. Por isso,
# quando o texto veio de OCR, estes voltam para o conferente.
SEM_REDUNDANCIA = {
    "contrato.item_outorga": "item da outorga de procurações",
    "contrato.item_reajuste": "item do reajuste",
}


def _confere_o_que_o_ocr_nao_defende(ficha: Ficha, coletor: nz.Coletor) -> None:
    if "OCR" not in ficha.origens.get("_natureza", ""):
        return
    for caminho, rotulo in SEM_REDUNDANCIA.items():
        secao, campo = caminho.split(".")
        valor = getattr(getattr(ficha, secao), campo, "")
        if valor:
            coletor.confirmar(
                rotulo,
                f'lido por OCR como "{valor}". Número de cláusula não tem dígito '
                f"verificador nem se repete no contrato: se o OCR trocar um "
                f"algarismo, nada acusa. Confira na imagem.",
                sugestao=valor)


def _valor_da_operacao(ficha: Ficha, coletor: nz.Coletor) -> str:
    """Na família terreno-com-obras o ato abre a alienação declarando o valor da
    operação inteira — terreno mais construção — antes da dívida, e **discrimina
    como ela foi integralizada**. Na família comum essa linha não existe.

    Redação calibrada sobre o R.04 da 34.274, que é o único exemplo registrado
    desta linha. Ele difere do R.03 da família comum em três pontos, e os três
    foram seguidos: as parcelas vêm **com extenso**, o financiamento vem
    **primeiro**, e não há "conforme R.xx seguinte" — o ato já é o do
    financiamento, não há a que remeter.

    A discriminação importa mais aqui do que na família comum: lá a composição
    está no R. de venda e compra. Aqui esse ato traz só o valor do terreno, e
    sem esta linha os recursos próprios não constam de lugar nenhum da matrícula
    — foi o que aconteceu no R.04 da 38.963. Decisão da serventia (25/08/2026).
    """
    v = ficha.valores
    if not v.tem_construcao:
        return ""

    parcelas = []
    if v.financiamento > 0:
        parcelas.append(f"{ex.moeda_com_extenso(v.financiamento)} mediante "
                        f"financiamento concedido pela CAIXA")
    if v.obra > 0:
        parcelas.append(f"{ex.moeda_com_extenso(v.obra)} de recursos próprios "
                        f"aplicados/a aplicar na obra")
    if v.recursos_proprios > 0:
        parcelas.append(f"{ex.moeda_com_extenso(v.recursos_proprios)} de "
                        f"recursos próprios")
    if v.fgts > 0:
        parcelas.append(f"{ex.moeda_com_extenso(v.fgts)} de recursos da conta "
                        f"vinculada do FGTS")
    if v.desconto_fgts > 0:
        parcelas.append(f"{ex.moeda_com_extenso(v.desconto_fgts)} de desconto "
                        f"concedido pelo FGTS/União")

    soma = v.financiamento + v.obra + v.recursos_proprios + v.fgts + v.desconto_fgts
    if parcelas and round(soma, 2) != round(v.total, 2):
        coletor.anota("composição da operação",
                      f"as parcelas somam {ex.moeda(soma)} e o contrato declara "
                      f"{ex.moeda(v.total)}.")

    if not parcelas:
        return (f"VALOR DA OPERAÇÃO: {ex.moeda_com_extenso(v.total)}, "
                f"integralizados da seguinte forma: "
                + coletor.falta("composição da operação",
                                "nenhuma parcela foi lida (caixa B4).",
                                "composição da operação") + ". ")

    if len(parcelas) == 1:
        composicao = parcelas[0]
    elif len(parcelas) == 2:
        # O R.04 da 34.274 separa as duas com " e," — sem ponto e vírgula.
        composicao = f"{parcelas[0]} e, {parcelas[1]}"
    else:
        # Três ou mais não há no acervo desta família; segue-se a pontuação que
        # a serventia usa quando há três parcelas no R.03 (38.807).
        composicao = "; ".join(parcelas[:-1]) + "; e, " + parcelas[-1]

    return (f"VALOR DA OPERAÇÃO: {ex.moeda_com_extenso(v.total)}, "
            f"integralizados da seguinte forma: {composicao}. ")


def _prazo(ficha: Ficha, coletor: nz.Coletor) -> str:
    """Com obras, o prazo é dois: o da construção e o da amortização."""
    f = ficha.financiamento
    if f.prazo_construcao:
        amortizacao = f.prazo_meses or coletor.falta(
            "prazo de amortização", "não lido (caixa B8.1).", "amortização")
        return (f"PRAZO TOTAL EM MESES: Construção: {f.prazo_construcao}; "
                f"Amortização: {amortizacao}.")
    prazo = f.prazo_meses or coletor.falta("prazo", "não lido (caixa B8).", "prazo")
    return f"PRAZO EM MESES: {prazo}."


def _cadeia_de_procuracoes(ficha: Ficha, coletor: nz.Coletor) -> str:
    procuracoes = ficha.credora.procuracoes
    if not procuracoes:
        return coletor.falta("procurações",
                             "a cadeia do representante da CAIXA não foi lida "
                             "(caixa A3).", "procurações")
    itens = []
    for item in procuracoes:
        # "Procuração lavrada", mas "Substabelecimento lavrado": o particípio
        # concorda com a espécie do ato, não com quem o lavrou.
        lavrado = "lavrada" if item.especie == "Procuração" else "lavrado"
        itens.append(f"{item.especie} {lavrado} em {item.data}, às fls. "
                     f"{item.folhas}, Livro {item.livro}, pelo "
                     f"{nz.serventia(item.serventia, coletor)}")
    if len(itens) == 1:
        return itens[0]
    return "; ".join(itens[:-1]) + "; e, " + itens[-1]


# ---------------------------------------------------------------- venda e compra
def venda_e_compra(ficha: Ficha) -> Ato:
    coletor = nz.Coletor()
    _confere_o_que_o_ocr_nao_defende(ficha, coletor)

    transmitentes, plural_t = qualifica_parte(ficha.vendedores, coletor, "transmitente")
    adquirentes, plural_a = qualifica_parte(ficha.compradores, coletor, "adquirente")

    origem = ficha.matricula.origem or coletor.falta(
        "origem", "não vem do contrato: é o ato anterior da matrícula, e precisa "
        "ser apontado.", "origem")

    texto = (
        "VENDA E COMPRA. "
        f"{'TRANSMITENTES' if plural_t else 'TRANSMITENTE'}: {transmitentes}. "
        f"{'ADQUIRENTES' if plural_a else 'ADQUIRENTE'}: {adquirentes}. "
        "IMÓVEL: O descrito na matrícula. "
        f"ORIGEM: {origem}. "
        f"FORMA DO TÍTULO: {_forma_do_titulo(ficha, coletor)}. "
        f"VALOR DA VENDA E COMPRA: {_valor_da_venda(ficha, coletor)}."
    )
    return Ato(texto, coletor.itens)


# ------------------------------------------------------------ alienação fiduciária
def alienacao_fiduciaria(ficha: Ficha) -> Ato:
    coletor = nz.Coletor()
    _confere_o_que_o_ocr_nao_defende(ficha, coletor)
    f = ficha.financiamento
    devedores = ficha.compradores

    qualificacao, plural = qualifica_parte(devedores, coletor, "devedor")

    # Só há feminino plural quando TODAS são mulheres — um homem no grupo já
    # devolve o masculino, que em português é a forma de gênero misto.
    fisicas = [p for d in devedores if not isinstance(d, Empresa)
               for p in ([d, d.conjuge] if d.conjuge else [d])]
    so_mulheres = bool(fisicas) and len(fisicas) == len(devedores) and         all(p.sexo == "F" for p in fisicas)

    if plural and so_mulheres:
        rotulo, sujeito, verbo = ("DEVEDORAS/FIDUCIANTES", "As devedoras fiduciantes",
                                  "transferem")
    elif plural:
        rotulo, sujeito, verbo = ("DEVEDORES/FIDUCIANTES", "Os devedores fiduciantes",
                                  "transferem")
    elif so_mulheres:
        rotulo, sujeito, verbo = ("DEVEDORA/FIDUCIANTE", "A devedora fiduciante",
                                  "transfere")
    else:
        rotulo, sujeito, verbo = ("DEVEDOR/FIDUCIANTE", "O devedor fiduciante",
                                  "transfere")

    if ficha.credora.representante:
        representacao = (
            ", representada no ato do contrato por " +
            qualifica_sozinho(ficha.credora.representante, coletor,
                              "representante da CAIXA", endereco_comercial=True) +
            "; conforme " + _cadeia_de_procuracoes(ficha, coletor))
    else:
        representacao = ""
        coletor.anota("representante da CAIXA", "não foi lido (caixa A3).")

    j = f.juros
    def taxa(valor, rotulo):
        formatada = nz.percentual(valor or "")
        if not re.fullmatch(r"\d+(?:,\d+)?", formatada):
            return coletor.falta(rotulo, "não identificada com segurança na coluna B9.4 (Taxa Contratada).", rotulo)
        return formatada + "%"
    texto = (
        "ALIENAÇÃO FIDUCIÁRIA. "
        f"{rotulo}: {qualificacao}. "
        f"CREDORA/FIDUCIÁRIA: {CAIXA_INSTITUCIONAL}{representacao}. "
        f"FORMA DO TÍTULO: {_forma_do_titulo(ficha, coletor)}. "
        f"PROPRIEDADE FIDUCIÁRIA: {sujeito}, pelo instrumento ora registrado, "
        f"{verbo} neste ato à credora fiduciária, a propriedade resolúvel do "
        "imóvel objeto desta matrícula, nos termos da Lei Federal n.º 9.514/1997, "
        "mediante as condições seguintes: "
        f"{_valor_da_operacao(ficha, coletor)}"
        f"VALOR TOTAL DA DÍVIDA: {ex.moeda_com_extenso(f.divida)}. "
        f"VALOR DA GARANTIA FIDUCIÁRIA: {ex.moeda_com_extenso(f.garantia)}. "
        f"SISTEMA DE AMORTIZAÇÃO: {f.amortizacao or coletor.falta('amortização', 'não lida (caixa B2).', 'amortização')}. "
        f"{_prazo(ficha, coletor)} "
        # Os dois atos do acervo pontuam isto de jeitos diferentes, e um deles se
        # contradiz dentro de si ("a.a;" e depois "a.a.;"). O gerador usa uma
        # forma só — a divergência tipográfica fica documentada no teste.
        f"Taxa de Juros Contratada: Nominal: {taxa(j.nominal_ao_ano, 'taxa nominal anual')} a.a; "
        f"Efetiva: {taxa(j.efetiva_ao_ano, 'taxa efetiva anual')} a.a; "
        f"Efetiva: {taxa(j.efetiva_ao_mes, 'taxa efetiva mensal')} a.m.; "
        f"Encargo mensal inicial total: "
        f"{ex.moeda(f.encargo_mensal_total) if f.encargo_mensal_total else coletor.falta('encargo mensal', 'não lido (caixa B10.1).', 'encargo mensal')}; "
        f"Vencimento do Primeiro Encargo Mensal: "
        f"{f.primeiro_vencimento or coletor.falta('primeiro vencimento', 'não lido (caixa B11).', 'primeiro vencimento')}; "
        f"Reajuste dos Encargos: De acordo com o item "
        f"{ficha.contrato.item_reajuste or coletor.falta('item do reajuste', 'não lido (caixa B12).', 'item do reajuste')}"
        " do contrato. "
        "OUTORGA DE PROCURAÇÕES: em conformidade com o item "
        f"{ficha.contrato.item_outorga or coletor.falta('item da outorga', 'precisa ser lido do corpo do contrato — o número muda conforme a versão do formulário.', 'item da outorga')}"
        " do contrato, todos os devedores se declaram solidariamente responsáveis "
        "pelas obrigações assumidas perante a credora fiduciária e constituíram-se "
        "procuradores recíprocos, até o cumprimento, com poderes irrevogáveis para "
        "receber citações, notificações, intimações, inclusive de penhora, leilão "
        "ou praça, dentre outros. Obrigam-se as partes pelo cumprimento de todas as "
        "demais cláusulas e condições constantes do contrato, do qual uma via fica "
        "arquivada nesta Serventia."
    )

    if f.garantia and ficha.valores.total and round(f.garantia, 2) != round(ficha.valores.total, 2):
        coletor.anota("garantia fiduciária",
                      f"o valor da garantia ({ex.moeda(f.garantia)}) difere do valor "
                      f"da venda e compra ({ex.moeda(ficha.valores.total)}); "
                      "confirme nas caixas B4 e B7.")

    return Ato(texto, coletor.itens)
