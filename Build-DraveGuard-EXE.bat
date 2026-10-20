@echo off
rem === Build-DraveGuard-EXE.bat  ->  dist\DraveGuard\DraveGuard.exe ===
cd /d "%~dp0"
chcp 65001 >nul

set "PY="
for %%V in (3.11 3.12 3.10 3.13) do (
  if not defined PY ( py -%%V -c "import sys" >nul 2>&1 && set "PY=py -%%V" )
)
if not defined PY ( py -3 -c "import sys" >nul 2>&1 && set "PY=py -3" )
if not defined PY ( python -c "import sys" >nul 2>&1 && set "PY=python" )
if not defined PY ( echo Geen Python gevonden. & pause & exit /b 1 )

echo === Pakketten controleren ===
%PY% -c "import PyQt6"      2>nul || %PY% -m pip install PyQt6
%PY% -c "import PIL"        2>nul || %PY% -m pip install pillow
%PY% -c "import send2trash" 2>nul || %PY% -m pip install send2trash
%PY% -c "import psutil"     2>nul || %PY% -m pip install psutil
%PY% -c "import yara"       2>nul || %PY% -m pip install yara-python
%PY% -c "import PyInstaller" 2>nul || %PY% -m pip install pyinstaller

if not exist "assets\icon.ico" ( %PY% make_icon.py )

echo === Sluit een eventueel draaiende DraveGuard ===
taskkill /f /im DraveGuard.exe >nul 2>&1

echo === Bouwen (onedir, portable - geen Temp/AppData) ===
rem LET OP: yara en psutil hebben gecompileerde onderdelen (.pyd) - die moeten
rem expliciet mee, anders start de EXE wel maar valt de scanner/systeemwacht stil.
%PY% -m PyInstaller --noconfirm --clean --windowed --onedir ^
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
  --hidden-import watcher ^
  main.py

if not exist "dist\DraveGuard\DraveGuard.exe" (
  echo.
  echo BUILD MISLUKT - DraveGuard.exe niet gevonden.
  pause & exit /b 1
)

echo === Assets naast de exe kopieren ===
if not exist "dist\DraveGuard\assets" mkdir "dist\DraveGuard\assets"
copy /y "assets\*.*" "dist\DraveGuard\assets\" >nul 2>&1

echo.
echo KLAAR: dist\DraveGuard\DraveGuard.exe
echo (Draai eventueel als administrator om alle mappen te kunnen scannen.)
pause
