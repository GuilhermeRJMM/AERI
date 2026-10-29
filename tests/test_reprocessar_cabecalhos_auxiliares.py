from scripts.reprocessar_cabecalhos_auxiliares import carregar_executor


def test_carrega_apenas_credenciais_previstas_sem_imitar_vercel(tmp_path, monkeypatch):
    for chave in ('POSTGRES_URL','AERI_HASH_REMOTO_TOKEN','VERCEL','CHAVE_ALHEIA'):
        monkeypatch.delenv(chave, raising=False)
    (tmp_path / '.env').write_text('POSTGRES_URL=conexao-sintetica\nVERCEL=1\nCHAVE_ALHEIA=ignorar\n',encoding='utf-8')
    (tmp_path / '.env.buscas.local').write_text('AERI_HASH_REMOTO_TOKEN=token-sintetico\n',encoding='utf-8')
    carregar_executor(tmp_path)
    import os
    assert os.environ['POSTGRES_URL'] == 'conexao-sintetica'
    assert os.environ['AERI_HASH_REMOTO_TOKEN'] == 'token-sintetico'
    assert 'VERCEL' not in os.environ and 'CHAVE_ALHEIA' not in os.environ
    monkeypatch.delenv('POSTGRES_URL')
    monkeypatch.delenv('AERI_HASH_REMOTO_TOKEN')


def test_nao_substitui_configuracao_existente_nem_aceita_marcador_sensivel(tmp_path, monkeypatch):
    monkeypatch.setenv('POSTGRES_URL','conexao-ja-configurada')
    monkeypatch.delenv('AERI_HASH_REMOTO_TOKEN',raising=False)
    (tmp_path / '.env').write_text('POSTGRES_URL=outra-conexao\nAERI_HASH_REMOTO_TOKEN=[SENSITIVE]\n',encoding='utf-8')
    carregar_executor(tmp_path)
    import os
    assert os.environ['POSTGRES_URL'] == 'conexao-ja-configurada'
    assert 'AERI_HASH_REMOTO_TOKEN' not in os.environ
