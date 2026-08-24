# -*- coding: utf-8 -*-
"""Carrega o catalogo e responde o que a nota precisa saber."""
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent


class Catalogo:
    def __init__(self, pasta=None):
        d = Path(pasta) if pasta else BASE / "dados"
        self.normas = {n["id"]: n for n in
                       json.loads((d / "normas.json").read_text(encoding="utf-8"))["normas"]}
        self.dispositivos = {(x["norma"], x["artigo"]): x for x in
                             json.loads((d / "dispositivos.json").read_text(encoding="utf-8"))["dispositivos"]}
        cat = json.loads((d / "exigencias.json").read_text(encoding="utf-8"))
        self.fragmentos = cat["fragmentos"]
        self.campos = cat.get("campos", {})
        self.exigencias = {e["id"]: e for e in cat["exigencias"]}

        # Precedentes: para a regra que nao esta em artigo de lei. Arquivo
        # opcional - o catalogo funciona sem ele.
        p = d / "precedentes.json"
        self.precedentes = ({x["id"]: x for x in
                             json.loads(p.read_text(encoding="utf-8"))["precedentes"]}
                            if p.exists() else {})

    def precedente(self, id_):
        if id_ not in self.precedentes:
            raise KeyError(f"precedente '{id_}' nao existe em precedentes.json")
        return self.precedentes[id_]

    def exigencia(self, id_):
        if id_ not in self.exigencias:
            raise KeyError(f"exigencia '{id_}' nao existe no catalogo")
        return self.exigencias[id_]

    def texto_dispositivo(self, norma, artigo, partes=None):
        """Texto oficial do artigo, montado para a nota.

        Sem 'partes', sai so o caput - artigos como o 176 da Lei 6.015 tem oito
        mil caracteres e nao cabem numa nota. Com 'partes', o caput e seguido dos
        paragrafos e incisos pedidos, separados por '(...)' para marcar o que foi
        omitido, do jeito que as notas do cartorio ja faziam.
        'partes': ["*"] traz o artigo inteiro.
        """
        d = self.dispositivos.get((norma, artigo))
        if d is None:
            raise KeyError(f"{norma} {artigo} nao esta em dispositivos.json - "
                           f"rode ferramentas/monta_dispositivos.py")
        if partes and partes == ["*"]:
            return d["texto"]
        if not partes:
            return d["caput"]

        disponiveis = {p["rotulo"]: p["texto"] for p in d["partes"]}
        # A ultima trava: dispositivo revogado nao sai impresso numa nota, ainda
        # que o catalogo o aponte. Errar aqui e erro do cartorio perante a
        # Corregedoria - o custo nao e simetrico.
        mortas = {x["rotulo"]: x["motivo"] for x in d.get("revogadas", [])}
        escolhidas = []
        for r in partes:
            if r in mortas:
                raise KeyError(f"{norma} {artigo} {r} esta revogada "
                               f"({mortas[r]}) e nao pode ser citada")
            if r not in disponiveis:
                raise KeyError(
                    f"{norma} {artigo} nao tem a parte '{r}' "
                    f"(tem: {', '.join(disponiveis) or 'nenhuma'})")
            escolhidas.append(disponiveis[r])
        return d["caput"] + " (...) " + " (...) ".join(escolhidas)

    def nome_norma(self, id_):
        return self.normas[id_]["nome"]
