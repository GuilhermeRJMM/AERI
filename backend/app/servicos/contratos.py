"""Adaptação do Preenchedor-de-Contratos ao motor, à sessão e ao banco do AERI."""
import base64
import copy
import hashlib
import json
import math
import os
import re
import unicodedata
from dataclasses import fields, is_dataclass
from types import SimpleNamespace

from cryptography.fernet import Fernet

from backend.app.contratos_nucleo import extrator, ficha as modelos, matricula as leitor, qualificacao, servico
from backend.app.contratos_nucleo.comparacao import areas_iguais, designativo

VERSAO_CONFRONTO = '20260901-confronto-v4-sem-blocos-de-operacao'
from backend.app.servicos.analise_matricula import analisar_matricula
from backend.app.servicos.documentos_contratos import extrair_documento, conferir_prazo


def cifrador():
    segredo = os.getenv("AERI_CONTRATOS_ENCRYPTION_KEY") or os.getenv("AERI_BUSCAS_HMAC_KEY")
    if not segredo or len(segredo) < 32:
        raise RuntimeError("Configure a chave de proteção dos contratos no servidor e no worker.")
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(("AERI:CONTRATOS:"+segredo).encode()).digest()))


def cifrar(payload):
    return cifrador().encrypt(json.dumps(payload, ensure_ascii=False, allow_nan=False).encode()).decode()


def decifrar(valor):
    return json.loads(cifrador().decrypt(valor.encode())) if valor else {}


def chave_texto(valor):
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", unicodedata.normalize("NFKD", str(valor)).encode("ascii","ignore").decode().lower())).strip()


def documentos_publicos(dados):
    # Nunca repassa caminhos de rede, usuário de status ou URL original do GED.
    return [{k:d.get(k) for k in ("ged_documento_id","tipo_documento","categoria","descricao","versao","status_atual")}
            for d in dados if isinstance(d,dict) and d.get("ged_documento_id")]


def ficha_de(dados):
    """Round-trip completo: o adapter original perdia Empresa e terreno/obra."""
    def montar(classe, valores, profundidade=0):
        if not isinstance(valores, dict) or profundidade > 5:
            raise ValueError("Estrutura de ficha inválida.")
        instancia=classe()
        for campo in fields(instancia):
            if campo.name not in valores:
                continue
            v=valores[campo.name]; padrao=getattr(instancia,campo.name)
            if campo.name in {"vendedores","compradores"}:
                if not isinstance(v,list) or len(v)>100 or any(not isinstance(p,dict) for p in v):
                    raise ValueError("Partes inválidas.")
                v=[montar(modelos.Empresa if p.get("tipo")=="juridica" else modelos.Pessoa,p,profundidade+1) for p in v]
            elif campo.name in {"conjuge","representante"}:
                v=montar(modelos.Pessoa,v,profundidade+1) if v else None
            elif campo.name=="procuracoes":
                if not isinstance(v,list) or len(v)>30:
                    raise ValueError("Procurações inválidas.")
                v=[montar(modelos.Procuracao,p,profundidade+1) for p in v]
            elif is_dataclass(padrao):
                v=montar(type(padrao),v,profundidade+1)
            elif isinstance(padrao,float):
                if isinstance(v,bool): raise ValueError("Valor numérico inválido.")
                v=float(v or 0)
                if not math.isfinite(v) or v < 0:
                    raise ValueError("Valor numérico inválido.")
            elif isinstance(padrao,bool):
                if not isinstance(v,bool): raise ValueError("Indicador inválido.")
            elif isinstance(padrao,str):
                if not isinstance(v,str) or len(v)>100_000: raise ValueError("Campo textual inválido.")
            elif isinstance(padrao,dict):
                if not isinstance(v,dict) or any(not isinstance(s,str) for s in v.values()):
                    raise ValueError("Origens inválidas.")
            setattr(instancia,campo.name,v)
        return instancia
    return montar(modelos.Ficha,dados)


