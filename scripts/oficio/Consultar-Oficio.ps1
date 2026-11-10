param(
    [string]$Cartorio = $env:OFICIO_CARTORIO_ID,
    [int]$TotalEsperado = 0,
    [string]$Python = "$env:LOCALAPPDATA\AnalisadorRGI-Lab\reverse-api-venv\Scripts\python.exe"
)
$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw 'Conector local não instalado. Siga docs/consulta-assistida-oficio.md. Nada será instalado automaticamente.'
}
Write-Host 'Abra o Ofício Eletrônico e prepare a lista completa de Intimações, sem filtros de data ou situação.'
Write-Host 'Esta ferramenta não abre mensagens, não envia anexos e não muda pedidos.'
if (-not $Cartorio) { $Cartorio = Read-Host 'Identificador da sua serventia no Ofício' }
if ($TotalEsperado -le 0) { $TotalEsperado = [int](Read-Host 'Total histórico exibido na lista completa (não o total em tratativa)') }
$PastaSaida = Join-Path $env:USERPROFILE 'Downloads'
if (-not (Test-Path -LiteralPath $PastaSaida -PathType Container)) { throw 'Pasta Downloads não encontrada.' }
$Saida = Join-Path $PastaSaida ("consulta-oficio-" + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '.json')
& $Python -u -B -X utf8 (Join-Path $PSScriptRoot 'consultar.py') --cartorio $Cartorio --total-esperado $TotalEsperado --saida $Saida
if ($LASTEXITCODE -ne 0) { throw 'Consulta não concluída. Nenhuma importação foi realizada no Analisador.' }
