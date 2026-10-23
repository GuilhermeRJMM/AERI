"""Observa o cálculo oficial sem alterar seus saldos ou decisões."""
from backend.app.analise.evidencias import codigo_ato, normalizar


def mesma_pessoa(a, b):
    import re
    documento_a = re.sub(r"\D", "", str(a.get("cpf") or ""))
    documento_b = re.sub(r"\D", "", str(b.get("cpf") or ""))
    if len(documento_a) in (11, 14) and len(documento_b) in (11, 14):
        return documento_a == documento_b
    return bool(normalizar(a.get("nome"))) and normalizar(a.get("nome")) == normalizar(b.get("nome"))


class ObservadorCadeia:
    def __init__(self, estado, destino=None):
        self.estado = estado
        self.destino = destino
        self.antes = None
        self.codigo = ""
        self.acao = "ATUALIZACAO"
        self.fontes = []

    def _foto(self):
        return {chave: {
            "nome": dados["nome"], "cpf": dados.get("cpf_original", ""),
            "proporcao": dados["proporcao"],
        } for chave, dados in self.estado.items() if dados["proporcao"] > 0.01}

    def iniciar(self, ato, acao="ATUALIZACAO"):
        if self.destino is None:
            return
        self.concluir()
        self.antes = self._foto()
        self.codigo = ato if isinstance(ato, str) else codigo_ato(ato)
        self.acao = acao
        self.fontes = []

    def efeito(self, acao, fontes=None):
        self.acao = acao
        self.fontes = fontes or []

    def concluir(self):
        if self.destino is None or self.antes is None:
            return
        anteriores = dict(self.antes)
        mudancas = []
        for chave, depois in self._foto().items():
            chave_antes = chave if chave in anteriores else next((
                k for k, pessoa in anteriores.items()
                if mesma_pessoa(pessoa, depois) or (
                    self.acao == "RETIFICACAO"
                    and normalizar(pessoa["nome"]) == normalizar(depois["nome"])
                )
            ), None)
            antes = anteriores.pop(chave_antes, None)
            if antes != depois:
                fontes = [codigo for codigo, pessoas in self.fontes if any(mesma_pessoa(p, depois) for p in pessoas)]
                mudancas.append({"antes": antes, "depois": depois,
                                 "atos": fontes or [codigo for codigo, _ in self.fontes] or [self.codigo]})
        mudancas.extend({"antes": pessoa, "depois": None} for pessoa in anteriores.values())
        if mudancas:
            self.destino.append({"ato": self.codigo, "acao": self.acao, "mudancas": mudancas})
        self.antes = None


def historico_proprietario(proprietario, rastro):
    referencia = proprietario
    historico = []
    for evento in reversed(rastro or []):
        mudanca = next((m for m in evento["mudancas"] if m["depois"] and mesma_pessoa(m["depois"], referencia)), None)
        if mudanca is None:
            continue
        antes, depois = mudanca["antes"], mudanca["depois"]
        percentual_antes = antes["proporcao"] if antes else 0.0
        historico.append({
            "ato": (mudanca.get("atos") or [evento["ato"]])[-1],
            "atos": mudanca.get("atos") or [evento["ato"]],
            "acao": evento["acao"], "nome_no_ato": depois["nome"],
            "percentual_antes": percentual_antes,
            "percentual_depois": depois["proporcao"],
            "variacao_percentual": depois["proporcao"] - percentual_antes,
        })
        if antes is None:
            break  # uma aquisição nova não herda um domínio já alienado integralmente
        referencia = antes
    return list(reversed(historico))
