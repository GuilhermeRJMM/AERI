"""A ficha: o que o sistema extrai do contrato, antes de virar texto de ato.

Existe separada do extrator e do gerador de propósito. O extrator preenche, o
conferente corrige na tela, o gerador escreve. Nenhum dos três conhece os
outros dois.

Cada campo carrega de onde veio (`origens`), porque a tela mostra a caixa do
contrato ao lado do valor — é isso que faz o "semi" ser conferência de verdade
em vez de confiança cega.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Documento:
    tipo: str = ""       # CNH | RG
    numero: str = ""
    orgao: str = ""


@dataclass
class Pessoa:
    """Parte pessoa física.

    `tipo` existe para a tela e o JSON distinguirem de `Empresa` sem precisar
    inspecionar a classe."""
    tipo: str = "fisica"
    nome: str = ""
    profissao: str = ""
    documento: Documento = field(default_factory=Documento)
    cpf: str = ""
    endereco: str = ""
    nascimento: str = ""

    # O contrato NÃO traz o sexo, e dele dependem todas as concordâncias do ato.
    # Fica vazio até o conferente decidir; o gerador acusa enquanto estiver.
    sexo: str = ""

    estado_civil: str = ""   # solteiro | casado
    regime_bens: str = ""    # "comunhão parcial de bens", "comunhão universal de bens"
    marco_lei: str = ""      # "posteriormente ao advento da Lei Federal n.º 6.515/77"

    # Preenchido quando o contrato diz "e seu cônjuge": os dois são qualificados
    # num bloco só, com nacionalidade, regime e endereço no plural, ao final.
    conjuge: "Pessoa | None" = None
    # O cônjuge que comparece "como interveniente anuente" outorga o
    # consentimento do art. 1.647 do Código Civil e NÃO transmite. O ato precisa
    # dizer isso: sem a marca, ele saía qualificado como se fosse cotitular.
    anuente: bool = False

    @property
    def eh_casal(self) -> bool:
        return self.conjuge is not None


@dataclass
class Empresa:
    """Parte pessoa jurídica.

    A qualificação registral de uma empresa não é a de uma pessoa com outros
    campos: é outra frase inteira — sede e foro, CNPJ, quem a representa e com
    que poderes, e a prova de que esses poderes existem.

    Boa parte dessa prova **não está no contrato da CAIXA**: a data do ato
    constitutivo e a certidão específica da Junta vêm de documento próprio, que
    a serventia exige à parte. Esses campos ficam pendentes.
    """
    tipo: str = "juridica"
    razao_social: str = ""
    cnpj: str = ""
    endereco: str = ""                  # sede e foro
    representante: "Pessoa | None" = None
    clausula_representacao: str = ""    # "cláusula sexta do Contrato Social"

    # do contrato
    juceg_numero: str = ""              # NIRE
    juceg_data: str = ""                # "em sessão de 07/02/2018"

    # NÃO vêm do contrato: saem da certidão específica da Junta Comercial
    ato_constitutivo_data: str = ""
    certidao_emissao: str = ""
    certidao_arquivamento: str = ""
    certidao_numero: str = ""

    @property
    def eh_casal(self) -> bool:
        return False


@dataclass
class Procuracao:
    especie: str = "Substabelecimento"   # Procuração | Substabelecimento
    data: str = ""
    folhas: str = ""
    livro: str = ""
    serventia: str = ""


@dataclass
class Credora:
    representante: Pessoa | None = None
    procuracoes: list[Procuracao] = field(default_factory=list)


@dataclass
class Contrato:
    numero: str = ""
    data: str = ""
    modelo: str = ""        # MO30173Av120 — identifica a versão do formulário
    descricao: str = ""     # "de Venda e Compra de Imóvel Residencial, mútuo ..."
    modalidade: str = ""    # AQUISIÇÃO DE IMÓVEL NOVO | USADO
    item_outorga: str = ""  # lido do corpo, nunca fixado no código
    item_reajuste: str = ""


@dataclass
class Valores:
    total: float = 0.0
    recursos_proprios: float = 0.0
    fgts: float = 0.0
    desconto_fgts: float = 0.0
    financiamento: float = 0.0

    # Só na família terreno-com-obras. O contrato dá o valor da operação inteira
    # (terreno mais construção), mas a venda e compra transmite SÓ O TERRENO —
    # e é o valor do terreno que o R. de venda e compra registra. Confundir os
    # dois faria a matrícula declarar uma transmissão de valor errado.
    terreno: float = 0.0
    obra: float = 0.0

    @property
    def tem_construcao(self) -> bool:
        return self.terreno > 0


@dataclass
class Juros:
    nominal_ao_ano: str = ""
    efetiva_ao_ano: str = ""
    efetiva_ao_mes: str = ""


@dataclass
class Financiamento:
    divida: float = 0.0
    garantia: float = 0.0
    amortizacao: str = ""
    prazo_meses: str = ""
    prazo_construcao: str = ""      # só na família terreno-com-obras
    juros: Juros = field(default_factory=Juros)
    encargo_mensal_total: float = 0.0
    primeiro_vencimento: str = ""


@dataclass
class Matricula:
    """Nada disto vem do contrato: sai do fólio real e do ITBI."""
    numero: str = ""
    origem: str = ""            # "O R.02 desta matrícula", "Abertura da presente matrícula"
    proximo_ato: str = ""       # o R. da alienação fiduciária, citado na venda e compra


@dataclass
class Ficha:
    contrato: Contrato = field(default_factory=Contrato)
    # Pessoa ou Empresa — o vendedor costuma ser construtora em loteamento novo.
    vendedores: list = field(default_factory=list)
    compradores: list = field(default_factory=list)
    credora: Credora = field(default_factory=Credora)
    valores: Valores = field(default_factory=Valores)
    financiamento: Financiamento = field(default_factory=Financiamento)
    matricula: Matricula = field(default_factory=Matricula)

    # caminho de campo -> caixa do contrato de onde saiu ("A1", "B4", "corpo")
    origens: dict[str, str] = field(default_factory=dict)
    # caminho de campo -> texto como veio, para a tela mostrar ao lado
    brutos: dict[str, str] = field(default_factory=dict)

    def de_onde(self, caminho: str) -> str:
        return self.origens.get(caminho, "")
