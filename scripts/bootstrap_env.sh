#!/usr/bin/env bash
# ==============================================================================
# scripts/bootstrap_env.sh - Environment & Knowledge Ingestion Provisioner
#
# Principal ML & Systems DevOps provisioning script for Project Bankai (K-CLI):
# 1. Scaffolds ~/.kcli directory hierarchy (docs, repos, logs, khoj_index, parsers).
# 2. Idempotently checks/installs system packages (universal-ctags, sqlite3).
# 3. Ensures target Python toolchain in k_cli_env.
# 4. Creates and validates tree-sitter AST parsers (~/.kcli/parsers/test_ast.py).
# 5. Generates Khoj offline indexing configuration (~/.kcli/khoj_index/khoj.json).
# 6. Executes DevDocs Ingestion Engine (scripts/setup_knowledge.py) to populate ~/.kcli/docs.db.
# ==============================================================================

set -euo pipefail

# Visual styling
RED='[0;31m'
GREEN='[0;32m'
YELLOW='[1;33m'
CYAN='[0;36m'
MAGENTA='[0;35m'
BOLD='[1m'
NC='[0m' # No Color

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
KCLI_HOME="${HOME}/.kcli"
VENV_DIR="${ROOT_DIR}/k_cli_env"

echo -e "${BOLD}${CYAN}======================================================================${NC}"
echo -e "${BOLD}${CYAN}⚡ PROJECT BANKAI: Local Environment & Knowledge Ingestion Engine${NC}"
echo -e "${BOLD}${CYAN}======================================================================${NC}"
echo -e "${CYAN}• K-CLI Home:${NC}      ${KCLI_HOME}"
echo -e "${CYAN}• Python Virtualenv:${NC} ${VENV_DIR}"
echo ""

# ------------------------------------------------------------------------------
# 1. Directory Hierarchy Scaffolding
# ------------------------------------------------------------------------------
echo -e "${BOLD}${MAGENTA}📁 [1/5] Scaffolding ~/.kcli directory hierarchy...${NC}"
mkdir -p "${KCLI_HOME}/docs"
mkdir -p "${KCLI_HOME}/repos"
mkdir -p "${KCLI_HOME}/logs"
mkdir -p "${KCLI_HOME}/khoj_index"
mkdir -p "${KCLI_HOME}/parsers"

echo -e "${GREEN}✔ Created:${NC}"
echo -e "  • ${KCLI_HOME}/docs/       (Offline documentation store)"
echo -e "  • ${KCLI_HOME}/repos/      (Local cloned repositories for indexing)"
echo -e "  • ${KCLI_HOME}/logs/       (Agent session and compiler logs)"
echo -e "  • ${KCLI_HOME}/khoj_index/ (Khoj neural search configurations)"
echo -e "  • ${KCLI_HOME}/parsers/    (Tree-Sitter grammars and AST test harness)"

# ------------------------------------------------------------------------------
# 2. System Packages Verification (universal-ctags, sqlite3)
# ------------------------------------------------------------------------------
echo -e "
${BOLD}${MAGENTA}📦 [2/5] Checking system packages (universal-ctags, sqlite3)...${NC}"

PACKAGES_TO_INSTALL=()
if ! command -v ctags &>/dev/null; then
    PACKAGES_TO_INSTALL+=("universal-ctags")
fi
if ! command -v sqlite3 &>/dev/null; then
    PACKAGES_TO_INSTALL+=("sqlite3")
fi

