"""Conferência prévia: o contrato confrontado com a matrícula.

O gerador escreve o ato que as partes querem. Este módulo pergunta outra coisa,
antes: **o registro pode ser feito?** É a qualificação registral, e ela olha
para os dois documentos ao mesmo tempo.

Cada exigência sai numerada e fundamentada. O fundamento não é enfeite: é o que
permite ao apresentante saber o que fazer, e ao conferente sustentar a nota.

Os artigos citados foram conferidos no texto das leis (`Desktop\\Notas\\
Fundamentações`) e, onde a serventia já tinha praticado o ato, no fundamento
que ela própria escreveu no fólio.

**Este módulo não substitui a qualificação de quem assina.** Ele lê o que os
dois documentos dizem e aponta o que salta; não vê o que não está escrito, e
não conhece o que corre fora do fólio.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import normaliza as nz
from .ficha import Empresa, Ficha
from .matricula import Matricula
from .comparacao import area_m2, areas_iguais, designativo

# Graus, do mais duro ao mais brando.
IMPEDE = "impede"      # não há registro possível enquanto não se resolver
EXIGE = "exige"        # falta ato ou documento prévio
ATENCAO = "atenção"    # confira; pode ser só transcrição


@dataclass
class Exigencia:
    titulo: str
    detalhe: str
    fundamento: str
    grau: str = EXIGE
    numero: int = 0


@dataclass
class Conferencia:
    exigencias: list[Exigencia] = field(default_factory=list)

    def acrescenta(self, titulo: str, detalhe: str, fundamento: str,
                   grau: str = EXIGE) -> None:
        self.exigencias.append(Exigencia(titulo, detalhe, fundamento, grau))

    def numera(self) -> list[Exigencia]:
        """Numera na ordem de gravidade: o que impede vem primeiro."""
        ordem = {IMPEDE: 0, EXIGE: 1, ATENCAO: 2}
        ordenadas = sorted(self.exigencias, key=lambda e: ordem.get(e.grau, 9))
        for indice, exigencia in enumerate(ordenadas, start=1):
            exigencia.numero = indice
        return ordenadas

    @property
    def impeditivas(self) -> int:
        return sum(1 for e in self.exigencias if e.grau == IMPEDE)


# --------------------------------------------------------------------- apoio
def _documentos_das_partes(partes, com_conjuge: bool = True) -> list[tuple[str, str]]:
    """(nome, CPF ou CNPJ) de cada parte, achatando cônjuge e representante.

    `com_conjuge=False` deixa de fora quem só assina consentindo: o cônjuge que
    comparece como interveniente anuente **não é titular**, e cobrar dele
    continuidade produzia exigência impeditiva contra quem nunca precisou
    constar do fólio (art. 1.647 do Código Civil — ele outorga, não transmite).
    """
    saida = []
    for parte in partes:
        if isinstance(parte, Empresa):
            saida.append((parte.razao_social, nz.so_digitos(parte.cnpj)))
            continue
        saida.append((parte.nome, nz.so_digitos(parte.cpf)))
        if com_conjuge and parte.conjuge:
            saida.append((parte.conjuge.nome, nz.so_digitos(parte.conjuge.cpf)))
    return saida


def _mora_no_texto(documento: str, texto: str) -> bool:
    return bool(documento) and documento in nz.so_digitos(texto)


# Regimes que só existem se houver pacto antenupcial. A comunhão parcial é o
# regime legal desde a Lei 6.515/77 e dispensa pacto (CC art. 1.640).
REGIMES_COM_PACTO = ("comunhão universal", "separação de bens",
                     "separação total", "separação convencional",
                     "participação final")

# O que, no fólio, diz que o proprietário é pessoa jurídica — e portanto não tem
# estado civil a cobrar. Cada marca precisa de fronteira de palavra: a versão
# anterior trazia `S/?A` e casava com o pedaço "sa" de qualquer nome. Ela nunca
# chegou a fazer estrago porque o `\b` do fim tinha virado um caractere de
# controle literal (0x08) na gravação do arquivo, e aí o padrão não casava com
# nada — a trava ficou morta desde que nasceu, e a exigência de estado civil
# sairia contra empresa.
MARCAS_DE_PESSOA_JURIDICA = re.compile(
    r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}"                 # CNPJ
    r"|pessoa\s+jur[íi]dica"
    r"|sociedade\s+(?:an[ôo]nima|empres[áa]ria|limitada|simples)"
    r"|\bLTDA\b|\bEIRELI\b|\bMEI\b|\bS/A\b|\bS\.\s?A\.", re.I)


# ---------------------------------------------------------------- conferências
def _continuidade(ficha: Ficha, m: Matricula, c: Conferencia) -> None:
    """Quem vende tem de ser quem consta como dono. É a trava mais dura que há.

    O cônjuge fica de fora: ele comparece como interveniente anuente, outorga o
    consentimento do art. 1.647 do Código Civil e **não transmite**. Cobrar dele
    continuidade acusava, como impedimento, alguém que nunca precisou constar do
    fólio — foi o que aconteceu com o cônjuge do primeiro transmitente do
    contrato 8.4444.4460043-3. Sendo ele coproprietário, aparece no fólio de
    todo jeito, e o titular já responde pela conferência.
    """
    vendedores = _documentos_das_partes(ficha.vendedores, com_conjuge=False)
    if not vendedores:
        return

    titulares = m.proprietarios
    if not titulares:
        c.acrescenta(
            "Titularidade não identificada na matrícula",
            "não consegui localizar quem consta como proprietário no fólio. "
            "Confira à mão antes de prosseguir.",
            "Lei 6.015/1973, art. 195", ATENCAO)
        return

    fora = [(nome, doc) for nome, doc in vendedores
            if doc and not _mora_no_texto(doc, titulares)]
    if fora:
        quem = "; ".join(f"{nz.nome_proprio(n)} ({d})" for n, d in fora)
        c.acrescenta(
            "Quebra de continuidade",
            f"o contrato apresenta como transmitente {quem}, que não consta "
            f"como titular na matrícula {m.numero}. O imóvel precisa estar "
            f"registrado em nome de quem transmite.",
            "Lei 6.015/1973, art. 195", IMPEDE)


def _so_letras(texto: str) -> str:
    return re.sub(r"[^A-Z]", "", nz.sem_acento(texto or "").upper())


def _nome_parecido_no_folio(nome: str, titulares: str) -> str:
    """O nome do fólio mais próximo do que o contrato traz, para a nota mostrar
    as duas grafias lado a lado. Vazio quando nada se parece."""
    from difflib import SequenceMatcher

    alvo = _so_letras(nome)
    melhor, semelhanca = "", 0.0
    for campo in re.split(r"[,;]", titulares):
        campo = campo.strip()
        if len(campo.split()) < 2 or not re.match(r"[A-ZÀ-Ýa-zà-ÿ]", campo):
            continue
        taxa = SequenceMatcher(None, alvo, _so_letras(campo)).ratio()
        if taxa > semelhanca:
            melhor, semelhanca = campo, taxa
    return melhor if semelhanca >= 0.75 else ""


def _confere_nome_do_titular(ficha: Ficha, m: Matricula, c: Conferencia) -> None:
    """O nome de quem transmite, no título, contra o do fólio.

    Só entra quando o documento **já foi encontrado** no fólio: aí é a mesma
    pessoa, e o que diverge é a grafia. Não estando o documento lá, o caso é
    outro — quebra de continuidade, tratada acima.

    Decisão da serventia (25/08/2026): **a minuta sai como o contrato escreve**,
    e a divergência vira pendência. Corrigir calado seria decidir no lugar de
    quem assina, e qual dos dois documentos está errado só o título de
    identidade diz.

    O cônjuge anuente fica de fora, como na continuidade: ele não precisa
    constar do fólio.

    A **profissão não é comparada**, e isso é medido: no R.04 da 38.807 o
    contrato diz "proprietário de estabelecimento" e o fólio "corretor de
    imóveis". Profissão muda com o tempo, e a serventia registra a declarada —
    cobrar igualdade produziria exigência falsa em caso correto.
    """
    titulares = m.proprietarios
    if not titulares:
        return

    for nome, documento in _documentos_das_partes(ficha.vendedores,
                                                  com_conjuge=False):
        if not nome or not documento:
            continue
        if not _mora_no_texto(documento, titulares):
            continue                      # não é a mesma pessoa: é continuidade
        if _so_letras(nome) in _so_letras(titulares):
            continue

        no_folio = _nome_parecido_no_folio(nome, titulares)
        como_esta = f' — a matrícula grafa "{no_folio}"' if no_folio else ""
        c.acrescenta(
            "Nome do titular divergente do fólio",
            f'o contrato qualifica o transmitente como "{nz.nome_proprio(nome)}"'
            f"{como_esta}, e o documento é o mesmo. A minuta sai como o contrato "
            f"escreve; a grafia do fólio precisa ser conferida contra o "
            f"documento de identidade e, sendo caso, retificada por averbação.",
            "Lei 6.015/1973, art. 176, §1º, II, 4, a; art. 213, I; art. 246",
            EXIGE)


def _matricula_viva(m: Matricula, c: Conferencia) -> None:
    if m.encerrada:
        c.acrescenta(
            "Matrícula encerrada",
            f"a matrícula {m.numero} foi encerrada e não comporta novo registro. "
            f"Verifique a matrícula que a sucedeu.",
            "Lei 6.015/1973, art. 233, II", IMPEDE)


def _onus(m: Matricula, c: Conferencia) -> None:
    for ato in m.onus_vigentes:
        # A data pode faltar: nem todo ato traz cabecalho legivel, e a exigencia
        # vale do mesmo jeito. Ler o atributo direto derrubava o confronto
        # inteiro por causa de um onus sem data.
        data = getattr(ato, "data", "") or ""
        quando = f", de {data}," if data else ""
        c.acrescenta(
            f"Ônus vigente — {ato.titulo.title()}",
            f"consta o {ato.rotulo}{quando} sem cancelamento averbado. "
            f"A transmissão depende da baixa ou da anuência do credor.",
            "Lei 6.015/1973, art. 252; Lei 9.514/1997, art. 25 "
            "(cancelamento pela quitação da dívida)", IMPEDE)


def _especialidade_objetiva(ficha: Ficha, m: Matricula, c: Conferencia) -> None:
    """O imóvel do contrato tem de ser o imóvel da matrícula."""
    if not m.designacao_cadastral:
        c.acrescenta(
            "Designação cadastral não averbada",
            "a matrícula não traz o CCI — o Certificado de Cadastro Imobiliário "
            "do imóvel, atribuído pelo Município. Sendo imóvel urbano com "
            "cadastro municipal atribuído, a designação integra a identificação "
            "do imóvel e precisa ser averbada. Instrua com o Boletim de "
            "Cadastro Imobiliário (BCI) da Prefeitura.",
            "Lei 6.015/1973, art. 176, §1º, II, 3, b", EXIGE)

    if not m.cep:
        # Não impede o registro, e o acervo prova: o R.03 da 39.303 foi
        # registrado sem CEP averbado. Vale como recomendação — e a averbação
        # que serve só para incluir o CEP não custa nada à parte.
        c.acrescenta(
            "CEP não averbado",
            "a matrícula não traz o Código de Endereçamento Postal. A averbação "
            "que serve apenas para incluir o CEP é gratuita, e aproveitar o "
            "protocolo evita novo requerimento depois.",
            "Provimento CNJ n.º 149/2023, art. 440-AV, parágrafo único "
            "(incluído pelo Provimento CN n.º 195/2025)", ATENCAO)

    # A obra que ainda vai ser feita não se averba: no contrato de terreno com
    # mútuo para obras a casa não existe, e cobrar averbação dela seria exigir
    # o impossível. Só interessa a construção que o título diz JÁ EDIFICADA.
    descricao = ficha.brutos.get("imovel", "")
    ja_edificada = re.search(r"\bCASA\b.{0,140}?\bEDIFICAD", descricao, re.I | re.S)

    if ja_edificada and not ficha.valores.tem_construcao and \
            not m.averbacao("EDIFICAÇÃO", "CONSTRUÇÃO"):
        c.acrescenta(
            "Edificação não averbada",
            "o título descreve casa já edificada sobre o terreno, e a matrícula "
            "não traz averbação de edificação. Instrua com o habite-se e a CND "
            "da obra, ou esclareça a divergência.",
            "Lei 6.015/1973, art. 167, II, 4", EXIGE)


# "situado na Rua CP-12, do Setor Cordeiro 02," — a frase é a mesma no contrato
# e no fólio, e é dela que saem logradouro e bairro.
ONDE_FICA = re.compile(
    r"situad[oa]\s+n[ao]\s+(?P<logradouro>[^,]+?)\s*,\s*"
    r"d[oae]s?\s+(?P<bairro>[^,]+?)\s*,", re.I)

# "uma CASA RESIDENCIAL de n.º 162" / "UMA CASA RESIDENCIAL DE Nº 162"
NUMERO_DA_CASA = re.compile(r"\bCASA\b.{0,80}?\bn\.?\s*[ºo°]?\s*(\d[\d.]*)",
                            re.I | re.S)
AREA_CONSTRUIDA = re.compile(
    r"([\d.,]+)\s*m\s*[²2]\s*(?:de\s+)?[áa]rea\s+constru[íi]da"
    r"|[áa]rea\s+constru[íi]da\s+(?:de\s+)?([\d.,]+)\s*m\s*[²2]", re.I)

# "125,00m² (cento e vinte e cinco metros quadrados)"
AREA_COM_EXTENSO = re.compile(
    r"[áa]rea\s+de\s*([\d.]*\d,\d+)\s*m\s*[²2]\s*\(([^)]{5,140})\)", re.I)


def _chave(texto: str) -> str:
    """Como duas grafias do mesmo nome viram a mesma coisa.

    Acento, caixa, pontuação e espaço não distinguem logradouro: "CP-12",
    "CP 12" e "cp12" são a mesma rua. Zero à esquerda também não: "Setor
    Cordeiro 02" e "Setor Cordeiro 2" são o mesmo setor. O que sobra tem de
    ser igual — decisão da serventia (25/08/2026): rua renomeada e não averbada
    é caso em que **o contrato acompanha o fólio**, então a diferença é
    exigência, não exceção.
    """
    limpo = re.sub(r"[^0-9A-Za-zÀ-Ý]", "", nz.sem_acento(texto or "")).upper()
    return re.sub(r"\d+", lambda d: str(int(d.group())), limpo)


def _onde_fica(texto: str):
    casou = ONDE_FICA.search(texto or "")
    if not casou:
        return None, None
    return casou.group("logradouro").strip(), casou.group("bairro").strip()


def _confere_endereco(ficha: Ficha, m: Matricula, c: Conferencia) -> None:
    """Logradouro e bairro do contrato contra os do fólio.

    Só compara o que conseguiu ler dos DOIS lados: não dando, cala. Exigência
    falsa custa mais que exigência faltando, e a frase varia de fólio para
    fólio.
    """
    do_contrato = _onde_fica(ficha.brutos.get("imovel", ""))
    do_folio = _onde_fica(m.descricao)

    for indice, (titulo, rotulo) in enumerate(
            (("Logradouro divergente", "logradouro"),
             ("Bairro ou setor divergente", "bairro"))):
        contrato, folio = do_contrato[indice], do_folio[indice]
        if not contrato or not folio or _chave(contrato) == _chave(folio):
            continue
        # Cada lado aparece como o seu documento escreve. Passar o do contrato
        # por `nome_proprio` produzia "Rua Cp-12" e punha na nota uma grafia
        # que não está em papel nenhum.
        c.acrescenta(
            titulo,
            f"o contrato descreve o imóvel {'na' if indice == 0 else 'no'} "
            f'"{contrato}" e a matrícula {m.numero} '
            f'{"na" if indice == 0 else "no"} "{folio}". A descrição do '
            f"título tem de ser a do fólio; havendo mudança de {rotulo} pelo "
            f"Município, ela precisa ser averbada antes.",
            "Lei 6.015/1973, art. 225; art. 176, §1º, II, 3, b", IMPEDE)


def _confere_edificacao(ficha: Ficha, m: Matricula, c: Conferencia) -> None:
    """A casa do contrato contra a casa averbada.

    Decisão da serventia (25/08/2026): divergência **impede**. A casa vendida
    não é a casa averbada, e a alienação fiduciária gravaria garantia sobre
    edificação que o fólio descreve de outro jeito.
    """
    ato = m.averbacao("EDIFICAÇÃO", "CONSTRUÇÃO")
    if not ato:
        return
    descricao = ficha.brutos.get("imovel", "")
    if not re.search(r"\bCASA\b", descricao, re.I):
        return

    diferencas = []
    for padrao, nome in ((NUMERO_DA_CASA, "número da casa"),
                         (AREA_CONSTRUIDA, "área construída")):
        no_contrato = padrao.search(descricao)
        no_folio = padrao.search(ato.texto)
        if not no_contrato or not no_folio:
            continue
        valor_contrato = next(g for g in no_contrato.groups() if g)
        valor_folio = next(g for g in no_folio.groups() if g)
        iguais = (areas_iguais(valor_contrato+' m²', valor_folio+' m²')
                  if nome == 'área construída' else designativo(valor_contrato) == designativo(valor_folio))
        if not iguais:
            diferencas.append(
                f"{nome}: o contrato diz {valor_contrato} e o "
                f"{ato.rotulo} averbou {valor_folio}")

    if diferencas:
        c.acrescenta(
            "Edificação divergente",
            "; ".join(diferencas) + ". A casa descrita no título não é a que "
            "consta averbada. Esclareça a divergência antes do registro — a "
            "garantia recairia sobre edificação diversa da do fólio.",
            "Lei 6.015/1973, art. 225; art. 167, II, 4", IMPEDE)


# "IMÓVEL HAVIDO CONFORME AV-02 DA MATRÍCULA 39.303" — e também "AV- 02", que
# é como sai do PDF de um dos contratos.
ATO_CITADO_NO_TITULO = re.compile(
    r"HAVID[OA]\s+CONFORME\s+(?P<especie>AV|R)\s*[-.]?\s*(?P<numero>\d{1,2})\b",
    re.I)


def _confere_remissao_ao_ato(ficha: Ficha, m: Matricula, c: Conferencia) -> None:
    """O ato que o título cita tem de ser o que ele diz ser.

    Nos três contratos do acervo que citam ato — AV-02 na 39.303, AV-03 na
    38.807 e AV-03 na 28.596 —, o citado é **sempre a averbação de
    edificação**: é ela que põe a casa no fólio, e é por ela que o imóvel
    descrito (terreno mais casa) corresponde à matrícula. Contrato de terreno
    sem casa cita só a matrícula, sem ato nenhum.

    Citação apontando outro ato quer dizer que o título foi redigido contra um
    fólio em outro estado — certidão de outra matrícula, ou desatualizada.

    **Exige, não impede** (decisão da serventia, 25/08/2026): a descrição do
    imóvel pode estar certa e só a remissão errada, e a ORIGEM do ato quem
    escreve é o registrador, a partir do fólio — não do contrato.
    """
    casou = ATO_CITADO_NO_TITULO.search(ficha.brutos.get("imovel", ""))
    if not casou:
        return

    numero = int(casou.group("numero"))
    citado = f"{casou.group('especie').upper()}.{numero:02d}"

    presentes = {(ato.especie, ato.numero): ato for ato in m.atos}
    alvo = presentes.get((casou.group('especie').upper(), numero))
    contexto = ficha.brutos.get('imovel', '')[:casou.start()]
    referencia_edificacao = casou.group('especie').upper() == 'AV' and bool(re.search(r'\bCASA\b.*\bEDIFICAD', contexto, re.I | re.S))
    if alvo is None:
        # A certidão pode ser parcial — o fólio da 28.596 começa na AV.02, sem
        # AV.01. Dizer "esse ato não existe" seria acusar o que não se sabe.
        c.acrescenta(
            "Ato citado não consta da certidão",
            f"o título faz referência {'à edificação' if referencia_edificacao else 'ao imóvel'} conforme o {citado} da "
            f"matrícula {m.numero}. Não foi possível localizar esse ato no texto "
            f"consultado; confira na Tri7 antes de concluir que há omissão.",
            "Lei 6.015/1973, art. 225", ATENCAO)
        return

    edificacao = m.averbacao("EDIFICAÇÃO", "CONSTRUÇÃO")
    if not edificacao:
        return
    if not referencia_edificacao:
        return
    if any(t in nz.sem_acento(alvo.titulo).upper() for t in ('EDIFICACAO','CONSTRUCAO')):
        return

    c.acrescenta(
        "Remissão do título aponta outro ato",
        f"o título remete à edificação conforme o "
        f"{citado}, mas nesta matrícula o {citado} é "
        f'"{alvo.titulo.title()}" — foi localizada edificação no '
        f"{edificacao.rotulo}. Confira a remissão no título e na Tri7.",
        "Lei 6.015/1973, art. 225", EXIGE)


def _extensos_possiveis(area: str) -> list[str]:
    """Como o acervo escreve a área por extenso, nas duas formas que usa."""
    from . import extenso as ex

    inteiro, _, decimal = area.replace(".", "").partition(",")
    metros = int(inteiro)
    centimetros = int((decimal + "00")[:2])
    formas = [f"{ex.inteiro(metros)} metros quadrados"]
    if centimetros:
        formas.append(f"{ex.inteiro(metros)} metros e "
                      f"{ex.inteiro(centimetros)} centímetros quadrados")
    return formas


def _confere_extenso_da_area(m: Matricula, c: Conferencia) -> None:
    """Algarismo contra extenso, dentro do próprio fólio.

    Não é divergência com o contrato: é vício da matrícula, e o registrador o
    corrige de ofício. Fica em `atenção` porque a redação por extenso varia, e
    a mensagem mostra o que se esperava em vez de afirmar que está errado.
    """
    casou = AREA_COM_EXTENSO.search(m.descricao)
    if not casou:
        return
    area, escrito = casou.group(1), _limpa_espacos(casou.group(2))
    try:
        formas = _extensos_possiveis(area)
    except (ValueError, IndexError):
        return
    if any(_chave(escrito) == _chave(forma) for forma in formas):
        return
    c.acrescenta(
        "Área por extenso não confere",
        f'a matrícula {m.numero} escreve a área como {area}m² e, por extenso, '
        f'"{escrito}" — para {area}m² esperava-se "{formas[-1]}". Erro '
        f"evidente do próprio fólio, que se corrige de ofício.",
        "Lei 6.015/1973, art. 213, I", ATENCAO)


def _limpa_espacos(texto: str) -> str:
    return re.sub(r"\s+", " ", texto or "").strip()


def _confere_descricao(ficha: Ficha, m: Matricula, c: Conferencia) -> None:
    """Área, lote e quadra do contrato contra os da matrícula."""
    descricao = ficha.brutos.get("imovel", "")
    if not descricao:
        return

    lote_m, quadra_m = m.lote_quadra
    # O número tem de ter algarismo. Sem isso, "LOTE DE TERRAS N 04-A" fazia
    # capturar "DE" como número do lote e acusar divergência que não existe.
    #
    # `re.I` não é detalhe: a descrição do contrato vem toda em CAIXA ALTA, e
    # sem ele "LOTE" nunca casava — a conferência de lote e quadra passava
    # calada em cima de qualquer divergência.
    numero = r"(\d[\w-]*)"
    lote_c = re.search(r"\bLOTE\s+(?:DE\s+\w+\s+)?N?\.?º?\s*" + numero,
                       descricao, re.I)
    # A quadra costuma ser letra ("Quadra C"), então aqui o algarismo não pode
    # ser exigido — mas uma letra solta só vale como quadra se for uma ou duas.
    quadra_c = re.search(r"\bQUADRA\s+N?\.?º?\s*(\d[\w-]*|[A-Za-z]{1,2}\b)",
                         descricao, re.I)

    def diferente(a, b):
        """Compara "09-A" com "9-A" sem cegar para "C" contra "D".

        Só os dígitos não bastam: a quadra costuma ser letra, e reduzi-la a
        dígitos igualava todas elas.
        """
        def chave(valor):
            limpo = re.sub(r"[^0-9A-Za-zÀ-Ý]", "", nz.sem_acento(valor)).upper()
            return re.sub(r"^0+(?=\d)", "", limpo)

        return bool(a) and bool(b) and chave(a) != chave(b)

    if lote_c and diferente(lote_c.group(1), lote_m):
        c.acrescenta(
            "Lote divergente",
            f"o contrato indica o lote {lote_c.group(1)} e a matrícula "
            f"{m.numero} descreve o lote {lote_m}.",
            "Lei 6.015/1973, art. 225", IMPEDE)

    if quadra_c and diferente(quadra_c.group(1), quadra_m):
        c.acrescenta(
            "Quadra divergente",
            f"o contrato indica a quadra {quadra_c.group(1)} e a matrícula "
            f"descreve a quadra {quadra_m}.",
            "Lei 6.015/1973, art. 225", IMPEDE)

    area_c = Matricula(preambulo=descricao).area
    if area_m2(area_c) is not None and area_m2(m.area) is not None:
        if not areas_iguais(area_c, m.area):
            c.acrescenta(
                "Área divergente",
                f"o contrato indica {area_c} e a matrícula descreve {m.area}. "
                f"Divergência de área impede o registro sem retificação.",
                "Lei 6.015/1973, art. 176, §1º, II, 3, b; art. 213", IMPEDE)


def _estado_civil_e_regime(ficha: Ficha, m: Matricula, c: Conferencia) -> None:
    """O estado civil de quem vende tem de ser o que consta no fólio.

    Casou depois de adquirir? Precisa de averbação. Casou em regime que não é o
    legal? O pacto antenupcial precisa estar registrado.
    """
    titulares = nz.sem_acento(m.proprietarios).lower()

    for parte in ficha.vendedores:
        if isinstance(parte, Empresa):
            continue

        if hasattr(m, 'qualificacao_titular'):
            titulares = nz.sem_acento(m.qualificacao_titular(parte)).lower()

        nome = nz.nome_proprio(parte.nome)
        civil = (parte.estado_civil or "").lower()

        if civil == "casado" and "casad" not in titulares and \
                re.search(r"\bsolteir|divorciad|vi[úu]v", titulares):
            c.acrescenta(
                "Estado civil divergente",
                f"{nome} figura no contrato como casado(a), e a matrícula o(a) "
                f"qualifica com outro estado civil. O casamento precisa ser "
                f"averbado antes da transmissão.",
                "Lei 6.015/1973, art. 246; art. 176, §1º, II, 4, a", EXIGE)

        regime = nz.sem_acento(parte.regime_bens or "").lower()
        if regime and any(nz.sem_acento(r) in regime for r in REGIMES_COM_PACTO):
            if not m.averbacao("PACTO ANTENUPCIAL", "CONVENÇÃO ANTENUPCIAL"):
                c.acrescenta(
                    "Pacto antenupcial não comprovado",
                    f"{nome} declara regime de {parte.regime_bens}, que só se "
                    f"constitui por pacto antenupcial. O pacto deve ser lavrado "
                    f"por escritura pública e registrado no Livro 3 do Registro "
                    f"de Imóveis do domicílio dos cônjuges; sem registro não "
                    f"produz efeito perante terceiros.",
                    "Código Civil, arts. 1.640, 1.653 e 1.657; "
                    "Lei 6.015/1973, art. 167, I, 12", EXIGE)


def _especialidade_subjetiva(ficha: Ficha, m: Matricula, c: Conferencia) -> None:
    """A matrícula precisa qualificar o proprietário por inteiro."""
    if hasattr(m, 'qualificacoes_proprietarios'):
        for q in m.qualificacoes_proprietarios:
            if not q['texto']:
                c.acrescenta('Qualificação não extraída para conferência',
                    f"Não foi possível extrair a qualificação de {q['nome']} com segurança. Confira os atos na Tri7; isso não comprova ausência no fólio.",
                    'Conferência da extração', ATENCAO)
            else:
                from types import SimpleNamespace
                _especialidade_subjetiva(ficha, SimpleNamespace(proprietarios=q['texto']), c)
        return
    titulares = m.proprietarios
    if not titulares:
        return

    eh_juridica = bool(MARCAS_DE_PESSOA_JURIDICA.search(titulares))

    faltando = []
    if not re.search(r"\d{3}\.\d{3}\.\d{3}-\d{2}|\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}",
                     titulares):
        faltando.append("CPF ou CNPJ")
    # Empresa não tem estado civil — cobrá-lo dela era exigência sem sentido.
    if not eh_juridica and not re.search(
            r"solteir|casad|divorciad|vi[úu]v|separad", titulares, re.I):
        faltando.append("estado civil")

    if faltando:
        c.acrescenta(
            "Qualificação do proprietário incompleta na matrícula",
            f"falta no fólio: {', '.join(faltando)}. A qualificação precisa ser "
            f"completada por averbação antes da transmissão.",
            "Lei 6.015/1973, art. 176, §1º, II, 4, a; art. 246", EXIGE)


def _tributario(ficha: Ficha, c: Conferencia) -> None:
    """O que o contrato nunca traz e a serventia sempre exige."""
    c.acrescenta(
        "ITBI",
        "o contrato não comprova o imposto. Instrua com a guia de lançamento e "
        "a prova de quitação, conferindo se a avaliação corresponde ao valor "
        "declarado no título.",
        "Lei 6.015/1973, art. 289 (fiscalização do pagamento dos impostos "
        "devidos pelos atos apresentados)", ATENCAO)


def _ja_registrado(ficha: Ficha, m: Matricula, c: Conferencia) -> bool:
    """A matrícula anexada já contém o registro deste próprio título?

    Acontece o tempo todo: pede-se a certidão depois de registrar, ou anexa-se
    a atualizada por engano. Sem avisar, a conferência acusaria quebra de
    continuidade — porque o dono já é o adquirente do contrato — e a nota sairia
    dizendo o contrário do que se passa.
    """
    numero = nz.so_digitos(ficha.contrato.numero)
    # O número do contrato da CAIXA tem 15 dígitos. Abaixo de 10 não é ele, e
    # procurar uma sequência curta dentro do fólio acharia qualquer coisa.
    if len(numero) < 10:
        return False

    for ato in m.atos:
        if numero in nz.so_digitos(ato.texto):
            c.acrescenta(
                "Esta matrícula já contém o registro deste título",
                f"o {ato.rotulo}, de {ato.data}, cita o contrato "
                f"n.º {ficha.contrato.numero}. Para a conferência prévia valer, "
                f"anexe a matrícula como estava ANTES deste registro.",
                "conferência prévia pressupõe o fólio anterior ao ato", ATENCAO)
            return True
    return False


def confere(ficha: Ficha, m: Matricula) -> Conferencia:
    """A conferência prévia inteira, na ordem em que um registrador a faria."""
    c = Conferencia()

    # Se o título já está registrado nesta matrícula, o resto da conferência
    # mede o fólio errado e só produziria exigência falsa.
    if _ja_registrado(ficha, m, c):
        return c

    _matricula_viva(m, c)
    _continuidade(ficha, m, c)
    _confere_nome_do_titular(ficha, m, c)
    _onus(m, c)
    _confere_descricao(ficha, m, c)
    _confere_endereco(ficha, m, c)
    _confere_edificacao(ficha, m, c)
    _confere_remissao_ao_ato(ficha, m, c)
    _confere_extenso_da_area(m, c)
    _especialidade_objetiva(ficha, m, c)
    _especialidade_subjetiva(ficha, m, c)
    _estado_civil_e_regime(ficha, m, c)
    _tributario(ficha, c)
    return c
