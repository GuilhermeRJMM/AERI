# -*- coding: utf-8 -*-
"""Monta a nota: preambulo, exigencias numeradas com fundamentacao, fecho.

A saida e uma lista de blocos neutros - cada bloco diz seu papel e traz o texto
ja em pedacos com marcas de negrito/sublinhado. Quem transforma isso em .docx e
notadev/documento.py; separar os dois deixa o texto testavel sem abrir o Word.
"""
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .catalogo import Catalogo, BASE

FORMULA = "Dessa forma, faz-se necessári{}"

# O numero do artigo sai em negrito a parte, entao e retirado do corpo. A
# comparacao tolera espaco no sufixo porque a extracao do PDF do CNN escreve
# "Art. 440 -AV" onde o catalogo diz "Art. 440-AV". O sufixo so conta colado ao
# hifen: em "Art. 176 - O Livro nº 2" o "O" e artigo da lingua, e come-lo
# deixava a nota comecando em "Livro nº 2...".
TIRA_NUMERO = re.compile(r"^\s*Art(?:igo)?\.?\s*[\d.]+\s*[ºo°]?\s*"
                         r"(?:\s*[-–][A-Z]{1,3})?\s*[.\-–]*\s*")

# Ponto duplo sobra onde a nota de alteracao foi retirada ("...Lei no 6.015/73.."
# no art. 211-A). So colapsa a reticencia colada em palavra: a de trecho vetado
# ("... (Vetado) ...") vem solta entre espacos, e o "(...)" que separa o caput
# dos paragrafos citados e seguido de ")".
JUNTA_PONTOS = re.compile(r"(?<=[^\s.])\.{2,}(?=\s|$)")

# Ambas tem caso de regressao em ferramentas/testa_redator.py.


def _genero(providencia):
    """A formula concorda com a providencia que vem depois dela.

    "faz-se necessária a apresentação" mas "faz-se necessário o prévio registro".
    O acervo usa as duas formas; quem manda e o artigo que abre a providencia.
    A exigencia pode fixar isso em 'genero', quando a primeira palavra enganar.
    """
    return "o" if re.match(r"\s*(?:os?|um|dois)\s", providencia) else "a"


@dataclass
class Bloco:
    papel: str                      # corpo | exigencia | fund_norma | fund_artigo | vazio
    partes: list = field(default_factory=list)   # [(texto, marcas)]
    numero: int = None


@dataclass
class Item:
    """Uma exigencia escolhida pelo operador, com os dados que ela pede."""
    exigencia: str
    valores: dict = field(default_factory=dict)


