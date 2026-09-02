#!/usr/bin/env bash
# K-CLI — One-Line Installer
# Usage: curl -sSL https://raw.githubusercontent.com/krishivjoshi219-collab/K-Cli/main/install.sh | bash

set -e

REPO="https://github.com/krishivjoshi219-collab/K-Cli-for-Devs.git"
INSTALL_DIR="$HOME/.k-cli"
BIN_DIR="$HOME/.local/bin"
PYTHON_MIN="3.11"

# ─── Colors ───────────────────────────────────────────────────────────────────
CYAN="\033[0;36m"; GREEN="\033[0;32m"; YELLOW="\033[1;33m"
RED="\033[0;31m"; BOLD="\033[1m"; RESET="\033[0m"

info()    { echo -e "${CYAN}[K-CLI]${RESET} $*"; }
success() { echo -e "${GREEN}[✔]${RESET} $*"; }
warn()    { echo -e "${YELLOW}[!]${RESET} $*"; }
die()     { echo -e "${RED}[✗]${RESET} $*" >&2; exit 1; }

# ─── Banner ───────────────────────────────────────────────────────────────────
echo -e "${CYAN}"
cat << 'EOF'
██╗  ██╗      ██████╗██╗     ██╗
██║ ██╔╝     ██╔════╝██║     ██║
█████╔╝      ██║     ██║     ██║
██╔═██╗      ██║     ██║     ██║
██║  ██╗     ╚██████╗███████╗██║
╚═╝  ╚═╝      ╚═════╝╚══════╝╚═╝

  Project Bankai — Agentic AI Workstation for Devs
EOF
echo -e "${RESET}"

info "Installing K-CLI..."

# ─── Check Python ─────────────────────────────────────────────────────────────
if command -v python3 &>/dev/null; then
    PY=$(python3 --version 2>&1 | grep -oP '\d+\.\d+' | head -1)
    PY_MAJOR=$(echo "$PY" | cut -d. -f1)
    PY_MINOR=$(echo "$PY" | cut -d. -f2)
    if [[ "$PY_MAJOR" -lt 3 || ("$PY_MAJOR" -eq 3 && "$PY_MINOR" -lt 11) ]]; then
        die "Python $PYTHON_MIN+ required (found $PY). Install from https://python.org"
    fi
    success "Python $PY found"
else
    die "Python 3 not found. Install from https://python.org"
fi

# ─── Clone or update ──────────────────────────────────────────────────────────
if [[ -d "$INSTALL_DIR/.git" ]]; then
    info "Updating existing installation at $INSTALL_DIR..."
    git -C "$INSTALL_DIR" pull --ff-only origin main || git -C "$INSTALL_DIR" fetch --all
else
    info "Cloning K-CLI to $INSTALL_DIR..."
    git clone --depth 1 "$REPO" "$INSTALL_DIR"
fi
success "Repository ready"

# ─── Virtual environment ──────────────────────────────────────────────────────
VENV="$INSTALL_DIR/.venv"
if [[ ! -d "$VENV" ]]; then
    info "Creating Python virtual environment..."
    python3 -m venv "$VENV"
fi
success "Virtual environment ready"

# ─── Install package ──────────────────────────────────────────────────────────
info "Installing K-CLI and dependencies..."
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet -e "$INSTALL_DIR"
success "K-CLI installed"

# ─── Shell wrapper ────────────────────────────────────────────────────────────
mkdir -p "$BIN_DIR"

cat > "$BIN_DIR/k" << WRAPPER
#!/usr/bin/env bash
exec "$VENV/bin/k-cli" "\$@"
WRAPPER
chmod +x "$BIN_DIR/k"

cat > "$BIN_DIR/k-cli" << WRAPPER
#!/usr/bin/env bash
exec "$VENV/bin/k-cli" "\$@"
WRAPPER
chmod +x "$BIN_DIR/k-cli"

success "Installed 'k' and 'k-cli' commands to $BIN_DIR"

# ─── PATH check ───────────────────────────────────────────────────────────────
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
    warn "Add $BIN_DIR to your PATH:"
    echo ""
    echo -e "  ${BOLD}echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.bashrc && source ~/.bashrc${RESET}"
    echo -e "  ${BOLD}# or for zsh:${RESET}"
    echo -e "  ${BOLD}echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.zshrc && source ~/.zshrc${RESET}"
    echo ""
fi

# ─── Optional: Ollama check ───────────────────────────────────────────────────
if command -v ollama &>/dev/null; then
    success "Ollama detected — local models available (no API key needed)!"
else
    warn "Ollama not found. Install from https://ollama.com to use local models for free."
fi

# ─── Done ─────────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}✔ K-CLI installed successfully!${RESET}"
echo ""
echo -e "  ${CYAN}k${RESET}              → launch the full-screen TUI workstation"
echo -e "  ${CYAN}k-cli codex${RESET}    → interactive setup (APIs, local models, DevDocs)"
echo -e "  ${CYAN}k-cli ui${RESET}       → TUI workstation"
echo -e "  ${CYAN}k \"fix my code\"${RESET} → inline agentic task"
echo ""
echo -e "  ${CYAN}Docs${RESET}: https://github.com/krishivjoshi219-collab/K-Cli-for-Devs"
echo ""
