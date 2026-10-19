# Registers the Windows scheduled task that runs scripts\run_daily.py.
# install.py runs it; to run it by hand, from the project folder:
#   powershell -ExecutionPolicy Bypass -File scripts\install_windows_task.ps1 [-At 10:00] [-EveryHours 0] [-NoLogon]
#   -At          time of the daily run
#   -EveryHours  repeat every N hours while the computer is on (0: once a day)
#   -NoLogon     don't also run it at logon
# Running it again replaces the task. To remove it:
#   Unregister-ScheduledTask -TaskName "Boletin parroquial"
# (ASCII only: Windows PowerShell 5.1 misreads UTF-8 files without a BOM.)

param(
    [string]$At = "10:00",
    [int]$EveryHours = 0,
    [switch]$NoLogon
)

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

# Every day at $At and, unless -NoLogon, at logon (a few minutes later, so the
# network is up). The script decides what each day needs.
$Triggers = @(New-ScheduledTaskTrigger -Daily -At $At)
if (-not $NoLogon) {
    $AtLogon = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
    $AtLogon.Delay = "PT5M"
    $Triggers += $AtLogon
}
if ($EveryHours -gt 0) {
    $Repeat = (New-ScheduledTaskTrigger -Once -At $At `
        -RepetitionInterval (New-TimeSpan -Hours $EveryHours) `
        -RepetitionDuration (New-TimeSpan -Days 1)).Repetition
    foreach ($Trigger in $Triggers) { $Trigger.Repetition = $Repeat }
}

$Settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1)

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Triggers `
    -Settings $Settings -Force `
    -Description "Parish newsletter: collect emails, reminders and the monthly Brevo draft (scripts\run_daily.py)." | Out-Null

$When = "daily at $At"
if ($EveryHours -gt 0) { $When += ", then every $EveryHours h" }
if (-not $NoLogon) { $When += ", and at logon" }
Write-Host "Task '$TaskName' registered: $When."
Write-Host "Log: $Project\logs\<YYYY-MM>.log"
