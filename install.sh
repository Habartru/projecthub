#!/usr/bin/env bash
# ╔══════════════════════════════════════════════════════════╗
# ║           ProjectHub — One-line Installer                ║
# ║  curl -fsSL https://raw.githubusercontent.com/           ║
# ║    Habartru/projecthub/main/install.sh | bash            ║
# ╚══════════════════════════════════════════════════════════╝
set -euo pipefail

# ── Colors ─────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

ok()   { echo -e "${GREEN}✓${NC} $*"; }
info() { echo -e "${BLUE}→${NC} $*"; }
warn() { echo -e "${YELLOW}⚠${NC} $*"; }
err()  { echo -e "${RED}✗${NC} $*"; exit 1; }
step() { echo -e "\n${BOLD}${CYAN}$*${NC}"; }

INSTALL_DIR="${PROJECTHUB_DIR:-$HOME/.local/share/projecthub}"
PORT="${PROJECTHUB_PORT:-8472}"
REPO="https://github.com/Habartru/projecthub.git"

echo -e "${BOLD}"
echo "  ╔════════════════════════════════╗"
echo "  ║       🗂  ProjectHub           ║"
echo "  ║   Local Dev Dashboard + Brain  ║"
echo "  ╚════════════════════════════════╝"
echo -e "${NC}"

# ── Step 1: Check requirements ─────────────────────────────
step "Step 1/5 — Checking requirements"

command -v python3 &>/dev/null || err "Python 3 is required. Install from https://python.org"
PYVER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
info "Python $PYVER found"

# Require Python >= 3.10
python3 -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" \
  || err "Python 3.10+ required (found $PYVER)"

command -v git &>/dev/null || err "Git is required."
ok "Git found"

if command -v docker &>/dev/null; then
  ok "Docker found — LIVE badges will work"
else
  warn "Docker not found — LIVE badges disabled (install Docker to enable)"
fi

# ── Step 2: Clone / Update ─────────────────────────────────
step "Step 2/5 — Installing ProjectHub"

if [ -d "$INSTALL_DIR/.git" ]; then
  info "Existing install found at $INSTALL_DIR — updating..."
  git -C "$INSTALL_DIR" pull --ff-only
  ok "Updated to latest version"
else
  info "Cloning to $INSTALL_DIR ..."
  git clone --depth=1 "$REPO" "$INSTALL_DIR"
  ok "Cloned successfully"
fi

# ── Step 3: Python virtualenv + deps ──────────────────────
step "Step 3/5 — Installing Python dependencies"

VENV="$INSTALL_DIR/venv"
python3 -m venv "$VENV"
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet -r "$INSTALL_DIR/backend/requirements.txt"
ok "Backend dependencies installed"

# MCP server
MCP_VENV="$INSTALL_DIR/mcp-server/.venv"
python3 -m venv "$MCP_VENV"
"$MCP_VENV/bin/pip" install --quiet --upgrade pip
"$MCP_VENV/bin/pip" install --quiet -r "$INSTALL_DIR/mcp-server/requirements.txt"
ok "MCP server dependencies installed"

# ── Step 4: Configure MCP client ──────────────────────────
step "Step 4/5 — Configuring MCP server"

MCP_ENTRY=$(cat <<JSON
{
  "project-context": {
    "command": "$MCP_VENV/bin/python",
    "args": ["$INSTALL_DIR/mcp-server/server.py"]
  }
}
JSON
)

# Try to auto-inject into known MCP config locations
MCP_CONFIGS=(
  "$HOME/.config/Qoder/User/mcp.json"
  "$HOME/.claude/mcp_servers.json"
  "$HOME/Library/Application Support/Claude/mcp_servers.json"
)

INJECTED=false
for CFG in "${MCP_CONFIGS[@]}"; do
  if [ -f "$CFG" ]; then
    info "Found MCP config: $CFG"
    # Check if already registered
    if grep -q "project-context" "$CFG" 2>/dev/null; then
      ok "MCP server already registered in $CFG"
      INJECTED=true
      break
    fi
    # Inject using python json merge
    python3 - "$CFG" "$INSTALL_DIR/mcp-server/server.py" "$MCP_VENV/bin/python" <<'PYEOF'
import json, sys
cfg_path, srv_path, py_path = sys.argv[1], sys.argv[2], sys.argv[3]
with open(cfg_path) as f:
    cfg = json.load(f)
