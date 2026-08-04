"""Camada de domínio do analisador registral.

Os extratores históricos permanecem isolados nos módulos já validados. Esta
camada coordena os domínios e define o contrato público sem acoplar as regras
registrais às rotas HTTP ou à interface.
"""

from backend.app.analise.contrato import NOME_MOTOR, VERSAO_MOTOR

__all__ = ["NOME_MOTOR", "VERSAO_MOTOR"]
