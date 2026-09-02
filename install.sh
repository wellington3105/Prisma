#!/usr/bin/env sh
# Instalador do Prisma para macOS e Linux.
#
# Uma linha, do zero ao Prisma pronto:
#
#   curl -fsSL https://raw.githubusercontent.com/wellington3105/Prisma/main/install.sh | sh
#
# O que este script faz que o `prisma_install.py` nao faz: INSTALA as
# dependencias. O instalador Python detecta o que falta e imprime o comando
# certo - honesto, mas deixa tres `brew install` na mao do usuario.
#
# POSIX sh, nao bash: em macOS antigo /bin/sh nao e bash, e um `[[ ]]` perdido
# quebra a instalacao logo na primeira linha, antes de qualquer diagnostico.
set -eu

C_CYAN='\033[36m'; C_GREEN='\033[32m'; C_YELLOW='\033[33m'; C_MAG='\033[35m'; C_OFF='\033[0m'
step() { printf "  ${C_CYAN}%s${C_OFF}\n" "$1"; }
ok()   { printf "  ${C_GREEN}OK  %s${C_OFF}\n" "$1"; }
warn() { printf "  ${C_YELLOW}!   %s${C_OFF}\n" "$1"; }

printf "\n${C_MAG}PRISMA - instalacao${C_OFF}\n\n"

OS="$(uname -s)"

# --- gerenciador de pacotes ------------------------------------------------
# Descoberto uma vez e reutilizado: em macOS e o Homebrew; em Linux depende da
# distro. Sem gerenciador conhecido seguimos assim mesmo - o `uv` tem instalador
# proprio e o resto vira aviso acionavel no fim.
PKG=""
if [ "$OS" = "Darwin" ]; then
    if command -v brew >/dev/null 2>&1; then
        PKG="brew"
    else
        warn "Homebrew nao encontrado - necessario para ffmpeg e node no macOS."
        printf "      Instale com:\n"
        printf '      /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"\n'
        printf "      Depois rode este instalador de novo.\n\n"
    fi
elif command -v apt-get >/dev/null 2>&1; then PKG="apt"
elif command -v dnf     >/dev/null 2>&1; then PKG="dnf"
elif command -v pacman  >/dev/null 2>&1; then PKG="pacman"
fi

instalar() {
    # $1 = comando, $2 = pacote, $3 = rotulo
    if command -v "$1" >/dev/null 2>&1; then ok "$3 ja instalado"; return 0; fi
    step "instalando $3..."
    case "$PKG" in
        brew)   brew install "$2" >/dev/null 2>&1 || warn "$3 falhou - instale com: brew install $2" ;;
        apt)    sudo apt-get install -y "$2" >/dev/null 2>&1 || warn "$3 falhou - instale com: sudo apt-get install $2" ;;
        dnf)    sudo dnf install -y "$2" >/dev/null 2>&1 || warn "$3 falhou - instale com: sudo dnf install $2" ;;
        pacman) sudo pacman -S --noconfirm "$2" >/dev/null 2>&1 || warn "$3 falhou - instale com: sudo pacman -S $2" ;;
        *)      warn "$3 ausente e sem gerenciador de pacotes conhecido - instale manualmente"; return 0 ;;
    esac
    command -v "$1" >/dev/null 2>&1 && ok "$3 instalado"
}

# --- uv --------------------------------------------------------------------
# Vem primeiro e por caminho proprio: o instalador oficial dispensa gerenciador
# de pacotes, e sem uv nada do resto acontece. Ele tambem traz o Python certo,
# por isso o Python nao aparece nesta lista.
if command -v uv >/dev/null 2>&1; then
    ok "uv (Python + pacotes) ja instalado"
else
    step "instalando uv (Python + pacotes)..."
    curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null 2>&1 || warn "uv falhou"
    # O instalador do uv escreve em ~/.local/bin, que so entra no PATH no
    # proximo shell. Adicionamos agora para o passo final funcionar de primeira.
    [ -d "$HOME/.local/bin" ] && PATH="$HOME/.local/bin:$PATH" && export PATH
    [ -d "$HOME/.cargo/bin" ] && PATH="$HOME/.cargo/bin:$PATH" && export PATH
    command -v uv >/dev/null 2>&1 && ok "uv instalado"
fi

# --- ffmpeg e node ---------------------------------------------------------
instalar ffmpeg ffmpeg "ffmpeg (corte, cor, render)"

# O nome do pacote do Node muda por distro; em apt ainda vem sem o npm.
case "$PKG" in
    brew)   instalar node nodejs   "Node.js (Remotion, Fase 2)" 2>/dev/null || instalar node node "Node.js (Remotion, Fase 2)" ;;
    apt)    if ! command -v node >/dev/null 2>&1; then
                step "instalando Node.js (Remotion, Fase 2)..."
                sudo apt-get install -y nodejs npm >/dev/null 2>&1 || warn "Node falhou - instale com: sudo apt-get install nodejs npm"
                command -v node >/dev/null 2>&1 && ok "Node.js instalado"
            else ok "Node.js (Remotion, Fase 2) ja instalado"; fi ;;
    *)      instalar node nodejs "Node.js (Remotion, Fase 2)" ;;
esac

# --- a skill ---------------------------------------------------------------
# Delegado ao prisma_install.py, que ja resolve o dificil: descobre qual agente
# esta instalado, baixa sem exigir git, e roda `uv sync`.
if ! command -v uv >/dev/null 2>&1; then
    warn "uv nao esta no PATH desta sessao."
    printf "      Abra um terminal novo e rode:\n"
    printf "      uv run https://raw.githubusercontent.com/wellington3105/Prisma/main/prisma_install.py\n"
    exit 1
fi

printf "\n"
step "instalando a skill Prisma..."
uv run https://raw.githubusercontent.com/wellington3105/Prisma/main/prisma_install.py "$@"
