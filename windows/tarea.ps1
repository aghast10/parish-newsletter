# Registers the Windows fallback: a daily task and a Startup-folder shortcut,
# both running scripts\run_daily.py with pythonw (no window). instalar.bat
# runs it; desinstalar.bat undoes it. run_daily.py takes a lock, so the two
# never run at once.
# (ASCII only: Windows PowerShell 5.1 misreads UTF-8 files without a BOM.)

$ErrorActionPreference = "Stop"

$Name = "Boletin parroquial"
$Project = Split-Path -Parent $PSScriptRoot
$Pythonw = Join-Path $Project ".venv\Scripts\pythonw.exe"
$Script = Join-Path $Project "scripts\run_daily.py"

# Every day at 10:00, or as soon as possible after that if the computer was off.
$Action = New-ScheduledTaskAction -Execute $Pythonw -Argument "`"$Script`"" -WorkingDirectory $Project
$Trigger = New-ScheduledTaskTrigger -Daily -At "10:00"
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RunOnlyIfNetworkAvailable `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1)
Register-ScheduledTask -TaskName $Name -Action $Action -Trigger $Trigger -Settings $Settings -Force `
    -Description "Parish newsletter: scripts\run_daily.py" | Out-Null

# At logon, through the Startup folder (an at-logon task needs administrator
# rights). --wait gives the network two minutes to come up.
$Startup = [Environment]::GetFolderPath("Startup")
$Link = (New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $Startup "$Name.lnk"))
$Link.TargetPath = $Pythonw
$Link.Arguments = "`"$Script`" --wait 120"
$Link.WorkingDirectory = $Project
$Link.Save()

Write-Host "Task '$Name' registered (daily at 10:00) and Startup shortcut created."