if [ ${#PACKAGES_TO_INSTALL[@]} -gt 0 ]; then
    echo -e "${YELLOW}Missing system binaries: ${PACKAGES_TO_INSTALL[*]}${NC}"
    if [ "${EUID:-1000}" -eq 0 ]; then
        apt-get update && apt-get install -y "${PACKAGES_TO_INSTALL[@]}"
        echo -e "${GREEN}✔ Installed ${PACKAGES_TO_INSTALL[*]} via apt-get.${NC}"
    elif command -v sudo &>/dev/null && sudo -n true 2>/dev/null; then
        sudo apt-get update && sudo apt-get install -y "${PACKAGES_TO_INSTALL[@]}"
        echo -e "${GREEN}✔ Installed ${PACKAGES_TO_INSTALL[*]} via sudo apt-get.${NC}"
    else
        echo -e "${YELLOW}ℹ Note: Running as non-root without passwordless sudo. Using userland / Python toolchain alternatives.${NC}"
    fi
else
    echo -e "${GREEN}✔ All system binaries (ctags, sqlite3) already present in PATH.${NC}"
fi

# ------------------------------------------------------------------------------
# 3. Python Toolchain Verification & Installation
# ------------------------------------------------------------------------------
echo -e "
${BOLD}${MAGENTA}🐍 [3/5] Verifying Python toolchain in k_cli_env...${NC}"

if [ -f "${VENV_DIR}/bin/activate" ]; then
    PYTHON_EXEC="${VENV_DIR}/bin/python3"
    PIP_EXEC="${VENV_DIR}/bin/pip"
else
    PYTHON_EXEC="$(command -v python3)"
    PIP_EXEC="$(command -v pip3 || command -v pip)"
fi

echo -e "Using Python: ${BOLD}${PYTHON_EXEC}${NC}"

REQUIRED_PACKAGES=(
    "sqlite-utils"
    "beautifulsoup4"
    "requests"
    "rich"
    "tree-sitter"
    "tree-sitter-python"
    "tree-sitter-cpp"
)

echo -e "Ensuring core libraries are installed..."
${PIP_EXEC} install -q --upgrade "${REQUIRED_PACKAGES[@]}"

echo -e "${GREEN}✔ Python toolchain packages verified.${NC}"

# ------------------------------------------------------------------------------
# 4. Tree-Sitter Parser Validation Harness & Khoj Config
# ------------------------------------------------------------------------------
echo -e "
${BOLD}${MAGENTA}🌳 [4/5] Building & verifying Tree-Sitter AST parsers...${NC}"

cat << 'EOF_HARNESS' > "${KCLI_HOME}/parsers/test_ast.py"
#!/usr/bin/env python3
import sys

def test_python():
    import tree_sitter_python as tspython
    from tree_sitter import Language, Parser
    
    py_lang = Language(tspython.language())
    try:
        parser = Parser(py_lang)
    except TypeError:
        parser = Parser()
        parser.language = py_lang
        
    code = b"""def binary_search(arr: list[int], target: int) -> int:
    return bisect_left(arr, target)
"""
    tree = parser.parse(code)
    root = tree.root_node
    assert root.type == "module", f"Expected module, got {root.type}"
    assert len(root.children) > 0, "AST has no child nodes"
    print(f"  • Python AST:   {root.type} -> {root.children[0].type} (Nodes: {len(root.children)})")

def test_cpp():
    import tree_sitter_cpp as tscpp
    from tree_sitter import Language, Parser
    
    cpp_lang = Language(tscpp.language())
    try:
        parser = Parser(cpp_lang)
    except TypeError:
        parser = Parser()
        parser.language = cpp_lang
        
    code = b"""#include <vector>
int main() {
    std::vector<int> data = {1, 2, 3};
    return 0;
}
"""
    tree = parser.parse(code)
    root = tree.root_node
    assert root.type == "translation_unit", f"Expected translation_unit, got {root.type}"
    assert len(root.children) > 0, "AST has no child nodes"
    print(f"  • C++ AST:      {root.type} -> {root.children[0].type} (Nodes: {len(root.children)})")

if __name__ == "__main__":
    test_python()
    test_cpp()
    print("✔ All Tree-Sitter AST grammars validated successfully.")
EOF_HARNESS

chmod +x "${KCLI_HOME}/parsers/test_ast.py"
${PYTHON_EXEC} "${KCLI_HOME}/parsers/test_ast.py"

# Initialize Khoj Index Config
cat << 'EOF_KHOJ' > "${KCLI_HOME}/khoj_index/khoj.json"
{
  "version": "1.0",
  "app": {
    "name": "Project Bankai Knowledge Index",
    "description": "Local codebase and DevDocs offline retrieval index for K-CLI"
  },
  "content_type": {
    "docs": {
      "input_files": ["~/.kcli/docs"],
      "file_type": ["md", "txt", "rst", "pdf", "org"],
      "enabled": true
    },
    "repos": {
      "input_files": ["~/.kcli/repos"],
      "file_type": ["py", "cpp", "c", "h", "hpp", "rs", "go", "js", "ts", "json", "toml", "yaml"],
      "enabled": true
    }
  },
  "search": {
    "symmetric": false,
    "max_results": 10
  }
}
EOF_KHOJ

echo -e "${GREEN}✔ Khoj index configuration created at ${KCLI_HOME}/khoj_index/khoj.json${NC}"

# ------------------------------------------------------------------------------
# 5. Execute DevDocs Ingestion Engine
# ------------------------------------------------------------------------------
echo -e "
${BOLD}${MAGENTA}📚 [5/5] Ingesting DevDocs (Go, JS, TS, DOM, Linux Syscalls, PyTorch, NumPy, Python, C++, Rust)...${NC}"

${PYTHON_EXEC} "${SCRIPT_DIR}/setup_knowledge.py" --db-path "${KCLI_HOME}/docs.db"

echo -e "
${BOLD}${GREEN}======================================================================${NC}"
echo -e "${BOLD}${GREEN}🎉 PROJECT BANKAI: Environment & Knowledge Engine Initialized!${NC}"
echo -e "${BOLD}${GREEN}======================================================================${NC}"
echo -e "SQLite Knowledge DB: ${BOLD}${KCLI_HOME}/docs.db${NC}"
echo -e "To query documentation via CLI: ${CYAN}sqlite3 ${KCLI_HOME}/docs.db "SELECT name, type FROM docs_fts WHERE docs_fts MATCH 'asyncio.Queue' LIMIT 5;"${NC}"
echo -e "${BOLD}${GREEN}======================================================================${NC}
"
