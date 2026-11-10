"""Filtro editorial da lista; não cria exigências nem decide sua aplicação jurídica."""
PERFIS=[
    {'id':'transferencia','rotulo':'Compra e venda / transmissão','termos':['compra e venda','venda e compra','permuta','dacao em pagamento','arrematacao','adjudicacao']},
    {'id':'inventario','rotulo':'Inventário / partilha','termos':['inventario','partilha','carta de adjudicacao']},
    {'id':'doacao','rotulo':'Doação','termos':['doacao']},
    {'id':'construcao','rotulo':'Construção / edificação','termos':['construcao','edificacao','habite se','demolicao']},
    {'id':'area','rotulo':'Área / georreferenciamento','termos':['retificacao de area','georreferenciamento','georreferenciada','certificacao sigef']},
    {'id':'parcelamento','rotulo':'Desmembramento / parcelamento','termos':['desmembramento','desdobro','loteamento','parcelamento','remembramento','unificacao']},
    {'id':'condominio','rotulo':'Condomínio / incorporação','termos':['condominio','incorporacao']},
    {'id':'garantia','rotulo':'Garantias','termos':['alienacao fiduciaria','penhor','hipoteca','cedula rural','cedula de credito','cedula de produto rural']},
    {'id':'cancelamento','rotulo':'Cancelamento / baixa','termos':['cancelamento','baixa de garantia','liberacao de garantia']},
    {'id':'cadastro','rotulo':'Atualização cadastral','termos':['averbacao de obito','certidao de obito','alteracao de nome','averbacao de casamento','atualizacao cadastral','averbacao de cep']},
]
COMUNS={'casamento','certidao','continuidade','copia','firma','pj','prazo','procuracao','protocolo','qualif','requerimento','selo'}
GRUPOS={
 'transferencia':{'area','cci','ccir','cep','cib','car','dare','fiduciaria','incapaz','itbi','itcd','itr','levantamento','onus','pacto','reserva','sefaz','transcricao','uniao','usufruto'},
 'inventario':{'area','cci','ccir','cep','cib','car','dare','fiduciaria','incapaz','itcd','itr','obito','onus','pacto','reserva','sefaz','transcricao','uniao','usufruto'},
 'doacao':{'area','cci','ccir','cep','cib','car','dare','doacao','fiduciaria','incapaz','itcd','itr','onus','pacto','reserva','sefaz','transcricao','uniao','usufruto'},
 'construcao':{'edificacao','cci','cep','onus','fiduciaria','transcricao'},
 'area':{'art_tec','car','ccir','cep','cib','confront','geo','itr','memorial','onus','reserva','retificacao','sig','transcricao'},
 'parcelamento':{'art_tec','car','ccir','cci','cep','cib','confront','desmembramento','geo','itr','loteamento','memorial','onus','reserva','retificacao','sig','transcricao'},
 'condominio':{'art_tec','cci','cep','condominio','edificacao','onus','transcricao'},
 'garantia':{'car','ccir','cci','cep','cib','fiduciaria','itr','onus','pacto','penhor','transcricao','uniao','usufruto'},
 'cancelamento':{'fiduciaria','onus','penhor','servidao','usufruto','obito'},
 'cadastro':{'car','ccir','cci','cep','cib','itr','obito','pacto','uniao','transcricao'},
}


def contextos(exigencia):
    if exigencia['assunto'] in COMUNS or exigencia['id']=='emolumentos-nao-complementados':
        return ['*']
    if exigencia['assunto']=='emolumentos':
        return ['transferencia','garantia']
    return [p for p,assuntos in GRUPOS.items() if exigencia['assunto'] in assuntos]
