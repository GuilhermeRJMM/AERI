"""Leitor da matrícula: o fólio real como ele está HOJE, antes do registro.

O contrato diz o que as partes querem fazer. A matrícula diz o que o registro
permite. A conferência prévia é o confronto dos dois, e para isso é preciso ler
a matrícula como um registrador a lê — não como texto corrido, mas como uma
sequência de atos, cada um alterando o estado do imóvel.

O que este módulo devolve é esse estado: quem é o proprietário agora, como o
imóvel está descrito, o que já foi averbado e o que ainda pesa sobre ele.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import normaliza as nz
from backend.app.parser import separar_atos

# Os atos vêm separados por uma régua de traços, e cada um se abre com a espécie,
# o número e a matrícula: "R.06-34.163 - Data: 25.03.2026".
CABECALHO_DO_ATO = re.compile(
    r"\b(?P<especie>AV|R)\s*[.-]\s*(?P<numero>\d+)\s*-\s*(?P<matricula>\d[\d.]*)\s*-?\s*"
    r"(?:Data:\s*(?P<data>[\d./]+)|[^.;\n]{1,65},\s*(?P<data_ext>\d{1,2}\s+de\s+\w+\s+de\s+\d{4}))", re.I)

# Títulos que transmitem propriedade: depois deles, o dono é outro.
TRANSMISSOES = ("VENDA E COMPRA", "DOAÇÃO", "PERMUTA", "DAÇÃO EM PAGAMENTO",
                "ADJUDICAÇÃO", "ARREMATAÇÃO", "INTEGRALIZAÇÃO", "PARTILHA",
                "DIVISÃO AMIGÁVEL", "USUCAPIÃO", "INCORPORAÇÃO")

# Ônus que impedem ou condicionam nova transmissão enquanto vigentes.
ONUS = ("ALIENAÇÃO FIDUCIÁRIA", "HIPOTECA", "PENHORA", "ARRESTO", "SEQUESTRO",
        "INDISPONIBILIDADE", "USUFRUTO", "CLÁUSULA", "SERVIDÃO")

CANCELAMENTOS = ("CANCELAMENTO", "BAIXA", "LIBERAÇÃO", "QUITAÇÃO", "EXTINÇÃO")

# Lote e quadra na descrição do imóvel. Servem ao fólio e ao contrato, que
# escrevem a mesma coisa em caixas diferentes ("Lote n.º 09-A" e "LOTE N 13") —
# por isso `re.I`, e por isso moram num lugar só: quando cada lado tinha o seu,
# um deles nasceu sem tolerar a palavra do meio e o outro sem tolerar a caixa.
#
# "Lote DE TERRENO n.º 28" e "LOTE DE TERRAS N 04-A": a palavra entre o rótulo
# e o número é pulada, e o designativo precisa começar por algarismo — sem isso
# se capturava "de" como número do lote.
LOTE_NA_DESCRICAO = re.compile(
    r"\bLOTE\s+(?:DE\s+\w+\s+)?N?\.?\s*[ºo°]?\s*(\d[\w-]*)", re.I)

# A quadra às vezes é letra ("da Quadra C", no acervo), então aqui o algarismo
# não pode ser exigido — mas letra solta só vale com uma ou duas.
QUADRA_NA_DESCRICAO = re.compile(
    r"\bQUADRA\s+N?\.?\s*[ºo°]?\s*(\d[\w-]*|[A-Za-z]{1,2})(?=\W|$)", re.I)

# O CCI nem sempre tem ato próprio: pode estar na *NOTA de um ato de
# transmissão, com outro nome. Ver `designacao_cadastral`.
CCI_EM_QUALQUER_ATO = re.compile(
    r"(?:C[ÓO]DIGO\s+DE\s+CADASTRO\s+DO\s+IM[ÓO]VEL|CCI)"
    r"\s*n?\.?\s*[ºo°]?\s*([\d][\d.\-]*\d)", re.I)

# O que, no corpo de uma averbação de baixa, anuncia o ato que está sendo
# cancelado. A citação que interessa é a que vem logo depois de um destes.
VERBO_DE_CANCELAMENTO = re.compile(
    r"\b(?:cancel\w*|baix\w*|liber\w*|extin\w*|quita\w*)\b", re.I)

# "R.03", "R-3", "AV.12" — como a serventia se refere a um ato do próprio fólio.
CITACAO_DE_ATO = re.compile(r"\b([RA]V?\.?\s?-?\s?\d{1,2})\b", re.I)


@dataclass
class AtoDaMatricula:
    especie: str          # "R" ou "AV"
    numero: int
    data: str
    titulo: str
    texto: str

    @property
    def rotulo(self) -> str:
        return f"{self.especie}.{self.numero:02d}"

    @property
    def eh_transmissao(self) -> bool:
        return any(t in self.titulo for t in TRANSMISSOES)

    @property
    def eh_onus(self) -> bool:
        return any(o in self.titulo for o in ONUS)

    @property
    def eh_cancelamento(self) -> bool:
        return any(c in self.titulo for c in CANCELAMENTOS)


@dataclass
class Matricula:
    numero: str = ""
    preambulo: str = ""
    atos: list[AtoDaMatricula] = field(default_factory=list)
    texto: str = ""

    # ---------------------------------------------------------- descrição
    @property
    def descricao(self) -> str:
        """O imóvel como o preâmbulo o descreve — antes de qualquer alteração."""
        corte = re.split(r"\bPROPRIET[ÁA]RI", self.preambulo, maxsplit=1)
        return corte[0].strip()

    @property
    def area(self) -> str:
        # Só a descrição do terreno: área construída e endereço das partes não entram.
        terreno = re.split(r"\bCASA\s*:", self.descricao, maxsplit=1, flags=re.I)[0]
        casou = re.search(r"[áa]rea\s+(?:total\s+)?de\s*([\d.,]+\s*(?:m[²2]|ha))\b", terreno, re.I)
        return casou.group(1).strip() if casou else ""

    @property
    def lote_quadra(self) -> tuple[str, str]:
        """O lote e a quadra da descrição — as duas formas que o fólio usa.

        "Lote de terreno n.º 28" fazia capturar **"de"** como número do lote, e
        a conferência acusava divergência contra o lote 28 que o contrato
        trazia certo. O designativo tem de começar por algarismo (ou ser a letra
        da quadra); palavra no meio do rótulo é pulada.
        """
        lote = LOTE_NA_DESCRICAO.search(self.preambulo)
        quadra = QUADRA_NA_DESCRICAO.search(self.preambulo)
        return (lote.group(1) if lote else "", quadra.group(1) if quadra else "")

    # ------------------------------------------------------- o que já consta
    def averbacao(self, *titulos: str) -> AtoDaMatricula | None:
        """O ato de averbação com um destes títulos, se houver."""
        alvos = [nz.sem_acento(t).upper() for t in titulos]
        for ato in reversed(self.atos):
            if ato.especie != 'AV':
                continue
            titulo = nz.sem_acento(ato.titulo).upper()
            if any(alvo in titulo for alvo in alvos):
                return ato
        return None

    @property
    def cep(self) -> str:
        """O CEP do imóvel, venha da descrição ou de averbação posterior.

        Procura primeiro na `descricao` — que já para em "PROPRIETÁRI" — e não
        no preâmbulo inteiro: a qualificação das partes traz o CEP da casa
        **delas**, e ele não descreve imóvel nenhum desta matrícula.
        """
        for onde in (self.descricao,
                     getattr(self.averbacao("CÓDIGO DE ENDEREÇAMENTO POSTAL",
                                            "INCLUSÃO DE CEP"), "texto", "")):
            casou = re.search(r"CEP\s*n?\.?º?\s*(\d{2}\.?\d{3}\-?\d{3})", onde)
            if casou:
                return casou.group(1)
        # Houve a averbação, mas o número não saiu no formato esperado: dizer
        # "não averbado" seria pior que dizer só que existe.
        return "averbado" if self.averbacao("CÓDIGO DE ENDEREÇAMENTO POSTAL",
                                            "INCLUSÃO DE CEP") else ""

    @property
    def designacao_cadastral(self) -> str:
        """O CCI do imóvel. O preâmbulo pode trazê-lo, ou vir de averbação.

        CCI é o **Certificado de Cadastro Imobiliário**: a designação
        cadastral que o Município atribui ao imóvel, a mesma do IPTU. Não é
        cédula de crédito imobiliário — título de outra natureza, que não
        descreve imóvel nenhum e nada tem a ver com este campo.
        """
        casou = re.search(r"CCI\s*n?\.?º?\s*([\d.\-]+?)\.?(?:\s|$)", self.preambulo)
        if casou:
            return casou.group(1)

        ato = self.averbacao("DESIGNAÇÃO CADASTRAL")
        if ato:
            casou = re.search(
                r"(?:CCI|sob o n\.?º)\s*n?\.?º?\s*([\d.\-]+?)\.?(?:\s|$)",
                ato.texto)
            return casou.group(1) if casou else "averbada"

        # Sem ato próprio, o número pode estar escondido dentro de outro ato —
        # tipicamente na *NOTA de uma venda e compra, e com outro nome: "O
        # Código de Cadastro do Imóvel n.º 125.256". Procurar só a averbação de
        # designação cadastral fazia a ferramenta exigir a averbação de um
        # número que já constava do fólio.
        casou = CCI_EM_QUALQUER_ATO.search(self.texto)
        return casou.group(1) if casou else ""

    @property
    def encerrada(self) -> bool:
        return bool(re.search(r"ENCERRADA A PRESENTE MATR[ÍI]CULA", self.texto, re.I))

    # ----------------------------------------------------------- titularidade
    @property
    def ato_de_titularidade(self) -> AtoDaMatricula | None:
        """A última transmissão registrada. É dela que sai o dono de hoje."""
        for ato in reversed(self.atos):
            if ato.especie.upper() == "R" and ato.eh_transmissao:
                return ato
        return None

    @property
    def proprietarios(self) -> str:
        """Texto da qualificação de quem é dono agora.

        Sai do ADQUIRENTE da última transmissão; não havendo transmissão
        nenhuma, sai do PROPRIETÁRIO do preâmbulo — o imóvel ainda está com
        quem abriu a matrícula.
        """
        ato = self.ato_de_titularidade
        if ato:
            casou = re.search(r"ADQUIRENTES?:(.*?)(?:IM[ÓO]VEL:|ORIGEM:|$)",
                              ato.texto, re.S | re.I)
            if casou:
                return _limpa(casou.group(1))
        casou = re.search(r"PROPRIET[ÁA]RI[AO]S?:(.*)$", self.preambulo, re.S | re.I)
        return _limpa(casou.group(1)) if casou else ""

    @property
    def cpfs_dos_proprietarios(self) -> list[str]:
        return re.findall(r"\d{3}\.\d{3}\.\d{3}-\d{2}", self.proprietarios)

    # ---------------------------------------------------------------- ônus
    @property
    def onus_vigentes(self) -> list[AtoDaMatricula]:
        """Ônus registrados que não foram cancelados por ato posterior.

        O cancelamento se liga ao ato que ele **cancela**, e não a todo ato que
        cita. Antes bastava a averbação mencionar um registro para dá-lo por
        baixado: uma baixa que dizia "cancelar a hipoteca do R.03, constituída
        em reforço à do R.02" derrubava os dois, e a matrícula aparecia sem
        ônus nenhum com a hipoteca de primeiro grau viva.

        Agora só conta a primeira citação que vem **depois de um verbo de
        cancelamento** — é ela o objeto do ato. Não achando nenhuma, nada é
        baixado: exigência falsa o conferente descarta, gravame que passa não.
        """
        cancelados: set[str] = set()
        for ato in self.atos:
            if not ato.eh_cancelamento:
                continue
            # O corpo, sem o cabeçalho: "AV.04-99.999" traz o próprio rótulo do
            # ato, que não é objeto de cancelamento nenhum.
            corpo = CABECALHO_DO_ATO.sub(" ", ato.texto)
            for verbo in VERBO_DE_CANCELAMENTO.finditer(corpo):
                janela = corpo[verbo.end():verbo.end() + 120]
                alvo = CITACAO_DE_ATO.search(janela)
                if alvo:
                    cancelados.add(re.sub(r"[\s.]", "", alvo.group(1)).upper())

        vigentes = []
        for ato in self.atos:
            if ato.especie.upper() != "R" or not ato.eh_onus:
                continue
            chave = f"R{ato.numero}"
            if chave not in cancelados and f"R0{ato.numero}" not in cancelados:
                vigentes.append(ato)
        return vigentes

    # --------------------------------------------------------------- recortes
    def antes_do_ato(self, numero) -> "Matricula":
        """A matrícula como estava antes do ato de número `numero`.

        Existe para os testes: o acervo só tem matrículas DEPOIS do registro,
        e a conferência prévia precisa ver o fólio como estava antes. Aceita o
        número como veio — 3, "03" ou "R.03" — porque quem escreve o teste
        copia o rótulo do ato, não o inteiro.
        """
        corte = re.sub(r"\D", "", str(numero))
        if not corte:
            return self
        corte = int(corte)
        return Matricula(
            numero=self.numero,
            preambulo=self.preambulo,
            atos=[a for a in self.atos if a.numero < corte],
            texto=self.texto)


def _limpa(texto: str) -> str:
    return re.sub(r"\s+", " ", texto or "").strip()


# A matrícula quebra linha no meio de números e siglas, e achatar o texto deixa
# "013.550.841- 05" e "Brasília- DF". É artefato do PDF, não conteúdo: sem
# juntar de volta, nenhum CPF é encontrado no fólio.
HIFEN_QUEBRADO = re.compile(r"(\w)-\s+(?=[0-9A-ZÇÃÕ])")


def _junta_hifenizacao(texto: str) -> str:
    return HIFEN_QUEBRADO.sub(r"\1-", texto)


# O título do ato é a primeira sequência em CAIXA ALTA depois do cabeçalho —
# "VENDA E COMPRA.", "CÓDIGO DE ENDEREÇAMENTO POSTAL.". Exigir duas maiúsculas
# seguidas afasta "Data:" e "Protocolo", que começam com maiúscula e seguem em
# minúsculas, e os números do protocolo, que não têm letra.
TITULO_DO_ATO = re.compile(r"\b([A-ZÀ-Ý]{2,}[A-ZÀ-Ý\s/\-]{2,60}?)\s*\.")


def _titulo_do_ato(corpo: str) -> str:
    inicio = CABECALHO_DO_ATO.sub('', corpo, count=1).lstrip(' .-')
    antigo = re.match(r'(Construção(?: de Prédio)?|Edificação|Venda e Compra|Compra e Venda|Doação|Cancelamento|Hipoteca|Penhora)\s*[.:]', inicio, re.I)
    if antigo:
        return antigo.group(1).upper()
    casou = TITULO_DO_ATO.search(corpo)
    return _limpa(casou.group(1)) if casou else ""


def le(texto: str) -> Matricula:
    """Monta a matrícula a partir do texto do fólio."""
    # Compartilha a segmentação validada do AERI, mantendo os formatos históricos.
    # Cabeçalhos completos também funcionam em texto colado sem quebras de linha.
    preparado = CABECALHO_DO_ATO.sub(lambda m: '\n'+m.group(0), texto)
    blocos = separar_atos(preparado)
    linear = _junta_hifenizacao(_limpa(preparado))
    cabecalhos = list(CABECALHO_DO_ATO.finditer(linear))
    preambulo = _limpa(preparado.split(blocos[0]['texto'], 1)[0]) if blocos else linear

    numero = cabecalhos[0].group("matricula") if cabecalhos else ""
    if not numero:
        casou = re.search(r"[Mm]atr[íi]cula n?\.?º?\s*([\d.]+)", linear)
        numero = casou.group(1) if casou else ""

    atos = []
    for bloco in blocos:
        corpo = _junta_hifenizacao(_limpa(bloco['texto']))
        cabecalho = CABECALHO_DO_ATO.match(corpo)
        especie, ordinal = bloco['codigo'].split('.')
        atos.append(AtoDaMatricula(
            especie=especie,
            numero=int(ordinal),
            # O ponto final da frase entra no grupo de dígitos: "14.08.2026."
            data=((cabecalho.group('data') or cabecalho.group('data_ext') or '') if cabecalho else '').rstrip('.'),
            titulo=_titulo_do_ato(corpo),
            texto=corpo))

    return Matricula(numero=numero, preambulo=preambulo, atos=atos, texto=linear)


def le_arquivo(caminho) -> Matricula:
    from . import documento as doc
    return le(doc.abre(caminho).texto)
