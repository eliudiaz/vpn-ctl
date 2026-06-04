#!/bin/bash
set -euo pipefail

# vpn-ctl Global CLI Uninstaller

echo ""
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║        vpn-ctl Global CLI Uninstaller (vpnctl)                 ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

# Check if installed
if [ ! -f "$HOME/.vpnctl/install_dir" ]; then
    echo "ℹ️  vpnctl is not installed"
    exit 0
fi

INSTALL_DIR="$(cat "$HOME/.vpnctl/install_dir")"

echo "Uninstalling vpnctl..."
echo "  Install Dir: $INSTALL_DIR"
echo ""

# Find and remove wrapper script
for BIN_DIR in /usr/local/bin "$HOME/.local/bin" "$HOME/bin"; do
    if [ -f "$BIN_DIR/vpnctl" ]; then
        echo "  Removing: $BIN_DIR/vpnctl"
        rm -f "$BIN_DIR/vpnctl"
    fi
done

# Remove configuration
echo "  Removing: $HOME/.vpnctl/"
rm -rf "$HOME/.vpnctl"

echo ""
echo "✅ Uninstalled successfully"
echo ""
echo "To remove the entire installation directory:"
echo "  rm -rf $INSTALL_DIR"
echo ""
