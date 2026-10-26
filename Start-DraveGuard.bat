@echo off
rem === Start-DraveGuard.bat ===
cd /d "%~dp0"
chcp 65001 >nul

set "PY="
for %%V in (3.11 3.12 3.10 3.13) do (
  if not defined PY ( py -%%V -c "import sys" >nul 2>&1 && set "PY=py -%%V" )
)
if not defined PY ( py -3 -c "import sys" >nul 2>&1 && set "PY=py -3" )
if not defined PY ( python -c "import sys" >nul 2>&1 && set "PY=python" )
if not defined PY ( echo Geen Python gevonden. Installeer Python van python.org & pause & exit /b 1 )

rem --- benodigde pakketten (guarded) ---
%PY% -c "import PyQt6"       2>nul || %PY% -m pip install PyQt6
%PY% -c "import PIL"         2>nul || %PY% -m pip install pillow
%PY% -c "import send2trash"  2>nul || %PY% -m pip install send2trash
%PY% -c "import psutil"      2>nul || %PY% -m pip install psutil
rem yara-python is optioneel; zonder werkt de rest gewoon door
%PY% -c "import yara"        2>nul || %PY% -m pip install yara-python

rem --- icoon 1x bouwen ---
if not exist "assets\icon.ico" ( %PY% make_icon.py )

%PY% main.py
if errorlevel 1 pause
