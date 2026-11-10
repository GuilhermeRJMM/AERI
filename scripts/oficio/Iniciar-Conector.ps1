param([switch]$Parear,[string]$Servidor,[switch]$UmaVez)
$ErrorActionPreference='Stop'
$Python=Join-Path $env:LOCALAPPDATA 'AnalisadorRGI-Lab\reverse-api-venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw 'Ambiente local não instalado. Siga docs/consulta-assistida-oficio.md.'
}
$Credencial=Join-Path $env:LOCALAPPDATA 'AnalisadorRGI-Lab\oficio-conector.dpapi'
if (-not (Test-Path -LiteralPath $Credencial -PathType Leaf)) { $Parear=$true }
$Argumentos=@('-u','-B','-X','utf8',(Join-Path $PSScriptRoot 'conector.py'))
if ($Parear) {
    Write-Host 'No Analisador: Intimações > Consultar Ofício Eletrônico > Conexão deste computador > Gerar código de conexão.'
    Write-Host 'O código é temporário. Cole somente quando o conector pedir; não envie no chat.'
    if (-not $Servidor) { $Servidor=Read-Host 'Endereço HTTPS completo do Analisador desta instalação' }
    $Argumentos+=@('--parear','--servidor',$Servidor)
}
if ($UmaVez) { $Argumentos+='--uma-vez' }
& $Python @Argumentos
if ($LASTEXITCODE -ne 0) { throw 'Conector encerrado sem concluir. Confira o pareamento e a autorização do Chrome.' }
