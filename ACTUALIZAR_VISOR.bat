@echo off
chcp 65001 >nul
setlocal

cd /d "%~dp0"

echo ========================================
echo  ACTUALIZACION VISOR NEUMO23 2026
echo ========================================
echo.

REM --- Detectar interprete de Python disponible (python o py) ---
set "PYCMD="
where python >nul 2>nul
if not errorlevel 1 set "PYCMD=python"
if not defined PYCMD (
    where py >nul 2>nul
    if not errorlevel 1 set "PYCMD=py"
)

if not defined PYCMD (
    echo [ERROR] No se encontro Python instalado en este equipo.
    echo El proceso de actualizacion necesita Python para leer la base RNI.
    echo Instalalo desde https://www.python.org/downloads/ y marca
    echo "Add python.exe to PATH" al instalar.
    echo.
    echo [ERROR] La actualizacion NO fue aplicada.
    echo Los datos anteriores del visor se mantienen intactos.
    echo.
    pause
    exit /b 1
)

set "PYTHONIOENCODING=utf-8"
%PYCMD% "%~dp0ACTUALIZADOR\actualizar_visor.py"
set "RC=%ERRORLEVEL%"

echo.
if "%RC%"=="0" (
    echo ========================================
    echo  Actualizacion completada correctamente.
    echo  El visor ya puede consultarse con los datos nuevos.
    echo ========================================
) else (
    echo ========================================
    echo  La actualizacion NO se aplico. Revise los
    echo  mensajes [ERROR] de arriba para ver la causa.
    echo  El visor sigue mostrando los datos anteriores.
    echo ========================================
)

echo.
pause
exit /b %RC%
