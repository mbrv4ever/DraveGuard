@echo off
rem Noodbouw 30-10-2026: dist\DraveGuard zat vast. Bouwt naar dist_bouw en kopieert de programmabestanden
rem daarna over de oude heen. De cache-map (handtekeningen, instellingen, quarantaine) wordt NIET aangeraakt.
cd /d "%~dp0"
set "PY=py -3.12"
%PY% -m PyInstaller --noconfirm --clean --windowed --onedir --distpath dist_bouw --workpath build_bouw ^
  --name DraveGuard ^
  --icon "assets\icon.ico" ^
  --collect-all PyQt6 ^
  --collect-all yara ^
  --collect-all psutil ^
  --hidden-import yara ^
  --hidden-import psutil ^
  --hidden-import send2trash ^
  --hidden-import winreg ^
  --hidden-import engine ^
  --hidden-import cleaner ^
  --hidden-import security ^
  --hidden-import sysmon ^
  --hidden-import startup ^
  --hidden-import watcher --hidden-import onderhoud --hidden-import onderhoud_ui --hidden-import telefoon --hidden-import telefoon_ui ^
  main.py
if not exist "dist_bouw\DraveGuard\DraveGuard.exe" ( echo BUILD MISLUKT & exit /b 1 )
robocopy "dist_bouw\DraveGuard" "dist\DraveGuard" /E /XD cache /NFL /NDL /NJH /NJS >nul
if not exist "dist\DraveGuard\assets" mkdir "dist\DraveGuard\assets"
copy /y "assets\*.*" "dist\DraveGuard\assets\" >nul 2>&1
if not exist "dist\DraveGuard\DraveGuard.exe" ( echo KOPIEREN MISLUKT & exit /b 1 )
echo KLAAR: dist\DraveGuard\DraveGuard.exe
