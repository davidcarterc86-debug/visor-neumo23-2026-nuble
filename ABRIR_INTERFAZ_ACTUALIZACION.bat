@echo off
setlocal

cd /d "%~dp0"

set "PYCMD="
where pythonw >nul 2>nul
if not errorlevel 1 set "PYCMD=pythonw"
if not defined PYCMD (
    where python >nul 2>nul
    if not errorlevel 1 set "PYCMD=python"
)
if not defined PYCMD (
    where py >nul 2>nul
    if not errorlevel 1 set "PYCMD=py"
)

if not defined PYCMD (
    echo [ERROR] No se encontro Python instalado en este equipo.
    echo Instalalo desde https://www.python.org/downloads/ y marca
    echo "Add python.exe to PATH" al instalar.
    echo.
    pause
    exit /b 1
)

start "" %PYCMD% "%~dp0APP_ACTUALIZACION\actualizar_gui.py"
