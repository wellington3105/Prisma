@echo off
REM Instalador do Prisma para CMD (Prompt de Comando).
REM
REM Uma linha, do zero ao Prisma pronto:
REM
REM   curl -sSL https://raw.githubusercontent.com/wellington3105/Prisma/main/install.cmd -o %TEMP%\prisma.cmd && %TEMP%\prisma.cmd
REM
REM O CMD nao executa .ps1 e nao tem um equivalente ao `irm | iex`, entao este
REM arquivo existe so para levar a execucao ao PowerShell - onde a instalacao
REM de fato acontece. Manter a logica em UM lugar evita que as duas versoes
REM divirjam com o tempo.
REM
REM -ExecutionPolicy Bypass vale so para este processo: nao altera a politica
REM da maquina, e e o que permite rodar o script sem pedir privilegio.

setlocal
echo.
echo PRISMA - instalacao (via PowerShell)
echo.

where powershell >nul 2>&1
if errorlevel 1 (
    echo   !   PowerShell nao encontrado neste sistema.
    echo       O Prisma precisa dele para instalar as dependencias.
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "irm https://raw.githubusercontent.com/wellington3105/Prisma/main/install.ps1 | iex"

endlocal
