<#
.SYNOPSIS
    Instalador do Prisma para Windows - provisiona as dependencias e instala a skill.

.DESCRIPTION
    Uma linha, do zero ao Prisma pronto:

        irm https://raw.githubusercontent.com/wellington3105/Prisma/main/install.ps1 | iex

    O que este script faz que o `prisma_install.py` nao faz: INSTALA as
    dependencias. O instalador Python detecta o que falta e imprime o comando
    certo - o que e honesto, mas deixa tres `winget install` na mao do usuario.
    Aqui elas sao provisionadas antes, e so entao a skill e instalada.

    Nada exige privilegio de administrador: winget instala no escopo do usuario
    e a skill vai para o diretorio do agente em %USERPROFILE%.

.NOTES
    Rode no PowerShell. Para CMD, use install.cmd - ele chama este arquivo.
#>

$ErrorActionPreference = 'Stop'

function Write-Step($msg)  { Write-Host "  $msg" -ForegroundColor Cyan }
function Write-Ok($msg)    { Write-Host "  OK  $msg" -ForegroundColor Green }
function Write-Warn2($msg) { Write-Host "  !   $msg" -ForegroundColor Yellow }

Write-Host ""
Write-Host "PRISMA - instalacao" -ForegroundColor Magenta
Write-Host ""

# --- 1. winget -------------------------------------------------------------
# Presente no Windows 10 1809+ e no 11. Sem ele nao ha como provisionar nada
# sem pedir ao usuario que baixe instaladores a mao, entao falhamos cedo e
# com uma instrucao acionavel em vez de erros em cascata.
if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
    Write-Warn2 "winget nao encontrado."
    Write-Host  "      Instale o 'App Installer' pela Microsoft Store e rode de novo:"
    Write-Host  "      https://apps.microsoft.com/detail/9NBLGGH4NNS1"
    exit 1
}

# --- 2. dependencias -------------------------------------------------------
# `winget install` e idempotente: se o pacote ja esta la ele sai com um codigo
# proprio em vez de reinstalar. Por isso checamos o comando antes - e mais
# rapido e o log fica legivel.
$deps = @(
    @{ Cmd = 'uv';     Id = 'astral-sh.uv';        Nome = 'uv (Python + pacotes)' },
    @{ Cmd = 'ffmpeg'; Id = 'Gyan.FFmpeg';         Nome = 'ffmpeg (corte, cor, render)' },
    @{ Cmd = 'node';   Id = 'OpenJS.NodeJS.LTS';   Nome = 'Node.js (Remotion, Fase 2)' },
    @{ Cmd = 'git';    Id = 'Git.Git';             Nome = 'git (opcional, para desenvolver)' }
)

foreach ($d in $deps) {
    if (Get-Command $d.Cmd -ErrorAction SilentlyContinue) {
        Write-Ok "$($d.Nome) ja instalado"
        continue
    }
    Write-Step "instalando $($d.Nome)..."
    winget install --id $d.Id --silent --accept-package-agreements --accept-source-agreements --scope user 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0 -and $LASTEXITCODE -ne -1978335189) {
        Write-Warn2 "$($d.Nome) falhou (codigo $LASTEXITCODE) - siga sem ele e instale depois"
    } else {
        Write-Ok "$($d.Nome) instalado"
    }
}

# O PATH do processo atual nao enxerga o que o winget acabou de instalar: a
# variavel e lida na criacao do processo. Recarregar evita o erro classico de
# "instalei mas o comando nao existe" no passo seguinte.
$env:Path = [System.Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' +
            [System.Environment]::GetEnvironmentVariable('Path', 'User')

# --- 3. a skill ------------------------------------------------------------
# Delegado ao prisma_install.py, que ja resolve o dificil: descobre qual agente
# esta instalado (Claude Code, Codex, ...), baixa o tarball sem exigir git, e roda
# `uv sync`. Duplicar essa logica aqui criaria duas versoes para divergir.
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Warn2 "uv nao esta no PATH desta sessao."
    Write-Host  "      Feche e reabra o terminal, depois rode:"
    Write-Host  "      uv run https://raw.githubusercontent.com/wellington3105/Prisma/main/prisma_install.py"
    exit 1
}

Write-Host ""
Write-Step "instalando a skill Prisma..."
uv run https://raw.githubusercontent.com/wellington3105/Prisma/main/prisma_install.py @args
