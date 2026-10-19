# Schedules scripts\brevo_relay.py with pythonw (no window): every hour from
# 08:00, and as soon as possible when the computer was off at that time.
# instalar.bat runs it; desinstalar.bat removes the task. The output goes to
# logs\brevo-relay.log.
# (ASCII only: Windows PowerShell 5.1 misreads UTF-8 files without a BOM.)

$ErrorActionPreference = "Stop"

$Name = "Boletin parroquial"
$Project = Split-Path -Parent $PSScriptRoot
$Pythonw = Join-Path $Project ".venv\Scripts\pythonw.exe"
$Script = Join-Path $Project "scripts\brevo_relay.py"

$Action = New-ScheduledTaskAction -Execute $Pythonw -Argument "`"$Script`"" -WorkingDirectory $Project
$Trigger = New-ScheduledTaskTrigger -Daily -At "08:00"
$Trigger.Repetition = (New-ScheduledTaskTrigger -Once -At "08:00" `
    -RepetitionInterval (New-TimeSpan -Hours 1) -RepetitionDuration (New-TimeSpan -Days 1)).Repetition
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RunOnlyIfNetworkAvailable `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
Register-ScheduledTask -TaskName $Name -Action $Action -Trigger $Trigger -Settings $Settings -Force `
    -Description "Parish newsletter: upload to Brevo the drafts GitHub could not (scripts\brevo_relay.py)." | Out-Null

Write-Host "Task '$Name' registered: every hour while the computer is on."