def campos_ficha(dados, prefixo=""):
    saida=[]
    if isinstance(dados,dict):
        for k,v in dados.items():
            if k in {"origens","brutos"}:
                continue
            saida.extend(campos_ficha(v, f"{prefixo}.{k}" if prefixo else k))
    elif isinstance(dados,list):
        for i,v in enumerate(dados):
            saida.extend(campos_ficha(v,f"{prefixo}.{i}"))
    elif dados is not None:
        saida.append({"campo":prefixo,"valor":dados})
    return saida


def documento_valido(valor):
    n=re.sub(r"\D","",str(valor))
    if len(n) not in (11,14) or len(set(n))==1:
        return False
    base=n[:-2]
    for peso in ([list(range(10,1,-1)),list(range(11,1,-1))] if len(n)==11 else
                 [[5,4,3,2,9,8,7,6,5,4,3,2],[6,5,4,3,2,9,8,7,6,5,4,3,2]]):
        resto=sum(int(d)*p for d,p in zip(base,peso))%11
        base+=str(0 if resto<2 else 11-resto)
    return base==n


# Documentos que convivem com o contrato no mesmo protocolo do GED e sao
# selecionados por engano. Dizer o que o arquivo E resolve na hora; dizer que
# ele "esta fora da familia CAIXA" faz procurar problema no contrato certo.
# Medido no acervo: dois conferentes diferentes bateram nisso escolhendo a guia
# de ITBI do protocolo 185.623 e do 185.771.
OUTROS_DOCUMENTOS = (
    ("imposto sobre transmissao de bens imoveis", "guia de ITBI da Prefeitura"),
    ("guia de informacao", "guia de ITBI da Prefeitura"),
    ("certidao negativa", "certidão negativa"),
    ("certidao de onus", "certidão de ônus"),
    ("matricula n", "cópia de matrícula"),
    ("procuracao", "procuração"),
)


def _documento_reconhecido(texto_chave: str) -> str | None:
    for marca, nome in OUTROS_DOCUMENTOS:
        if marca in texto_chave:
            return nome
    return None


def extrair_contrato(dados, progresso=None, *, permitir_ocr=True, prazo=None):
    documento=extrair_documento(dados,progresso,permitir_ocr=permitir_ocr,prazo=prazo)
    conferir_prazo(prazo)
    chave=chave_texto(documento["texto"])
    if "caixa economica federal" not in chave:
        outro=_documento_reconhecido(chave)
        if outro:
            raise ValueError(
                f"O documento selecionado é {outro}, não o contrato. "
                "Volte ao protocolo e escolha o contrato da CAIXA.")
        raise ValueError("Contrato fora da família CAIXA suportada. O sistema não pode presumir a instituição credora.")
    ficha=servico.para_json(extrator.extrai_do_texto(documento["texto"]))
    # extrai_do_texto so recebe texto e marca "nato-digital" por padrao; quem
    # sabe a origem e o documento. A marca nao e cosmetica: a minuta so pede
    # confirmacao dos campos que o OCR nao defende quando ela diz OCR
    # (minuta._confere_o_que_o_ocr_nao_defende), e a tela mostra qual motor leu,
    # porque Tesseract e Windows erram coisas diferentes. Sem isto, contrato
    # digitalizado seguia para a minuta como se fosse nato-digital.
    if documento["ocr"]:
        motores = sorted({
            pagina["metodo"].replace("OCR ", "").lower()
            for pagina in documento["paginas"] if pagina["metodo"].startswith("OCR")
        })
        ficha.setdefault("origens", {})["_natureza"] =             "digitalizado, lido por OCR (" + ", ".join(motores) + ")"
    if not ficha["contrato"]["numero"] or not ficha["vendedores"] or not ficha["compradores"]:
        raise ValueError("O modelo do contrato não foi reconhecido suficientemente. A base atual atende contratos habitacionais CAIXA; confira o documento selecionado.")
    alertas=[]
    for pagina in documento["paginas"]:
        if pagina["insuficiente"]:
            alertas.append({"campo":f"Página {pagina['pagina']}","motivo":"Texto insuficiente. Confira a página original, inclusive anexos e assinaturas."})
    for campo in campos_ficha(ficha):
        c,v=campo["campo"],campo["valor"]
        if c.endswith((".cpf",".cnpj")) and v and not documento_valido(v):
            alertas.append({"campo":c,"motivo":"CPF/CNPJ com dígitos verificadores inválidos. Confira o original."})
        elif documento["ocr"] and v:
            alertas.append({"campo":c,"motivo":"Obtido por OCR: conferir com a página original; confiança não equivale a certeza."})
        elif v in ("",0):
            alertas.append({"campo":c,"motivo":"Não identificado ou não aplicável; confirme antes de gerar."})
    evidencias={}
    for campo in campos_ficha(ficha):
        valor=str(campo["valor"]).strip()
        paginas=[p["pagina"] for p in documento["paginas"] if valor and chave_texto(valor) in chave_texto(p["texto"])]
        evidencias[campo["campo"]]={"paginas":paginas,"origem":ficha["origens"].get(campo["campo"],ficha["origens"].get(campo["campo"].split('.')[0],"Parser — conferir documento"))}
    conferir_prazo(prazo)
    return {"documento":documento,"fichaOriginal":ficha,"ficha":copy.deepcopy(ficha),"alertasExtracao":alertas,"evidencias":evidencias}


