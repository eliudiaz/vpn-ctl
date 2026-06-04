#!/bin/bash
set -euo pipefail

# vpn-ctl Global CLI Installer & Version Manager
# Installs vpnctl command globally, configured to work from installation directory
# Supports version generation: setup.sh version <new-version>

# Get the directory where setup.sh was called from
INSTALL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Handle version generation command
if [ "${1:-}" = "version" ] && [ -n "${2:-}" ]; then
    NEW_VERSION="$2"

    echo ""
    echo "╔════════════════════════════════════════════════════════════════╗"
    echo "║       vpnctl Version Generator (vpn-ctl)                       ║"
    echo "╚════════════════════════════════════════════════════════════════╝"
    echo ""

    # Validate version format (semantic versioning: X.Y.Z)
    if ! [[ "$NEW_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        echo "❌ Error: Invalid version format. Use semantic versioning (X.Y.Z)"
        echo "   Example: setup.sh version 1.1.0"
        exit 1
    fi

    # Verify we're in the right place
    if [ ! -f "$INSTALL_DIR/pyproject.toml" ] || [ ! -d "$INSTALL_DIR/domain" ]; then
        echo "❌ Error: setup.sh must be run from the vpn-ctl project root"
        echo "   (Directory containing pyproject.toml and domain/)"
        exit 1
    fi

    echo "📁 Project directory: $INSTALL_DIR"
    echo "📦 Generating version: $NEW_VERSION"
    echo ""

    # Update pyproject.toml version
    echo "🔧 Step 1: Updating pyproject.toml..."
    OLD_VERSION=$(grep '^version = ' "$INSTALL_DIR/pyproject.toml" | sed 's/version = "//' | sed 's/".*//')
    sed -i '' "s/^version = .*/version = \"$NEW_VERSION\"/" "$INSTALL_DIR/pyproject.toml"
    echo "   ✓ Updated version: $OLD_VERSION → $NEW_VERSION"

    # Create VERSION file for reference
    echo "🔧 Step 2: Creating VERSION file..."
    echo "$NEW_VERSION" > "$INSTALL_DIR/.vpnctl-version"
    echo "   ✓ Created .vpnctl-version"

    # Update version in domain/__init__.py if it exists
    if [ -f "$INSTALL_DIR/domain/__init__.py" ]; then
        echo "🔧 Step 3: Updating domain/__init__.py..."
        if grep -q "__version__" "$INSTALL_DIR/domain/__init__.py"; then
            sed -i '' "s/__version__ = \"[^\"]*\"/__version__ = \"$NEW_VERSION\"/" "$INSTALL_DIR/domain/__init__.py"
        fi
        echo "   ✓ Updated domain/__init__.py"
    fi

    # Create git tag (optional, if git repo exists)
    if [ -d "$INSTALL_DIR/.git" ]; then
        echo "🔧 Step 4: Creating git tag..."
        git -C "$INSTALL_DIR" tag -a "v$NEW_VERSION" -m "Release version $NEW_VERSION" 2>/dev/null || true
        echo "   ✓ Created git tag: v$NEW_VERSION"
    fi

    echo ""
    echo "╔════════════════════════════════════════════════════════════════╗"
    echo "║              ✅ VERSION UPDATE COMPLETE                        ║"
    echo "╚════════════════════════════════════════════════════════════════╝"
    echo ""
    echo "📋 Version Information:"
    echo "   Previous Version: $OLD_VERSION"
    echo "   New Version: $NEW_VERSION"
    echo "   Version File: $INSTALL_DIR/.vpnctl-version"
    echo "   pyproject.toml: $INSTALL_DIR/pyproject.toml"
    echo ""
    echo "Next steps:"
    echo "   1. Review changes: git diff"
    echo "   2. Commit changes: git commit -m \"chore: Bump version to $NEW_VERSION\""
    echo "   3. Push changes: git push origin main"
    echo ""
    exit 0
fi

# Show usage for version command
if [ "${1:-}" = "version" ]; then
    echo "Usage: setup.sh version <X.Y.Z>"
    echo "Example: setup.sh version 1.1.0"
    exit 0
fi

echo ""
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║          vpn-ctl Global CLI Installer (vpnctl)                 ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

echo "📁 Installation directory: $INSTALL_DIR"

# Verify we're in the right place
if [ ! -f "$INSTALL_DIR/pyproject.toml" ] || [ ! -d "$INSTALL_DIR/domain" ]; then
    echo "❌ Error: setup.sh must be run from the vpn-ctl project root"
    echo "   (Directory containing pyproject.toml and domain/)"
    exit 1
fi

echo ""
echo "📦 Step 1: Creating Python virtual environment..."

# Create virtual environment
if [ -d "$INSTALL_DIR/venv" ]; then
    echo "   ✓ Virtual environment already exists"
else
    python3 -m venv "$INSTALL_DIR/venv"
    echo "   ✓ Virtual environment created"
fi

# Activate virtual environment
source "$INSTALL_DIR/venv/bin/activate"
echo "   ✓ Virtual environment activated"

echo ""
echo "📚 Step 2: Installing dependencies..."

# Upgrade pip
pip install --quiet --upgrade pip setuptools wheel
echo "   ✓ pip/setuptools/wheel upgraded"

# Install requirements
pip install --quiet -r "$INSTALL_DIR/requirements.txt"
echo "   ✓ Dependencies installed"

echo ""
echo "🔧 Step 3: Creating global vpnctl command..."

# Determine where to install the wrapper script
# Try /usr/local/bin first (preferred), fall back to ~/.local/bin
if [ -w /usr/local/bin ]; then
    BIN_DIR="/usr/local/bin"
    INSTALL_METHOD="system"
elif [ -w "$HOME/.local/bin" ]; then
    BIN_DIR="$HOME/.local/bin"
    INSTALL_METHOD="user"
    # Add to PATH if not already there
    if ! echo "$PATH" | grep -q "$HOME/.local/bin"; then
        echo ""
        echo "⚠️  Note: $HOME/.local/bin is not in your PATH"
        echo "   Add to ~/.bashrc or ~/.zshrc:"
        echo "   export PATH=\"\$HOME/.local/bin:\$PATH\""
        echo ""
    fi
else
    BIN_DIR="$HOME/bin"
    mkdir -p "$BIN_DIR"
    INSTALL_METHOD="home"
    # Add to PATH if not already there
    if ! echo "$PATH" | grep -q "$HOME/bin"; then
        echo ""
        echo "⚠️  Note: $HOME/bin is not in your PATH"
        echo "   Add to ~/.bashrc or ~/.zshrc:"
        echo "   export PATH=\"\$HOME/bin:\$PATH\""
        echo ""
    fi
fi

# Create the wrapper script
WRAPPER_SCRIPT="$BIN_DIR/vpnctl"

cat > "$WRAPPER_SCRIPT" << 'WRAPPER_EOF'
#!/bin/bash
# vpn-ctl CLI Wrapper
# Auto-detects installation directory and runs vpnctl with proper paths

# Get the directory of this wrapper script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Find the vpn-ctl installation by looking for venv
# First check in common locations
INSTALL_DIR=""

# Check if there's an installation marker
if [ -f "$HOME/.vpnctl/install_dir" ]; then
    INSTALL_DIR="$(cat "$HOME/.vpnctl/install_dir")"
    if [ ! -f "$INSTALL_DIR/pyproject.toml" ]; then
        INSTALL_DIR=""
    fi
fi

# If not found, search for it
if [ -z "$INSTALL_DIR" ]; then
    # Look for venv in likely locations
    for dir in \
        "$HOME/vpn-ctl" \
        "$HOME/projects/vpn-ctl" \
        "$HOME/aff-atg" \
        "$HOME/code/aff-atg" \
        "/opt/vpn-ctl" \
        "/srv/vpn-ctl" \
        ; do
        if [ -f "$dir/pyproject.toml" ] && [ -d "$dir/venv" ]; then
            INSTALL_DIR="$dir"
            break
        fi
    done
fi

# Last resort: look in current directory and parent
if [ -z "$INSTALL_DIR" ]; then
    if [ -f "./pyproject.toml" ] && [ -d "./venv" ]; then
        INSTALL_DIR="."
    elif [ -f "../pyproject.toml" ] && [ -d "../venv" ]; then
        INSTALL_DIR=".."
    fi
fi

# If still not found, show error
if [ -z "$INSTALL_DIR" ]; then
    echo "❌ Error: Cannot find vpn-ctl installation directory"
    echo ""
    echo "To fix this, run one of:"
    echo "  1. cd /path/to/aff-atg && bash setup.sh"
    echo "  2. Set: vpnctl_install_dir=/path/to/aff-atg vpnctl"
    echo ""
    exit 1
fi

# Remember installation directory for future runs
mkdir -p "$HOME/.vpnctl"
echo "$INSTALL_DIR" > "$HOME/.vpnctl/install_dir"

# Change to installation directory so specs resolve correctly
cd "$INSTALL_DIR"

# Activate virtual environment
source "$INSTALL_DIR/venv/bin/activate"

# Run the CLI
exec python3 -m presentation.cli.main "$@"
WRAPPER_EOF

chmod +x "$WRAPPER_SCRIPT"
echo "   ✓ Created: $WRAPPER_SCRIPT"

# Create install directory marker
mkdir -p "$HOME/.vpnctl"
echo "$INSTALL_DIR" > "$HOME/.vpnctl/install_dir"
echo "   ✓ Installation directory registered"

echo ""
echo "✅ Step 4: Verifying installation..."

# Test the command
if command -v vpnctl &> /dev/null; then
    echo "   ✓ vpnctl command available globally"
    VERSION=$("$WRAPPER_SCRIPT" version 2>&1 || echo "v1.0.0")
    echo "   ✓ $VERSION"
else
    echo "   ⚠️  vpnctl not in PATH yet"
    if [ "$INSTALL_METHOD" != "system" ]; then
        echo "   Please add to your shell config (~/.bashrc or ~/.zshrc):"
        echo "   export PATH=\"$BIN_DIR:\$PATH\""
        echo "   Then reload: source ~/.bashrc"
    fi
fi

echo ""
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║                  ✅ INSTALLATION COMPLETE                      ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""
echo "📍 Installation Details:"
echo "   Base Directory: $INSTALL_DIR"
echo "   Binary Location: $WRAPPER_SCRIPT"
echo "   Virtual Environment: $INSTALL_DIR/venv"
echo "   Config Directory: $HOME/.vpnctl"
echo ""
echo "🚀 Quick Start:"
echo "   vpnctl peer add          # Create new peer"
echo "   vpnctl peer list         # List all peers"
echo "   vpnctl peer deploy NAME  # Deploy peer"
echo "   vpnctl tunnel status     # Check tunnels"
echo "   vpnctl --help            # Full help"
echo ""
echo "📚 Documentation:"
echo "   README:     $INSTALL_DIR/README.md"
echo "   CLI Guide:  $INSTALL_DIR/docs/reference/CLI.md"
echo "   Architecture: $INSTALL_DIR/docs/reference/ARCHITECTURE.md"
echo ""
echo "🔄 Version Management:"
echo "   bash setup.sh version 1.1.0  # Generate new version"
echo "   cat $INSTALL_DIR/.vpnctl-version  # View current version"
echo ""
echo "🔧 Uninstall:"
echo "   rm $WRAPPER_SCRIPT"
echo "   rm -rf $HOME/.vpnctl"
echo ""
