@echo off
rem Removes the scheduled task. Leaves the folder alone.
schtasks /delete /tn "Boletin parroquial" /f
echo Quitado. Este ordenador ya no sube nada a Brevo.
pause