def completar_juros_ausentes(payload):
    """Rele o B9 salvo ao reconfrontar, sem substituir taxa editada pelo usuario.

    A extracao original e imutavel. O complemento fica identificado em separado
    e so e aplicado quando o trio estava inteiramente vazio, inclusive na ficha
    original. Nao usa dados da matricula nem consulta novamente o GED.
    """
    campos = ("nominal_ao_ano", "efetiva_ao_ano", "efetiva_ao_mes")
    ficha = payload.get("ficha") or {}
    juros = ficha.get("financiamento", {}).get("juros", {})
    originais = payload.get("fichaOriginal", {}).get("financiamento", {}).get("juros", {})
    if any(juros.get(c) not in (None, "") or originais.get(c) not in (None, "") for c in campos):
        return False
    documento = payload.get("documento") or {}
    taxa, origem = extrator._taxa_contratada(extrator._limpa(documento.get("texto", "")))
    if not taxa:
        return False
    ficha.setdefault("financiamento", {}).setdefault("juros", {}).update(servico.para_json(taxa))
    ficha.setdefault("origens", {}).pop("financiamento._alerta_juros", None)
    ficha["origens"]["financiamento.juros"] = origem
    caminhos = {"financiamento.juros." + c for c in campos}
    payload["alertasExtracao"] = [a for a in payload.get("alertasExtracao", []) if a.get("campo") not in caminhos]
    for c in campos:
        caminho = "financiamento.juros." + c
        valor = getattr(taxa, c)
        payload.setdefault("complementosExtracao", {})[caminho] = {"valor": valor, "origem": origem}
        paginas = [p["pagina"] for p in documento.get("paginas", [])
                   if "Taxa Contratada" in p.get("texto", "") and valor in p.get("texto", "")]
        payload.setdefault("evidencias", {})[caminho] = {"paginas": paginas, "origem": origem}
    return True


def valor_imovel(analise, rotulo):
    for itens in analise.get("imovel",{}).values():
        if isinstance(itens,list):
            for i in itens:
                if isinstance(i,dict) and chave_texto(i.get("rotulo",""))==chave_texto(rotulo):
                    v=i.get("valor","")
                    return "" if v=="NÃO CONSTA" else str(v)
    return ""


