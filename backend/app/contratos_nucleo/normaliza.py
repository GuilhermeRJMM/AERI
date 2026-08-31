"""Normalizadores.

A CAIXA grava em CAIXA ALTA, sem acento e com endereço abreviado; o registro
escreve por extenso e acentuado. Cada regra aqui nasceu de par real
(contrato -> ato registrado), nunca de exemplo inventado.

Nada é adivinhado: o que não se sabe converter vira pendência.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

# Logradouros e bairros de Morrinhos, do Cadastro dos Correios (DNE) que a
# serventia forneceu. Gerado por `tools/gera_logradouros.py` — não editar à mão.
from .logradouros_morrinhos import BAIRROS, LOGRADOUROS

MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
         "agosto", "setembro", "outubro", "novembro", "dezembro"]

# Partículas que ficam minúsculas no meio do nome.
PARTICULAS = {"da", "das", "de", "do", "dos", "e"}

TIPOS_LOGRADOURO = {
    "R": "Rua", "RUA": "Rua",
    "AV": "Avenida", "AVE": "Avenida", "AVENIDA": "Avenida",
    "TV": "Travessa", "TRAV": "Travessa", "TRAVESSA": "Travessa",
    "PC": "Praça", "PRACA": "Praça", "PRAÇA": "Praça",
    "ROD": "Rodovia", "RODOVIA": "Rodovia",
    "AL": "Alameda", "ALAMEDA": "Alameda",
    "VL": "Viela", "VIELA": "Viela",
    "CH": "Chácara", "CHACARA": "Chácara", "CHÁCARA": "Chácara",
}

# Profissões vêm do CBO, sem acento e em caixa alta. O dicionário cresce com o
# acervo; o que não estiver nele vira pendência em vez de palpite.
PROFISSOES = {
    "TRABALHADOR DE FABRICACAO E PREPARACAO DE ALIMENTOS E BEBIDA":
        "trabalhador de fabricação e preparação de alimentos e bebida",
    "AUXILIAR DE ESCRITORIO E ASSEMELHADOS": "auxiliar de escritório e assemelhados",
    "CONSERTADOR DE APARELHO ELETRONICO ELETRODOMESTICO":
        "consertador de aparelho eletrônico e eletrodoméstico",
    "ADMINISTRADOR": "administrador",
    "ECONOMIARIO": "economiário",
    "ECONOMIARIA": "economiária",
    "BANCARIO": "bancário",
    "PROTETICO": "protético",
    "TRATORISTA": "tratorista",
    "LAVRADOR": "lavrador",
    "COMERCIANTE": "comerciante",
    "DO LAR": "do lar",
    "APOSENTADO": "aposentado",
    "APOSENTADA": "aposentada",
    "PROFESSOR": "professor",
    "PROFESSORA": "professora",
    "MOTORISTA": "motorista",
    "PEDREIRO": "pedreiro",
    "AUTONOMO": "autônomo",
    "AUTONOMA": "autônoma",
    "SERVIDOR PUBLICO": "servidor público",
    "SERVIDORA PUBLICA": "servidora pública",
}


# Nomes próprios que a CAIXA grava sem acento. A sugestão é OFERECIDA na tela;
# o sistema não a aplica sozinho, porque acento errado em nome qualifica outra
# pessoa. Cresce com o acervo, como o dicionário de profissões.
NOMES_ACENTUADOS = {
    "ROGERIO": "Rogério", "GONCALVES": "Gonçalves", "JOSE": "José",
    "ANTONIO": "Antônio", "JOAO": "João", "MARCIA": "Márcia", "FABIO": "Fábio",
    "GLORIA": "Glória", "LUIS": "Luís", "INES": "Inês", "SEBASTIAO": "Sebastião",
    "CONCEICAO": "Conceição", "ASSUNCAO": "Assunção", "ARAUJO": "Araújo",
    "OTAVIO": "Otávio", "CELIA": "Célia", "SONIA": "Sônia", "HELOISA": "Heloísa",
    "TANIA": "Tânia", "PATRICIA": "Patrícia", "LUCIA": "Lúcia", "CASSIA": "Cássia",
    "MOISES": "Moisés", "ISAIAS": "Isaías", "VALERIA": "Valéria",
    "VITORIA": "Vitória", "JONATAS": "Jônatas", "GERALDO": "Geraldo",
    "SERGIO": "Sérgio", "MARIO": "Mário", "JULIO": "Júlio", "VINICIUS": "Vinícius",
    "TARCISIO": "Tarcísio", "EUGENIO": "Eugênio", "ROMULO": "Rômulo",
    "GENESIO": "Genésio", "ANISIO": "Anísio", "AURELIO": "Aurélio",
}

# Nome da serventia como o contrato escreve -> como o ato registra.
SERVENTIAS = {
    "2º OFICIO DE NOTAS E PROTESTO DE BRASILIA-DF":
        "2º Ofício de Notas e Protesto de Brasília-DF",
    "2º OFICIO DE NOTAS E PROTESTO DE TITULOS DE BRASILIA-DF":
        "2º Ofício de Notas e Protesto de Brasília-DF",
    "2º REGISTRO CIVIL E TABELIONATO DE NOTAS DA COMARCA DE GOIANIA-GO":
        "2º Registro Civil e Tabelionato de Notas de Goiânia-GO",
    "2º TABELIONATO DE NOTAS, PROTESTO, REGISTRO DE TITULOS E DOCUMENTOS E "
    "PESSOAS JURIDICAS DA COMARCA DE CATALAO-GO":
        "2º Tabelionato de Notas, Protesto, Registro de Títulos e Documentos e "
        "Pessoas Jurídicas da Comarca de Catalão-GO",
}

# Órgãos expedidores: a CAIXA escreve o nome inteiro, o ato usa a sigla.
ORGAOS = {
    "SECRETARIA DE SEGURANCA PUBLICA/GO": "SSP/GO",
    "SECRETARIA DE SEGURANCA PUBLICA": "SSP",
    "SSP/GO": "SSP/GO",
    "SPTC/GO": "SPTC/GO",
    "DETRAN/GO": "DETRAN/GO",
    "DGPC/GO": "DGPC/GO",
    # Conselhos de classe: a CAIXA escreve o nome inteiro, o ato usa a sigla.
    "CONSELHO REGIONAL DE ENGENHARIA E AGRONOMIA/PR": "CREA/PR",
    "CONSELHO REGIONAL DE ENGENHARIA E AGRONOMIA/GO": "CREA/GO",
    "CONSELHO REGIONAL DE MEDICINA/GO": "CRM/GO",
    "ORDEM DOS ADVOGADOS DO BRASIL/GO": "OAB/GO",
}


@dataclass
class Pendencia:
    """Um campo que o sistema se recusa a preencher sozinho.

    `grau` separa o que impede o registro do que só pede olho humano — sem essa
    distinção a tela vira um muro vermelho e o conferente para de ler."""
    campo: str
    motivo: str
    grau: str = "falta"      # falta | confirmar
    sugestao: str = ""

    @property
    def impede(self) -> bool:
        return self.grau == "falta"

    def __str__(self) -> str:
        return f"{self.campo}: {self.motivo}"


@dataclass
class Coletor:
    """Junta as pendências de uma geração inteira, sem repetir."""
    itens: list[Pendencia] = field(default_factory=list)

    def anota(self, campo: str, motivo: str, grau: str = "falta",
              sugestao: str = "") -> None:
        for existente in self.itens:
            if existente.campo == campo and existente.motivo == motivo:
                return
        self.itens.append(Pendencia(campo, motivo, grau, sugestao))

    def confirmar(self, campo: str, motivo: str, sugestao: str = "") -> None:
        """Não impede o registro: pede conferência antes de assinar."""
        self.anota(campo, motivo, grau="confirmar", sugestao=sugestao)

    @property
    def impeditivas(self) -> list[Pendencia]:
        return [i for i in self.itens if i.impede]

    def falta(self, campo: str, motivo: str, rotulo: str) -> str:
        """Anota e devolve a marca visível que entra no texto do ato."""
        self.anota(campo, motivo)
        return f"[[falta: {rotulo}]]"

    def __len__(self) -> int:
        return len(self.itens)


def sem_acento(texto: str) -> str:
    decomposto = unicodedata.normalize("NFD", str(texto))
    return "".join(c for c in decomposto if unicodedata.category(c) != "Mn")


def so_digitos(texto) -> str:
    return re.sub(r"\D", "", str(texto or ""))


def _chave(texto) -> str:
    return re.sub(r"\s+", " ", sem_acento(str(texto or "")).strip().upper())


def _preenche_zero(numero) -> str:
    return f"{int(numero):02d}"


def eh_numeral_romano(palavra: str) -> bool:
    """Numeral romano em nome de bairro — "Setor Cristo Redentor II Etapa" — não
    pode virar "Ii". Só I, V e X entram no teste: incluir D, C, L e M faria "DI",
    "CI" e "MI" passarem por numeral. Numeral de logradouro não passa de XXXIX."""
    return (len(palavra) >= 2
            and re.fullmatch(r"[ivx]+", palavra, re.I) is not None
            and re.fullmatch(r"x{0,3}(ix|iv|v?i{0,3})", palavra, re.I) is not None)


def nome_proprio(texto: str) -> str:
    """"MARIANA ALVES PEREIRA" -> "Mariana Alves Pereira"
    "PEDRO SOUZA DA MATA" -> "Pedro Souza da Mata"

    Acento perdido NÃO é restituído: "JOSE" viraria "José" ou "Jose"? Só quem lê
    o documento sabe, e inventar acento em nome é falsificar qualificação."""
    if not texto:
        return ""
    palavras = str(texto).strip().lower().split()
    saida = []
    for indice, palavra in enumerate(palavras):
        if indice > 0 and palavra in PARTICULAS:
            saida.append(palavra)
        elif eh_numeral_romano(palavra):
            saida.append(palavra.upper())
        else:
            saida.append(palavra[:1].upper() + palavra[1:])
    return " ".join(saida)


def confere_acentos(nome: str, coletor: Coletor, dono: str) -> None:
    """A CAIXA grava "ROGERIO"; o ato registra "Rogério". Restituir acento
    automaticamente é inventar qualificação, então aqui a grafia certa é
    SUGERIDA e o conferente decide — mesma disciplina do dígito de CPF."""
    palavras = nome_proprio(nome).split()
    houve_troca = False

    for indice, palavra in enumerate(palavras):
        chave = sem_acento(palavra).upper()
        certo = NOMES_ACENTUADOS.get(chave)
        if certo and palavra != certo:
            palavras[indice] = certo
            houve_troca = True

    if houve_troca:
        sugerido = " ".join(palavras)
        coletor.confirmar(
            f"acento no nome ({dono})",
            f'a CAIXA grava sem acento; a grafia provável é "{sugerido}".',
            sugestao=sugerido)


def serventia(texto: str, coletor: Coletor) -> str:
    chave = _chave(texto)
    if chave in SERVENTIAS:
        return SERVENTIAS[chave]
    coletor.confirmar(
        "nome da serventia",
        f'"{texto}" não está na tabela; o ato costuma abreviar o nome oficial '
        f"(cai o \"de Títulos\", cai o \"da Comarca\"). Confira a redação.")
    return str(texto).strip()


def _vocabulario_acentuado(frases) -> dict[str, str]:
    """Palavra sem acento -> palavra com acento, tirado das próprias entradas.

    "servidor público" e "auxiliar de escritório" ensinam que "publico" é
    "público" e "escritorio" é "escritório". Com isso a ferramenta reconhece o
    acento perdido em profissão que ainda não está no dicionário inteiro —
    sem nunca inventar: só repete o que já está escrito em algum lugar.
    """
    vocabulario: dict[str, str] = {}
    for frase in frases:
        for palavra in frase.split():
            se = sem_acento(palavra)
            if se != palavra:
                vocabulario.setdefault(se.lower(), palavra.lower())
    return vocabulario


VOCABULARIO_PROFISSOES = _vocabulario_acentuado(PROFISSOES.values())


def profissao(texto, coletor: Coletor, dono: str) -> str:
    """Decisão da serventia (24/08/2026): copiar fielmente o que o contrato diz.

    O ato não substitui a profissão; só devolve o acento que a CAIXA come. O
    dicionário resolve as frases inteiras que já conhecemos, e o vocabulário
    resolve palavra a palavra o resto — quando não reconhece nada, o texto passa
    como veio e ninguém é incomodado.
    """
    chave = _chave(texto)
    if not chave:
        return coletor.falta(f"profissão ({dono})",
                             "não consta do contrato.", "profissão")
    if chave in PROFISSOES:
        return PROFISSOES[chave]

    palavras = str(texto).lower().split()
    sugeridas = list(palavras)
    houve_troca = False
    for indice, palavra in enumerate(palavras):
        certa = VOCABULARIO_PROFISSOES.get(palavra)
        if certa and certa != palavra:
            sugeridas[indice] = certa
            houve_troca = True

    if houve_troca:
        sugestao = " ".join(sugeridas)
        coletor.confirmar(
            f"profissão ({dono})",
            f'a CAIXA gravou "{str(texto).lower()}" sem acento; a grafia '
            f'provável é "{sugestao}".',
            sugestao=sugestao)

    return str(texto).lower()


PREPOSICOES = {"de", "da", "do", "das", "dos", "em", "e", "com"}


def flexiona_profissao(texto: str, sexo: str) -> str:
    """O contrato grava a profissão no masculino do CBO; o ato concorda com a
    pessoa — "administrador" vira "administradora" para a compradora.

    Flexiona a primeira palavra e, quando ela é seguida de adjetivo (e não de
    preposição), também a segunda: "servidor público" -> "servidora pública".
    "trabalhador de fabricação..." para na preposição, como deve."""
    if sexo != "F" or not texto:
        return texto

    palavras = texto.split()

    def feminino(palavra: str) -> str:
        if palavra.endswith("or"):
            return palavra + "a"
        if palavra.endswith("o"):
            return palavra[:-1] + "a"
        return palavra

    palavras[0] = feminino(palavras[0])
    if len(palavras) > 1 and palavras[1] not in PREPOSICOES:
        palavras[1] = feminino(palavras[1])
    return " ".join(palavras)


def orgao_expedidor(texto, coletor: Coletor, dono: str) -> str:
    chave = _chave(texto)
    if not chave:
        return coletor.falta(f"órgão expedidor ({dono})",
                             "não consta do contrato.", "órgão expedidor")
    if chave in ORGAOS:
        return ORGAOS[chave]
    coletor.confirmar(f"órgão expedidor ({dono})",
                      f'"{texto}" não está na tabela de siglas; confirme a redação.')
    return str(texto).strip()


def nome_de_logradouro(bruto: str, coletor: Coletor | None = None,
                       dono: str = "") -> str:
    """Convenção local de Morrinhos, lida do acervo:
    "Cr7" -> "CR-07" (letras + número); "4d" -> "04-D" (número + letra).
    Nome conhecido ganha acento pelo dicionário; nome novo fica como veio."""
    texto = str(bruto or "").strip()

    casou = re.fullmatch(r"([A-Za-z]{1,3})[\s-]?(\d{1,3})", texto)
    if casou:
        return f"{casou.group(1).upper()}-{_preenche_zero(casou.group(2))}"

    casou = re.fullmatch(r"(\d{1,3})[\s-]?([A-Za-z])", texto)
    if casou:
        return f"{_preenche_zero(casou.group(1))}-{casou.group(2).upper()}"

    if re.fullmatch(r"\d{1,3}", texto):
        return _preenche_zero(texto)

    return _confere_cadastro(texto, LOGRADOUROS, "logradouro", coletor, dono)


def _confere_cadastro(texto: str, cadastro: dict, especie: str,
                      coletor: Coletor | None, dono: str) -> str:
    """Copia o que veio do contrato e AVISA quando o cadastro grafa diferente.

    Decisão da serventia (24/08/2026): a ferramenta não troca o nome por conta
    própria. Corrigir calado seria decidir no lugar de quem assina — e o
    cadastro dos Correios, embora seja a fonte oficial, não é o que o contrato
    diz. Então o texto sai como veio e a divergência vira aviso, com a grafia
    do cadastro oferecida ao lado.
    """
    escrito = nome_proprio(texto)
    oficial = cadastro.get(_chave(texto))

    if oficial is None:
        if coletor is not None and re.search(r"[A-Za-z]{4}", texto):
            coletor.confirmar(
                f"{especie} ({dono})",
                f'"{escrito}" não consta do cadastro dos Correios; confira a '
                f"grafia e se o loteamento já foi cadastrado.")
    elif oficial != escrito and coletor is not None:
        coletor.confirmar(
            f"{especie} ({dono})",
            f'o contrato escreve "{escrito}" e o cadastro da Prefeitura grafa '
            f'"{oficial}".',
            sugestao=oficial)

    return escrito


def nome_de_bairro(bruto: str, coletor: Coletor, dono: str) -> str:
    """Mesma disciplina do logradouro: copia o do contrato e avisa se o cadastro
    da Prefeitura grafa diferente."""
    return _confere_cadastro(str(bruto or "").strip(), BAIRROS, "bairro",
                             coletor, dono)


def _expande_quadra_lote(campo: str):
    """"Q 11 L 14", "Q62 L01" e "Quadra 39 Lote 14" -> "Quadra 39, Lote 14".

    None quando não for quadra e lote — bloco, apartamento, letra solta.

    A ORDEM das alternativas é a regra inteira: expressão regular escolhe a
    primeira que casa, não a mais longa. Com `QD|Q|QUADRA` o `Q` vencia, e
    "QUADRA 39" virava rótulo "Q" com número "UADRA" — o ato saía "Quadra
    UADRA, 39, Lote OTE, 14". As formas por extenso vêm primeiro.
    """
    pedacos = []
    restante = str(campo).strip()
    achou = False
    padrao = re.compile(
        r"^(QUADRA|QD|Q|LOTE|LT|L)\.?\s*"
        # o designativo é número ("39", "09-A") ou letra ("Quadra C" existe no
        # acervo); duas letras no máximo, para não engolir palavra inteira.
        r"(\d[0-9A-Za-z-]*|[A-Za-z]{1,2})(?=\s|$)\s*", re.I)
    while restante:
        casou = padrao.match(restante)
        if not casou:
            break
        achou = True
        etiqueta = "Quadra" if casou.group(1).upper().startswith("Q") else "Lote"
        pedacos.append(f"{etiqueta} {casou.group(2).upper()}")
        restante = restante[casou.end():]
    if not achou or restante.strip():
        return None
    return ", ".join(pedacos)


def endereco(bruto: str, coletor: Coletor, dono: str) -> str:
    """"R Cr7, 18, Setor Cristo Redentor II Etapa em Morrinhos/GO"
        -> "Rua CR-07, n.º 18, Setor Cristo Redentor II Etapa, Morrinhos-GO"

    O "0" no lugar do número não vira "n.º 0": a CAIXA usa zero para "sem
    número", e o ato registrado o omitiu. Omitir e avisar; nunca escrever zero.
    """
    texto = str(bruto or "").strip().rstrip(".")
    if not texto:
        return coletor.falta(f"endereço ({dono})", "não consta do contrato.", "endereço")

    municipio = ""
    casou = re.search(r"\s+em\s+([^,]+?)\s*/\s*([A-Za-z]{2})\s*\.?$", texto)
    if casou:
        municipio = f"{nome_proprio(casou.group(1).strip())}-{casou.group(2).upper()}"
        texto = texto[:casou.start()]

    campos = [c.strip() for c in texto.split(",") if c.strip()]

    # O endereço comercial do representante já vem no formato do ato
    # ("..., Centro, Morrinhos-GO") — sem o "em Cidade/UF" das partes.
    if not municipio and campos:
        casou = re.fullmatch(r"(.+?)-([A-Za-z]{2})", campos[-1])
        if casou:
            municipio = f"{nome_proprio(casou.group(1))}-{casou.group(2).upper()}"
            campos.pop()

    partes = []

    # 1º campo: tipo + nome do logradouro
    primeiro = campos.pop(0) if campos else ""
    pedaco = primeiro.split(None, 1)
    if len(pedaco) == 2 and pedaco[0].upper().rstrip(".") in TIPOS_LOGRADOURO:
        tipo = TIPOS_LOGRADOURO[pedaco[0].upper().rstrip(".")]
        partes.append(f"{tipo} {nome_de_logradouro(pedaco[1], coletor, dono)}")
    else:
        coletor.confirmar(f"logradouro ({dono})",
                      f'tipo de logradouro não reconhecido em "{primeiro}".')
        partes.append(nome_de_logradouro(primeiro, coletor, dono))

    # 2º campo: número, quadra e lote podem vir grudados ("169 B Q62 L01")
    if campos:
        partes.extend(_numero_e_complemento(campos.pop(0), coletor, dono))

    # Uma letra sozinha logo depois do número é complemento dele, não campo
    # próprio: o contrato escreve "169, B" e o ato registra "n.º 169 B".
    if (campos and partes and partes[-1].startswith("n.º ")
            and re.fullmatch(r"[A-Za-z]", campos[0])):
        partes[-1] += " " + campos.pop(0).upper()

    # Campos seguintes: quadra/lote soltos, número atrasado, depois bairro
    ja_tem_numero = any(p.startswith("n.º ") for p in partes)
    while campos:
        campo = campos.pop(0)

        expandido = _expande_quadra_lote(campo)
        if expandido:
            partes.append(expandido)
            continue

        # O número nem sempre vem no segundo campo: "Avenida D, Qd 43, 959"
        # traz a quadra antes dele. Um campo só de dígitos, quando ainda não há
        # número no endereço, é o número — e não um bairro chamado "959".
        if not ja_tem_numero and re.fullmatch(r"\d{1,6}", campo):
            numero = int(campo)
            if numero:
                partes.append("n.º " + f"{numero:,}".replace(",", "."))
                ja_tem_numero = True
            continue

        partes.append(nome_de_bairro(campo, coletor, dono))

    if municipio:
        partes.append(municipio)
    return ", ".join(partes)


def _numero_e_complemento(campo: str, coletor: Coletor, dono: str) -> list[str]:
    """"18" -> ["n.º 18"];  "169 B Q62 L01" -> ["n.º 169", "B", "Quadra 62", "Lote 1"]"""
    partes = []
    restante = campo.strip()

    # "169 B" é um número só — a letra faz parte dele, e o ato escreve
    # "n.º 169 B". Só quadra e lote é que viram campo separado.
    casou = re.match(r"^(\d+)\s*([A-Za-z])?(?=\s|$)", restante)
    if casou:
        numero = int(casou.group(1))
        letra = f" {casou.group(2).upper()}" if casou.group(2) else ""
        restante = restante[casou.end():]
        if numero == 0:
            # Decisão da serventia (24/08/2026): a CAIXA usa "0" para dizer que
            # o imóvel não tem número, e o ato simplesmente não escreve número
            # nenhum. Não há o que confirmar — omitir e seguir.
            pass
        else:
            partes.append("n.º " + f"{numero:,}".replace(",", ".") + letra)

    if not restante.strip():
        return partes

    expandido = _expande_quadra_lote(restante)
    if expandido:
        partes.extend(expandido.split(", "))
        return partes

    # Sobrou algo que não é quadra nem lote — bloco, apartamento, letra solta.
    pedacos = restante.split()
    sobra = []
    for pedaco in pedacos:
        expandido = _expande_quadra_lote(pedaco)
        if expandido:
            if sobra:
                partes.append(" ".join(sobra))
                sobra = []
            partes.extend(expandido.split(", "))
        else:
            sobra.append(pedaco)
    if sobra:
        texto = " ".join(sobra)
        coletor.confirmar(
            f"complemento do endereço ({dono})",
            f'"{texto}" não foi reconhecido como quadra, lote ou bairro; '
            f"confirme como deve entrar no ato.")
        partes.append(texto)
    return partes


def data(bruto, coletor: Coletor, dono: str) -> str:
    """"17/04/2026" e "17 de Março de 2026" -> "17.04.2026" """
    texto = str(bruto or "").strip()

    casou = re.fullmatch(r"(\d{1,2})[/.](\d{1,2})[/.](\d{4})", texto)
    if casou:
        return (f"{_preenche_zero(casou.group(1))}.{_preenche_zero(casou.group(2))}."
                f"{casou.group(3)}")

    casou = re.fullmatch(r"(\d{1,2})\s+de\s+([A-Za-zÀ-ÿ]+)\s+de\s+(\d{4})", texto, re.I)
    if casou:
        procurado = sem_acento(casou.group(2)).lower()
        for indice, mes in enumerate(MESES):
            if sem_acento(mes) == procurado:
                return (f"{_preenche_zero(casou.group(1))}.{_preenche_zero(indice + 1)}."
                        f"{casou.group(3)}")

    return coletor.falta(f"data ({dono})", f'"{bruto}" não foi reconhecida.', "data")


def data_por_extenso(pontuada: str) -> str:
    """"25.03.2026" -> "25 de março de 2026", para o fecho do ato."""
    partes = str(pontuada).split(".")
    if len(partes) != 3:
        return pontuada
    return f"{int(partes[0])} de {MESES[int(partes[1]) - 1]} de {partes[2]}"


def percentual(bruto) -> str:
    """"4.5000" -> "4,5000" """
    return str(bruto).strip().replace(".", ",")


def _digito_cpf(base: str) -> str:
    """DV do CPF. Validação nossa: o contrato pode trazer número transcrito
    errado, e CPF errado qualifica outra pessoa."""
    digitos = [int(c) for c in base]
    soma = sum(d * peso for d, peso in zip(digitos, range(len(digitos) + 1, 1, -1)))
    resto = (soma * 10) % 11
    return str(0 if resto == 10 else resto)


def cpf_valido(bruto) -> bool:
    numero = so_digitos(bruto)
    if len(numero) != 11 or numero == numero[0] * 11:
        return False
    return numero[9] == _digito_cpf(numero[:9]) and numero[10] == _digito_cpf(numero[:10])


def cpf(bruto, coletor: Coletor | None = None, dono: str = "") -> str | None:
    numero = so_digitos(bruto)
    if len(numero) != 11:
        return None
    if coletor is not None and not cpf_valido(numero):
        coletor.anota(f"CPF ({dono})",
                      f"o dígito verificador de {bruto} não confere; a transcrição "
                      f"pode estar errada.")   # impeditiva: CPF errado qualifica outra pessoa
    return f"{numero[:3]}.{numero[3:6]}.{numero[6:9]}-{numero[9:]}"


def cnpj(bruto) -> str | None:
    numero = so_digitos(bruto)
    if len(numero) != 14:
        return None
    return (f"{numero[:2]}.{numero[2:5]}.{numero[5:8]}/{numero[8:12]}-{numero[12:]}")
