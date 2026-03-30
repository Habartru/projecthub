#!/bin/bash
# Install Project Context MCP Server

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"

echo "Setting up Project Context MCP Server..."

# Create virtual environment
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
fi

# Activate and install dependencies
source "$VENV_DIR/bin/activate"
pip install --upgrade pip
pip install -r "$SCRIPT_DIR/requirements.txt"

# Create log directory
mkdir -p ~/.config/project-context

# Make server executable
chmod +x "$SCRIPT_DIR/server.py"

echo ""
echo "Installation complete!"
echo ""

# Claude Code config
echo "=== Claude Code ==="
echo ""
echo "Run this command to add the MCP server to Claude Code:"
echo ""
echo "  claude mcp add project-context $VENV_DIR/bin/python $SCRIPT_DIR/server.py"
echo ""
echo "Or manually add to ~/.claude.json:"
echo ""
cat << EOF
{
  "mcpServers": {
    "project-context": {
      "command": "$VENV_DIR/bin/python",
      "args": ["$SCRIPT_DIR/server.py"]
    }
  }
}
EOF

echo ""
echo "=== Windsurf ==="
echo ""
echo "Add to ~/.codeium/windsurf/mcp_config.json:"
echo ""
cat << EOF
{
  "mcpServers": {
    "project-context": {
      "command": "$VENV_DIR/bin/python",
      "args": ["$SCRIPT_DIR/server.py"]
    }
  }
}
EOF

echo ""
echo "Then restart your editor."