class FolioAeri:
    """Preserva conferências do upstream, mas não cria outro motor de titularidade/ônus."""
    def __init__(self,texto,analise,numero):
        self.folio=leitor.le(texto); self.analise=analise; self.numero=str(numero)
    def __getattr__(self,nome):
        return getattr(self.folio,nome)
    @property
    def proprietarios(self):
        return "; ".join(f"{p['nome']}, {p.get('cpf_cnpj',p.get('cpf',''))}" for p in self.analise["proprietarios_atuais"])
    @property
    def qualificacoes_proprietarios(self):
        # A titularidade continua sendo exclusivamente a do motor principal.
        # Qualificações não podem introduzir transmitentes/garantes como titulares.
        titulares = self.analise['proprietarios_atuais']
        def normalizar(t):
            return ''.join(c for c in unicodedata.normalize('NFD', t) if not unicodedata.combining(c)).upper()
        nomes = [normalizar(p['nome']) for p in titulares]
        fontes = []
        inicial = re.search(r'PROPRIET[ÁA]RI[AO]S?\s*:(.*)', self.folio.preambulo, re.I | re.S)
        if inicial:
            fontes.append(inicial.group(1))
        for ato in self.folio.atos:
            adquirentes = re.search(r'\bADQUIRENTES?\s*:(.*?)(?=\b(?:IM[ÓO]VEL|ORIGEM|TRANSMITENTES?|VENDEDORES?)\s*:|$)', ato.texto, re.I | re.S)
            if adquirentes:
                fontes.append(adquirentes.group(1))
            elif ato.especie == 'AV' and re.search(r'QUALIFICA|INSER[ÇC][ÃA]O.*DADOS|CASAMENTO|ESTADO CIVIL', ato.titulo, re.I):
                fontes.append(ato.texto)
        saida = []
        for p, nome in zip(titulares, nomes):
            encontrada = ''
            for fonte in fontes:
                pos = re.search(r'(?<!\w)'+re.escape(nome)+r'(?!\w)', normalizar(fonte))
                if not pos:
                    continue
                trecho = fonte[pos.start():]
                # Cortar antes de outro titular ou de outra função no ato.
                limites = [len(trecho)]
                for outro in nomes:
                    if outro != nome:
                        prox = re.search(r'(?<!\w)'+re.escape(outro)+r'(?!\w)', normalizar(trecho))
                        if prox: limites.append(prox.start())
                papel = re.search(r'\b(?:INTERVENIENTE|ANUENTE|DEVEDOR|CREDOR|TRANSMITENTE|PROCURADOR|REPRESENTANTE)\w*\s*:', trecho, re.I)
                if papel: limites.append(papel.start())
                candidata = trecho[:min(limites)].strip(' ,;')
                if re.search(r'solteir|casad|divorciad|vi[úu]v|separad', candidata, re.I) or not encontrada:
                    encontrada = candidata
            saida.append({'nome':p['nome'], 'documento':p.get('cpf_cnpj',p.get('cpf','')), 'texto':encontrada})
        return saida
    def qualificacao_titular(self, parte):
        doc = re.sub(r'\D', '', parte.cpf or '')
        for q in self.qualificacoes_proprietarios:
            if (doc and doc == re.sub(r'\D', '', q['documento'])) or chave_texto(parte.nome) == chave_texto(q['nome']):
                return q['texto']
        return ''
    @property
    def encerrada(self):
        return self.analise["imovel"]["situacao"]["status"]=="ENCERRADA"
    @property
    def onus_vigentes(self):
        return [SimpleNamespace(rotulo=a["codigo"],titulo=a.get("tipo_onus") or a["categoria"],texto=a.get("descricao",""))
                for a in self.analise["atos"] if a["status"]=="ATIVO" and a["categoria"] in {"ÔNUS","RESTRIÇÃO","PUBLICIDADE"}]
    @property
    def area(self): return valor_imovel(self.analise,"Área")
    @property
    def cep(self): return valor_imovel(self.analise,"CEP")
    @property
    def designacao_cadastral(self): return valor_imovel(self.analise,"CCI") or valor_imovel(self.analise,"Cadastro Municipal")
    @property
    def lote_quadra(self): return valor_imovel(self.analise,"Lote"),valor_imovel(self.analise,"Quadra")