class Redator:
    def __init__(self, catalogo=None):
        self.cat = catalogo or Catalogo()
        self.modelo = json.loads(
            (BASE / "dados" / "modelo.json").read_text(encoding="utf-8"))

    # ---------------------------------------------------------------- textos

    # Trecho entre colchetes so entra se os campos dele estiverem preenchidos:
    # "(CCIR)[ do imóvel da matrícula n.º {matricula}], documento exigido..."
    # Serve para o dado que enriquece a frase mas nao a sustenta.
    SEGMENTO = re.compile(r"\[([^\[\]]*)\]")

    def campos_obrigatorios(self, e):
        """Campos fora de colchetes - os que, faltando, impedem a nota."""
        fora = self.SEGMENTO.sub("", e["defeito"] + " " + e["providencia"])
        usados = set(re.findall(r"\{(\w+)\}", fora))
        return [c for c in e.get("campos", [])
                if c in usados and not self.cat.campos.get(c, {}).get("padrao")]

    def _resolve_segmentos(self, texto, valores):
        def decide(m):
            dentro = m.group(1)
            for chave in re.findall(r"\{(\w+)\}", dentro):
                v = str(valores.get(chave, "")).strip()
                if not v and not self.cat.campos.get(chave, {}).get("padrao"):
                    return ""
            return dentro
        return self.SEGMENTO.sub(decide, texto)

    def _preenche(self, texto, valores):
        """Troca {campo} pelos valores e pelos fragmentos. Nao aceita buraco.

        Campo com 'padrao' declarado e opcional: em branco, entra a redacao
        generica. Serve para o dado que nem sempre se tem em maos - o numero do
        protocolo do titulo anterior, por exemplo.
        """
        def troca(m):
            chave = m.group(1)
            if chave in valores:
                v = str(valores[chave]).strip()
                if v:
                    return v
                padrao = self.cat.campos.get(chave, {}).get("padrao")
                if padrao:
                    return padrao
                raise ValueError(f"o campo '{chave}' veio vazio")
            if chave in self.cat.fragmentos:
                return self.cat.fragmentos[chave]
            padrao = self.cat.campos.get(chave, {}).get("padrao")
            if padrao:
                return padrao
            raise ValueError(f"falta informar o campo '{chave}'")
        return re.sub(r"\{(\w+)\}", troca, self._resolve_segmentos(texto, valores))

    def _exigencia(self, item, numero):
        e = self.cat.exigencia(item.exigencia)
        faltando = [c for c in self.campos_obrigatorios(e) if c not in item.valores]
        if faltando:
            raise ValueError(f"exigencia '{e['id']}': falta informar "
                             + ", ".join(faltando))

        defeito = self._preenche(e["defeito"], item.valores)
        providencia = self._preenche(e["providencia"], item.valores)
        fecho = self.cat.fragmentos[e["fecho"]]

        genero = e.get("genero") or _genero(providencia)
        blocos = [Bloco("exigencia", numero=numero, partes=[
            (defeito + " ", set()),
            (FORMULA.format(genero), {"negrito", "sublinhado"}),
            (" " + providencia + ", " + fecho + ".", set()),
        ])]

        # fundamentacao: cabecalho da norma uma vez, depois os artigos
        if e.get("fundamentos"):
            blocos.append(Bloco("vazio_fund"))   # respiro entre a exigência e a lei

        norma_atual = None
        for f in e.get("fundamentos", []):
            norma, artigo, partes = f["norma"], f["artigo"], f.get("partes")
            if norma != norma_atual:
                if norma_atual is not None:
                    # respiro entre normas diferentes: sem ele o ultimo artigo de
                    # uma lei cola no cabecalho da seguinte e as duas se confundem
                    blocos.append(Bloco("vazio_fund"))
                blocos.append(Bloco("fund_norma", partes=[
                    (self.cat.nome_norma(norma), {"negrito"})]))
                norma_atual = norma
            texto = self.cat.texto_dispositivo(norma, artigo, partes)
            corpo = JUNTA_PONTOS.sub(".", TIRA_NUMERO.sub("", texto))
            blocos.append(Bloco("fund_artigo", partes=[
                (artigo + ".", {"negrito"}), (" " + corpo, set())]))

        # Jurisprudencia: entra depois da lei, sob cabecalho proprio, porque nao
        # e norma - e o modo como os tribunais leem a norma.
        if e.get("precedentes"):
            if e.get("fundamentos"):
                blocos.append(Bloco("vazio_fund"))
            blocos.append(Bloco("fund_norma", partes=[("Jurisprudência", {"negrito"})]))
            for pid in e["precedentes"]:
                p = self.cat.precedente(pid)
                blocos.append(Bloco("fund_artigo", partes=[
                    (p["identificacao"] + ":", {"negrito"}),
                    (" “" + p["texto"] + "”", set())]))

        if e.get("fundamentos") or e.get("precedentes"):
            blocos.append(Bloco("vazio"))
        return blocos

    # ------------------------------------------------------------------ nota

    def redige(self, especie, titulo, itens, judicial=False):
        esp = self.modelo["especies"].get(especie)
        if esp is None:
            raise KeyError(f"especie '{especie}' nao existe em modelo.json "
                           f"(ha: {', '.join(self.modelo['especies'])})")
        if not itens:
            raise ValueError("uma nota sem exigencia nao e nota")

        blocos = []
        if judicial:
            blocos.append(Bloco("corpo", partes=[
                (self.modelo["preambulo_titulo_judicial"], set())]))
            blocos.append(Bloco("vazio"))
        blocos.append(Bloco("corpo", partes=[
            (self._preenche(esp["preambulo"], {"titulo": titulo}), set())]))
        blocos.append(Bloco("vazio"))

        for i, item in enumerate(itens, 1):
            blocos.extend(self._exigencia(item, i))

        # A ressalva vai emendada ao fecho, e nao em paragrafo proprio: e parte
        # do aviso final, nao um recado solto no pe da nota.
        fecho = esp["fecho"]
        if esp.get("ressalva") and self.modelo.get("ressalva_reapresentacao"):
            fecho += " " + self.modelo["ressalva_reapresentacao"]
        blocos.append(Bloco("corpo", partes=[(fecho, set())]))
        return blocos

    def nao_revisadas(self, itens):
        """Exigencias cuja fundamentacao ainda nao foi validada por registrador."""
        fora = []
        for it in itens:
            e = self.cat.exigencia(it.exigencia)
            if not e.get("revisado"):
                fora.append(e["id"])
        return fora

    def em_texto(self, blocos):
        """Versao em texto puro, para conferir sem abrir o Word."""
        linhas = []
        for b in blocos:
            if b.papel in ("vazio", "vazio_fund"):
                linhas.append("")
                continue
            t = "".join(p for p, _ in b.partes)
            if b.papel == "exigencia":
                linhas.append(f"{b.numero}. {t}")
            elif b.papel == "fund_norma":
                linhas.append(f"        {t}")
            elif b.papel == "fund_artigo":
                linhas.append(f"        {t}")
            else:
                linhas.append(t)
        return "\n".join(linhas)
