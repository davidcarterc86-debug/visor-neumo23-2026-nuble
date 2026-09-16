@echo off
setlocal enabledelayedexpansion

set "PORT=8731"
set "URL=http://localhost:%PORT%/index.html"

REM ------------------------------------------------------------------
REM Modo interno: esta misma ventana se vuelve a invocar a si misma con
REM el parametro ABRIRNAVEGADOR para abrir el navegador un instante
REM despues de arrancar el servidor, sin bloquear el arranque de este.
REM ------------------------------------------------------------------
if "%~1"=="ABRIRNAVEGADOR" goto ABRIRNAVEGADOR

title Visor Neumo23 2026 - Nuble (servidor local)
cd /d "%~dp0"

REM --- Detectar interprete de Python disponible (python o py) ---
set "PYCMD="
where python >nul 2>nul
if not errorlevel 1 set "PYCMD=python"
if not defined PYCMD (
    where py >nul 2>nul
    if not errorlevel 1 set "PYCMD=py"
)

if not defined PYCMD (
    echo.
    echo ============================================================
    echo   ERROR: no se encontro Python instalado en este equipo.
    echo   El visor necesita Python para levantar el servidor local
    echo   ^(no incluye datos ni logica; solo sirve los archivos^).
    echo.
    echo   Instala Python desde https://www.python.org/downloads/
    echo   y marca la casilla "Add python.exe to PATH" al instalar.
    echo ============================================================
    echo.
    pause
    exit /b 1
)

REM --- Verificar si el puerto 8731 ya esta en uso (servidor ya activo) ---
set "PUERTO_OCUPADO="
for /f "tokens=*" %%L in ('netstat -ano ^| findstr /C:":%PORT% " ^| findstr "LISTENING"') do (
    set "PUERTO_OCUPADO=1"
)

if defined PUERTO_OCUPADO (
    echo El servidor local del visor ya estaba activo en el puerto %PORT%.
    echo Abriendo el visor en el navegador...
    start "" "%URL%"
    exit /b 0
)

echo ============================================================
echo   Visor Neumo23 2026 - Nuble
echo   Iniciando servidor local en el puerto %PORT% ...
echo   Carpeta: %cd%
echo.
echo   NO CIERRES esta ventana mientras uses el visor.
echo   Para salir: cierra esta ventana o presiona Ctrl+C.
echo ============================================================
echo.

REM Abrir el navegador un par de segundos despues, en una ventana aparte
REM y minimizada, sin bloquear el arranque del servidor de abajo.
start "" /min "%~f0" ABRIRNAVEGADOR

REM Levantar el servidor HTTP local (queda corriendo en esta ventana)
%PYCMD% -m http.server %PORT%

echo.
echo El servidor se detuvo.
pause
exit /b 0

:ABRIRNAVEGADOR
timeout /t 2 /nobreak >nul
start "" "%URL%"
exit /b 0