if "mcpServers" not in cfg:
    cfg["mcpServers"] = {}
cfg["mcpServers"]["project-context"] = {
    "command": py_path,
    "args": [srv_path]
}
with open(cfg_path, "w") as f:
    json.dump(cfg, f, indent=2)
print(f"  → Injected into {cfg_path}")
PYEOF
    INJECTED=true
    ok "MCP server registered in $CFG"
    break
  fi
done

if [ "$INJECTED" = false ]; then
  warn "Could not auto-register MCP server. Add manually:"
  echo ""
  echo -e "${YELLOW}  File: ~/.config/Qoder/User/mcp.json  (Windsurf/Cascade)${NC}"
  echo -e "${YELLOW}  File: ~/.claude/mcp_servers.json      (Claude Code)${NC}"
  echo ""
  echo '  Add inside "mcpServers": {'
  echo "    \"project-context\": {"
  echo "      \"command\": \"$MCP_VENV/bin/python\","
  echo "      \"args\": [\"$INSTALL_DIR/mcp-server/server.py\"]"
  echo "    }"
  echo "  }"
fi

# ── Step 5: Create launcher ────────────────────────────────
step "Step 5/5 — Creating launcher"

LAUNCHER="$HOME/.local/bin/projecthub"
mkdir -p "$(dirname "$LAUNCHER")"
cat > "$LAUNCHER" <<LAUNCH
#!/usr/bin/env bash
exec "$VENV/bin/python" "$INSTALL_DIR/backend/main.py" "\$@"
LAUNCH
chmod +x "$LAUNCHER"
ok "Launcher created: $LAUNCHER"

# Add to PATH hint if needed
if ! echo "$PATH" | grep -q "$HOME/.local/bin"; then
  warn "Add ~/.local/bin to your PATH:"
  echo "  echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.bashrc && source ~/.bashrc"
fi

# ── Optional: systemd autostart ───────────────────────────
if command -v systemctl &>/dev/null && systemctl --user status &>/dev/null 2>&1; then
  SVCDIR="$HOME/.config/systemd/user"
  mkdir -p "$SVCDIR"
  cat > "$SVCDIR/projecthub.service" <<SVC
[Unit]
Description=ProjectHub Dashboard
After=network.target

[Service]
WorkingDirectory=$INSTALL_DIR
ExecStart=$VENV/bin/python $INSTALL_DIR/backend/main.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
SVC
  systemctl --user daemon-reload
  ok "systemd service created (projecthub.service)"
  echo ""
  read -rp "  Enable autostart on login? [y/N] " AUTOSTART
  if [[ "$AUTOSTART" =~ ^[Yy]$ ]]; then
    systemctl --user enable --now projecthub.service
    ok "Autostart enabled"
  fi
fi

# ── Obsidian vault ─────────────────────────────────────────
VAULT="$HOME/Projects/@memory/brain"
if [ ! -d "$VAULT" ]; then
  mkdir -p "$VAULT/knowledge/projects" "$VAULT/logs"
  echo "# Knowledge Base Index" > "$VAULT/knowledge/index.md"
  ok "Brain vault created at $VAULT"
else
  ok "Brain vault already exists at $VAULT"
fi

# ── Done! ──────────────────────────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}${BOLD}  ✅  ProjectHub installed successfully!${NC}"
echo -e "${GREEN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "  ${BOLD}Start:${NC}   projecthub"
echo -e "  ${BOLD}Open:${NC}    http://localhost:$PORT"
echo -e "  ${BOLD}Brain vault:${NC} $VAULT"
echo ""
echo -e "  ${CYAN}Obsidian (optional):${NC} open $VAULT as vault"
echo -e "  ${CYAN}Restart AI client${NC} to activate MCP Brain tools"
echo ""
read -rp "  Start ProjectHub now? [Y/n] " START
if [[ ! "$START" =~ ^[Nn]$ ]]; then
  info "Starting on http://localhost:$PORT ..."
  "$LAUNCHER" &
  sleep 2
  if command -v xdg-open &>/dev/null; then
    xdg-open "http://localhost:$PORT" 2>/dev/null &
  elif command -v open &>/dev/null; then
    open "http://localhost:$PORT" &
  fi
  ok "ProjectHub is running! Press Ctrl+C to stop."
  wait
fi
