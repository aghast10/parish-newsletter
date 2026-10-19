# Registers the Windows scheduled task that runs scripts\run_daily.py.
# Run it once, from the project folder, in PowerShell:
#   powershell -ExecutionPolicy Bypass -File scripts\install_windows_task.ps1
# Running it again replaces the task. To remove it:
#   Unregister-ScheduledTask -TaskName "Boletin parroquial"
# (ASCII only: Windows PowerShell 5.1 misreads UTF-8 files without a BOM.)

$ErrorActionPreference = "Stop"

$TaskName = "Boletin parroquial"
$Project = Split-Path -Parent $PSScriptRoot
# pythonw: no console window pops up; the output goes to logs\YYYY-MM.log.
$Pythonw = Join-Path $Project ".venv\Scripts\pythonw.exe"
$Script = Join-Path $Project "scripts\run_daily.py"

if (-not (Test-Path $Pythonw)) {
    throw "$Pythonw not found. Create the venv first: py -m venv .venv; .venv\Scripts\pip install -r requirements.txt"
}

$Action = New-ScheduledTaskAction -Execute $Pythonw -Argument "`"$Script`"" -WorkingDirectory $Project

# At logon (a few minutes later, so the network is up) and every day at 10:00
# in case the computer stays on. The script decides what each day needs.
$AtLogon = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
$AtLogon.Delay = "PT5M"
$Daily = New-ScheduledTaskTrigger -Daily -At "10:00"

$Settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1)

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $AtLogon, $Daily `
    -Settings $Settings -Force `
    -Description "Parish newsletter: collect emails, reminders and the monthly Brevo draft (scripts\run_daily.py)." | Out-Null

Write-Host "Task '$TaskName' registered. It runs at logon and daily at 10:00."
Write-Host "Log: $Project\logs\<YYYY-MM>.log"
