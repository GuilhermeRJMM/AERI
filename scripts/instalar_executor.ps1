# Instala o executor do AERI como Tarefa Agendada do Windows.
#
# Depois disto ninguem precisa abrir terminal: a tarefa sobe junto com a sessao
# e fica lendo a fila -- contrato digitalizado extraido no site e reconhecido
# por OCR aqui, sem intervencao.
#
#   powershell -ExecutionPolicy Bypass -File scripts\instalar_executor.ps1
#
# Para desinstalar:
#
#   powershell -ExecutionPolicy Bypass -File scripts\instalar_executor.ps1 -Remover
#
# Nao pede senha nem privilegio de administrador: a tarefa roda no logon do
# usuario atual, que e quando a maquina da serventia esta em uso. Rodar como
# servico do sistema exigiria guardar a senha da conta, e nao vale a troca.
param(
  [switch]$Remover,
  [int]$Intervalo = 15
)

$ErrorActionPreference = "Stop"
$Nome = "AERI Executor"
$Raiz = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Script = Join-Path $Raiz "scripts\worker_operacional.py"
$Log = Join-Path $Raiz ".tmp\executor.log"

if ($Remover) {
  if (Get-ScheduledTask -TaskName $Nome -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $Nome -Confirm:$false
    Write-Host "Tarefa '$Nome' removida."
  } else {
    Write-Host "Tarefa '$Nome' nao estava instalada."
  }
  return
}

# pythonw nao abre janela de console; sem ele a tarefa pisca um terminal preto
# a cada logon.
$Python = (Get-Command python -ErrorAction Stop).Source
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
# Um executor so: StopExisting evita duas copias disputando a mesma fila depois
# de bloquear e desbloquear a sessao. O lease do banco ja protege contra
# processamento duplo, mas duas copias so gastam CPU a toa.
$config = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries `
  -DontStopIfGoingOnBatteries -StartWhenAvailable `
  -MultipleInstances StopExisting -RestartInterval (New-TimeSpan -Minutes 1) -RestartCount 3
$config.ExecutionTimeLimit = "PT0S"   # sem limite: e um laco continuo

Register-ScheduledTask -TaskName $Nome -Action $acao -Trigger $gatilho `
  -Settings $config -Description "Le a fila do AERI e faz OCR de contratos digitalizados nesta maquina." `
  -Force | Out-Null

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
