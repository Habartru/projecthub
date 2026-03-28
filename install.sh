#!/bin/bash
# ProjectHub - One-line installer
# Usage: curl -fsSL https://raw.githubusercontent.com/yourusername/projecthub/main/install.sh | bash

set -e

echo "🚀 Installing ProjectHub..."

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

# Detect OS
OS=$(uname -s)
ARCH=$(uname -m)

echo -e "${BLUE}Detected: $OS ($ARCH)${NC}"

# Installation directory
INSTALL_DIR="$HOME/.local/share/projecthub"
BIN_DIR="$HOME/.local/bin"

echo "📦 Downloading ProjectHub..."

# Create directories
mkdir -p "$INSTALL_DIR"
mkdir -p "$BIN_DIR"

# Clone or download
cd "$INSTALL_DIR"

if command -v git &> /dev/null; then
    git clone --depth 1 https://github.com/yourusername/projecthub.git repo
    cp -r repo/* .
    rm -rf repo
else
    echo "Git not found. Please install git first."
    exit 1
fi

# Create virtual environment
echo "🐍 Creating Python environment..."
python3 -m venv venv
source venv/bin/activate

# Install dependencies
echo "📚 Installing dependencies..."
pip install -q -r requirements.txt

# Create launcher script
cat > "$BIN_DIR/projecthub" << 'EOF'
#!/bin/bash
INSTALL_DIR="$HOME/.local/share/projecthub"
cd "$INSTALL_DIR"
source venv/bin/activate
python backend/main.py "$@"
EOF

chmod +x "$BIN_DIR/projecthub"

# Create dash command
cat > "$BIN_DIR/dash" << 'EOF'
#!/bin/bash
echo "🚀 Starting ProjectHub..."
open http://localhost:8472/static/index.html 2>/dev/null || xdg-open http://localhost:8472/static/index.html 2>/dev/null || echo "Open: http://localhost:8472/static/index.html"
projecthub
EOF

chmod +x "$BIN_DIR/dash"

# Add to PATH if needed
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
    echo "export PATH=\"$BIN_DIR:\$PATH\"" >> "$HOME/.bashrc"
    echo "export PATH=\"$BIN_DIR:\$PATH\"" >> "$HOME/.zshrc" 2>/dev/null || true
fi

echo -e "${GREEN}✅ ProjectHub installed successfully!${NC}"
echo ""
echo "🎉 Quick start:"
echo "   dash        - Launch ProjectHub"
echo "   projecthub  - Start server manually"
echo ""
echo "📍 Installation: $INSTALL_DIR"
echo "🌐 Dashboard:   http://localhost:8472"
echo ""
echo "💡 Tip: Run 'dash' to start ProjectHub"