def confrontar(payload,texto,numero,regras=None):
    analise=analisar_matricula(texto,regras_aprendidas=regras,numero_matricula=str(numero))
    ficha=ficha_de(payload["ficha"])
    folio=FolioAeri(texto,analise,numero)
    conferencia=qualificacao.confere(ficha,folio)
    exigencias=servico._exigencias_em_json(conferencia)
    comparacoes=[]
    def linha(campo,contrato,matricula):
        normalizar = (lambda v: re.sub(r"\D", "", str(v))) if campo=="matricula.numero" or campo.endswith((".cpf",".cnpj")) else chave_texto
        if campo in {'imovel.lote', 'imovel.quadra'}: normalizar = designativo
        iguais = areas_iguais(contrato, matricula) if campo == 'imovel.area' else normalizar(contrato)==normalizar(matricula)
        status="COMPATIVEL" if contrato and matricula and iguais else "REVISAR"
        aplicavel = campo=="matricula.numero" or campo.startswith("vendedores.")
        comparacoes.append({"campo":campo,"contrato":contrato or "NÃO CONSTA","matricula":matricula or "NÃO CONSTA","situacao":status,
                            "permiteMatricula":bool(aplicavel and matricula),"somenteConferencia":not aplicavel})
    linha("matricula.numero",ficha.matricula.numero,str(numero))
    contrato_imovel=payload["ficha"].get("brutos",{}).get("imovel","")
    mcontrato=leitor.le("IMÓVEL: "+contrato_imovel)
    for campo,a,b in [("imovel.area",mcontrato.area,folio.area),("imovel.lote",mcontrato.lote_quadra[0],folio.lote_quadra[0]),
                       ("imovel.quadra",mcontrato.lote_quadra[1],folio.lote_quadra[1])]:
        linha(campo,a,b)
    for i,p in enumerate(payload["ficha"].get("vendedores",[])):
        doc=re.sub(r"\D","",p.get("cnpj") or p.get("cpf", ""))
        titulares=[t for t in analise["proprietarios_atuais"] if doc and doc==re.sub(r"\D","",t.get("cpf_cnpj",t.get("cpf","")))]
        linha(f"vendedores.{i}.{'razao_social' if p.get('tipo')=='juridica' else 'nome'}",p.get("nome") or p.get("razao_social"),titulares[0]["nome"] if len(titulares)==1 else "")
        linha(f"vendedores.{i}.{'cnpj' if p.get('tipo')=='juridica' else 'cpf'}",doc,doc if len(titulares)==1 else "")
    # Comprador, credora, valores e financiamento pertencem a nova operacao:
    # nao existe contraparte na matricula para comparar. Eles ja sao conferidos
    # campo a campo na ficha, com a confirmacao unica antes de gerar. Emiti-los
    # como pendencia obrigava a uma decisao e uma justificativa por bloco sem
    # nada a decidir, e escondia as divergencias reais no meio do formulario.
    return {"numero":str(numero),"versaoRegras":VERSAO_CONFRONTO,"textoHash":hashlib.sha256(texto.encode()).hexdigest(),"texto":texto,
            "analise":analise,"comparacoes":comparacoes,"exigencias":exigencias}


def aplicar_decisoes(payload, ficha, decisoes, conferida):
    """Não aceita confirmação vazia nem ficha diferente daquela confrontada."""
    nova=servico.para_json(ficha_de(ficha))
    if nova != payload["ficha"]:
        raise ValueError("A ficha foi editada. Consulte/confronte a matrícula novamente antes de gerar.")
    if conferida is not True or not isinstance(decisoes,dict):
        raise ValueError("Confirme a conferência da extração.")
    aplicadas=[]
    for c in payload["confronto"]["comparacoes"]:
        decisao=decisoes.get(c["campo"])
        if decisao is None and c["situacao"]=="COMPATIVEL": continue
        if not isinstance(decisao,dict) or decisao.get("acao") not in {"CONTRATO","MATRICULA","MANUAL"}:
            raise ValueError(f"Registre uma decisão para o campo pendente: {c['campo']}.")
        justificativa=decisao.get("justificativa")
        if not isinstance(justificativa,str) or not justificativa.strip() or len(justificativa)>2000:
            raise ValueError(f"Informe a justificativa da decisão: {c['campo']}.")
        if decisao["acao"]=="MATRICULA":
            if not c.get("permiteMatricula"):
                raise ValueError("Este campo exige conferência manual; não há valor substituível na matrícula.")
            partes=c["campo"].split('.'); alvo=nova
            for k in partes[:-1]: alvo=alvo[int(k)] if isinstance(alvo,list) else alvo[k]
            alvo[partes[-1]]=c["matricula"]
            nova["origens"][c["campo"]]="MATRÍCULA — escolha humana"
        aplicadas.append({"campo":c["campo"],**decisao,"somenteConferencia":c.get("somenteConferencia",False)})
    return nova, aplicadas
