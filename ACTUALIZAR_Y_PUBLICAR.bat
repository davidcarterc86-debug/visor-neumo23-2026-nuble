@echo off
chcp 65001 >nul
setlocal

cd /d "%~dp0"

echo ========================================
echo  ACTUALIZACION Y PUBLICACION DEL VISOR
echo  NEUMO23 2026 - ÑUBLE
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
    echo El proceso de actualizacion y publicacion necesita Python.
    echo Instalalo desde https://www.python.org/downloads/ y marca
    echo "Add python.exe to PATH" al instalar.
    echo.
    echo [ERROR] La actualizacion NO fue aplicada ni publicada.
    echo.
    pause
    exit /b 1
)

set "PYTHONIOENCODING=utf-8"
%PYCMD% "%~dp0ACTUALIZADOR\publicar_visor.py"
set "RC=%ERRORLEVEL%"

echo.
if "%RC%"=="0" (
    echo ========================================
    echo  Proceso completado correctamente.
    echo  Si hubo cambios, ya fueron publicados en GitHub Pages
    echo  ^(puede tardar 1-2 minutos en reflejarse^).
    echo  Si no hubo cambios, el visor ya estaba al dia.
    echo ========================================
) else if "%RC%"=="2" (
    echo ========================================
    echo  Los datos se actualizaron y se creo el COMMIT LOCAL,
    echo  pero el PUSH a GitHub fallo. Revise su conexion o
    echo  credenciales y reintente mas tarde con:
    echo      git push origin main
    echo ========================================
) else (
    echo ========================================
    echo  La actualizacion/publicacion NO se aplico. Revise los
    echo  mensajes [ERROR] de arriba para ver la causa exacta.
    echo  No se ejecuto ningun commit ni push. Los datos del
    echo  visor publicados anteriormente permanecen intactos.
    echo ========================================
)

echo.
pause
exit /b %RC%
