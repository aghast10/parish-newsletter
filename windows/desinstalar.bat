@echo off
rem Removes the daily task and the Startup shortcut. Leaves the folder (and data\) alone.
schtasks /delete /tn "Boletin parroquial" /f
del "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Boletin parroquial.lnk" 2>nul
echo Quitado. Ya no se ejecuta solo en este ordenador.
pause
