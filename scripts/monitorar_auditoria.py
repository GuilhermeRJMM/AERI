import argparse
import csv
import os
import sys
import time
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path


RAIZ = Path(__file__).resolve().parent.parent


def argumentos() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Exibe o progresso da auditoria Tri7 em tempo real.")
    parser.add_argument(
        "--arquivo",
        type=Path,
        default=RAIZ / "output" / "relatorios" / "auditoria_semantica_tri7-v2.csv",
    )
    parser.add_argument("--inicio", type=int, default=13_001)
    parser.add_argument("--fim", type=int, default=39_767)
    parser.add_argument("--intervalo", type=float, default=5.0)
    parser.add_argument("--uma-vez", action="store_true")
    return parser.parse_args()


def ler_ultimo_resultado(caminho: Path) -> dict[int, dict]:
    resultados: dict[int, dict] = {}
    if not caminho.exists():
        return resultados
    with caminho.open("r", encoding="utf-8-sig", newline="") as arquivo:
        for linha in csv.DictReader(arquivo):
            numero = str(linha.get("numero_matricula", "")).strip()
            if numero.isdigit():
                resultados[int(numero)] = linha
    return resultados


def duracao(segundos: float | None) -> str:
    if segundos is None or segundos < 0:
        return "calculando..."
    total = int(segundos)
    horas, resto = divmod(total, 3600)
    minutos, segundos = divmod(resto, 60)
    if horas:
        return f"{horas:02d}h {minutos:02d}min {segundos:02d}s"
    return f"{minutos:02d}min {segundos:02d}s"


def barra(percentual: float, largura: int = 44) -> str:
    preenchido = min(largura, max(0, round(largura * percentual / 100)))
    return "█" * preenchido + "░" * (largura - preenchido)


def limpar_tela() -> None:
    os.system("cls" if os.name == "nt" else "clear")


def main() -> int:
    args = argumentos()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if args.inicio < 1 or args.fim < args.inicio or args.intervalo < 1:
        raise SystemExit("Parâmetros inválidos.")

    total = args.fim - args.inicio + 1
    inicio_monitor = time.monotonic()
    contagem_anterior: int | None = None
    instante_anterior: float | None = None
    velocidade_media: float | None = None

    while True:
        agora = time.monotonic()
        resultados = ler_ultimo_resultado(args.arquivo)
        faixa = {
            numero: linha
            for numero, linha in resultados.items()
            if args.inicio <= numero <= args.fim
        }
        processadas = len(faixa)
        restantes = max(0, total - processadas)
        percentual = processadas / total * 100
        matricula_atual = max(faixa, default=args.inicio - 1)

        if contagem_anterior is not None and instante_anterior is not None:
            intervalo = max(agora - instante_anterior, 0.001)
            velocidade_instantanea = max(0.0, (processadas - contagem_anterior) / intervalo)
            if velocidade_instantanea > 0:
                velocidade_media = (
                    velocidade_instantanea
                    if velocidade_media is None
                    else velocidade_media * 0.65 + velocidade_instantanea * 0.35
                )

        eta_segundos = restantes / velocidade_media if velocidade_media else None
        termino = (
            datetime.now() + timedelta(seconds=eta_segundos)
            if eta_segundos is not None
            else None
        )
        status = Counter(str(linha.get("status", "")) for linha in faixa.values())
        erros = sum(valor for chave, valor in status.items() if chave.startswith("ERRO"))
        alertadas = sum(bool(str(linha.get("alertas", "")).strip()) for linha in faixa.values())
        idade_arquivo = time.time() - args.arquivo.stat().st_mtime if args.arquivo.exists() else float("inf")
        situacao = "CONCLUÍDA" if processadas >= total else ("EM EXECUÇÃO" if idade_arquivo < 30 else "SEM AVANÇO")

        limpar_tela()
        print("╔════════════════════════════════════════════════════════════╗")
        print("║              AERI · AUDITORIA DAS MATRÍCULAS              ║")
        print("╚════════════════════════════════════════════════════════════╝")
        print()
        print(f" Situação:          {situacao}")
        print(f" Matrícula atual:   {matricula_atual:,}".replace(",", "."))
        print(f" Faixa:             {args.inicio:,} → {args.fim:,}".replace(",", "."))
        print(f" Processadas:       {processadas:,} de {total:,}".replace(",", "."))
        print(f" Restantes:         {restantes:,}".replace(",", "."))
        print()
        print(f" [{barra(percentual)}] {percentual:6.2f}%")
        print()
        print(f" Velocidade real:   {velocidade_media:.2f} matrículas/s" if velocidade_media else " Velocidade real:   calculando...")
        print(f" Previsão restante: {duracao(eta_segundos)}")
        print(f" Término estimado:  {termino.strftime('%d/%m/%Y às %H:%M:%S') if termino else 'calculando...'}")
        print(f" Monitor aberto:    {duracao(agora - inicio_monitor)}")
        print()
        print(f" Alertadas:         {alertadas:,}".replace(",", "."))
        print(f" Falhas de API:     {erros:,}".replace(",", "."))
        print()
        print(" Atualização automática a cada 5 segundos. Feche esta janela para sair.")

        if args.uma_vez or processadas >= total:
            return 0
        contagem_anterior = processadas
        instante_anterior = agora
        time.sleep(args.intervalo)


if __name__ == "__main__":
    raise SystemExit(main())
