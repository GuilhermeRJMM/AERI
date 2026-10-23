# Instala o executor do AERI como Tarefa Agendada do Windows.
#
# Depois disto ninguem precisa abrir terminal: a tarefa sobe junto com a sessao
# e fica lendo a fila -- contrato digitalizado extraido no site e reconhecido
# por OCR aqui, sem intervencao.
#
#   powershell -ExecutionPolicy Bypass -File scripts\instalar_executor.ps1
#
# Depois de atualizar o codigo (git pull), reinicie -- Python importa os modulos
# uma vez, e um executor ja rodando segue com a versao velha:
#
#   powershell -ExecutionPolicy Bypass -File scripts\instalar_executor.ps1 -Reiniciar
#
# Para desinstalar:
#
#   powershell -ExecutionPolicy Bypass -File scripts\instalar_executor.ps1 -Remover
#
# Por padrão roda no logon. Em servidor sempre ligado, -AoIniciarSistema
# instala como SYSTEM no boot, sem guardar senha (exige PowerShell elevado).
# Nesse modo a conta SYSTEM precisa acessar a pasta, Python e .env. Unidades
# de rede mapeadas na sessão do usuário não existem na sessão de SYSTEM.
param(
  [switch]$Remover,
  [switch]$Reiniciar,
  [switch]$AoIniciarSistema,
  [string]$PythonExecutavel = '',
  [int]$Intervalo = 15
)

$ErrorActionPreference = "Stop"
$Nome = "AERI Executor"
$Raiz = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Script = Join-Path $Raiz "scripts\worker_operacional.py"
$Log = Join-Path $Raiz ".tmp\executor.log"

# Python carrega os modulos uma vez, no inicio: um executor ja rodando segue
# com o codigo velho depois de um git pull. Foi assim que uma correcao para nao
# abrir console ficou 24 minutos sem efeito, com o processo antigo abrindo
# janelas o tempo todo. Reinicie sempre que atualizar o codigo.
if ($Reiniciar) {
  Stop-ScheduledTask -TaskName $Nome -ErrorAction SilentlyContinue
  Start-Sleep -Seconds 2
  Start-ScheduledTask -TaskName $Nome
  Start-Sleep -Seconds 3
  Write-Host "Reiniciado. Estado: $((Get-ScheduledTask -TaskName $Nome).State)"
  return
}

if ($Remover) {
  if (Get-ScheduledTask -TaskName $Nome -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $Nome -Confirm:$false
    Write-Host "Tarefa '$Nome' removida."
  } else {
    Write-Host "Tarefa '$Nome' nao estava instalada."
  }
  return
}

# Quem diz onde o Python esta e o proprio Python: no PATH do usuario, "python"
# costuma resolver para o stub da Microsoft Store em WindowsApps, que abre a
# Loja em vez de executar. A tarefa ficaria instalada e nunca rodaria.
$Python = $null
if ($PythonExecutavel -and -not (Test-Path -LiteralPath $PythonExecutavel)) {
  throw 'O Python informado nao existe.'
}
$candidatos = @($PythonExecutavel, (Join-Path $Raiz '.venv\Scripts\python.exe'), 'python', 'py')
foreach ($candidato in $candidatos) {
  if (-not $candidato) { continue }
  try {
    $saida = & $candidato -c "import sys; print(sys.executable)" 2>$null
    if ($LASTEXITCODE -eq 0 -and $saida -and (Test-Path $saida) -and
        $saida -notlike "*\WindowsApps\*") { $Python = $saida; break }
  } catch { }
}
if (-not $Python) {
  throw 'nao encontrei um Python utilizavel fora do stub da Microsoft Store. Instale o Python de python.org ou ajuste o PATH.'
}
# pythonw nao abre janela de console; sem ele a tarefa pisca um terminal preto
# a cada logon.
$Pythonw = Join-Path (Split-Path -Parent $Python) "pythonw.exe"
if (-not (Test-Path $Pythonw)) { $Pythonw = $Python }

if (-not (Test-Path $Script)) { throw "nao achei $Script" }
if (-not (Test-Path (Join-Path $Raiz ".env"))) {
  throw "nao achei o .env na raiz. Configure POSTGRES_URL e a chave dos contratos antes de instalar."
}

New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Log) | Out-Null

Write-Host "Instalando '$Nome'"
Write-Host "   python   : $Pythonw"
Write-Host "   script   : $Script"
Write-Host "   intervalo: ${Intervalo}s"
Write-Host "   log      : $Log"

$acao = New-ScheduledTaskAction -Execute $Pythonw `
  -Argument "`"$Script`" --intervalo $Intervalo" -WorkingDirectory $Raiz
$gatilho = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$principal = $null
if ($AoIniciarSistema) {
  $identidade = [Security.Principal.WindowsIdentity]::GetCurrent()
  $administrador = [Security.Principal.WindowsPrincipal]::new($identidade)
  if (-not $administrador.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw '-AoIniciarSistema exige PowerShell como administrador no servidor.'
  }
  $gatilho = New-ScheduledTaskTrigger -AtStartup
  $principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
}
# Um executor so: IgnoreNew descarta um segundo disparo enquanto o primeiro
# roda -- o que acontece ao bloquear e desbloquear a sessao. O lease do banco ja
# protege contra processamento duplo, mas duas copias so gastam CPU a toa.
$config = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries `
  -DontStopIfGoingOnBatteries -StartWhenAvailable `
  -MultipleInstances IgnoreNew -RestartInterval (New-TimeSpan -Minutes 1) -RestartCount 999
$config.ExecutionTimeLimit = "PT0S"   # sem limite: e um laco continuo

$parametros = @{
  TaskName = $Nome; Action = $acao; Trigger = $gatilho; Settings = $config
  Description = 'Sincroniza matrículas e registros auxiliares continuamente, acompanha o Livro e processa documentos.'
  Force = $true
}
if ($principal) { $parametros.Principal = $principal }
Register-ScheduledTask @parametros | Out-Null

Start-ScheduledTask -TaskName $Nome
Start-Sleep -Seconds 3
$estado = (Get-ScheduledTask -TaskName $Nome).State
Write-Host ""
Write-Host "Instalada e iniciada. Estado: $estado"
Write-Host ""
Write-Host "Conferir se esta rodando:"
Write-Host "   Get-ScheduledTask -TaskName '$Nome'"
Write-Host "Parar por um tempo:"
Write-Host "   Stop-ScheduledTask -TaskName '$Nome'"
Write-Host "Desinstalar:"
Write-Host "   powershell -ExecutionPolicy Bypass -File scripts\instalar_executor.ps1 -Remover"
