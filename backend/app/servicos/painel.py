"""Catálogo operacional e indicadores; nenhuma regra registral mora no painel."""
MODULOS = (
    ("onus", "certidao", "Ônus e Matrícula", "Analise o texto, os proprietários e as restrições do imóvel.", "processar_matricula", "Consultas"),
    ("buscas", "certidao", "Buscas", "Pesquise titularidade por nome ou documento.", "acessar_buscas", "Consultas"),
    ("incra", "certidao", "INCRA", "Organize as comunicações de atos rurais.", "processar_incra", "Rotinas"),
    ("livroproto", "certidao", "Livro de Protocolos", "Confira os protocolos e acompanhe ocorrências do dia.", "acessar_livro_protocolos", "Conferência"),
    ("custas", "certidao", "Informar Custas", "Acompanhe pedidos, resultados e pagamentos.", "gerenciar_custas", "Rotinas"),
    ("regaux", "certidao", "Registro Auxiliar", "Consulte emitentes, produtos e safras nos textos.", "consultar_registro_auxiliar", "Consultas"),
    ("rotina", "certidao", "Rotina — Intimação", "Prazos, fases, documentos e conferências.", "ver_intimacoes", "Rotinas"),
    ("mapaonr", "rgi", "MAPA-ONR", "Converta os dados da matrícula para o padrão ONR.", "acessar_mapa_onr", "Produção"),
    ("poligonos", "rgi", "Polígonos", "Visualize e organize geometrias do imóvel.", "acessar_poligonos", "Consultas"),
    ("geradornotas", "rgi", "Gerador de Notas", "Elabore exigências com os modelos da serventia.", "acessar_gerador_notas", "Produção"),
    ("contratos", "rgi", "Contratos e Minutas", "Do GED à minuta para conferir e editar na Tri7.", "acessar_contratos", "Produção"),
    ("auditoria", "rgi", "Auditoria registral", "Revise pendências e resultados do analisador.", "revisar_auditoria", "Conferência"),
    ("integracoes", "sistema", "Integrações e agendamentos", "Ofício Eletrônico e verificações automáticas.", "configurar_sistema", "Sistema"),
    ("usuarios", "sistema", "Usuários e Acessos", "Perfis, permissões, senhas e sessões.", "gerenciar_usuarios", "Sistema"),
)


def modulos_permitidos(permissoes):
    return [dict(zip(("id", "setor", "nome", "descricao", "permissao", "grupo"), m))
            for m in MODULOS if permissoes.get(m[4])]
