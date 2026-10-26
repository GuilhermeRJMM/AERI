from types import SimpleNamespace
from backend.app.rotas.autenticacao import sessao
from unittest.mock import patch


def test_contexto_publico_distingue_hub_sem_mudar_permissoes():
    for origem, esperado in [('HUB', 'HUB'), ('LOCAL', 'LOCAL'), (None, 'LOCAL')]:
        conta = {'usuario': 'SINTETICO', 'nome': 'Pessoa Teste', 'perfil': 'USUARIO',
                 'deve_trocar_senha': False, 'origem_autenticacao': origem}
        request = SimpleNamespace(state=SimpleNamespace(sessao=conta))
        with patch('backend.app.rotas.autenticacao.csrf_atual', return_value='sintetico'), \
             patch('backend.app.rotas.autenticacao.permissoes_sessao', return_value={'ver_intimacoes': False}):
            resultado = sessao(request, 'SINTETICO')
        assert resultado['origemAutenticacao'] == esperado
        assert resultado['permissoes'] == {'ver_intimacoes': False}
