#!/bin/bash

################################################################################
# Quick Access Script
# Add this to your shell profile to access skills easily
################################################################################

# Source this file to add skills to PATH:
# source .claude/QUICK-ACCESS.sh

CLAUDE_SKILLS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Add .claude directory to PATH
export PATH="$CLAUDE_SKILLS_DIR:$PATH"

echo "✓ Claude skills added to PATH"
echo "Available commands:"
ls -1 "$CLAUDE_SKILLS_DIR"/skill-* 2>/dev/null | xargs -I {} basename {} | sed 's/^/  ✓ /'
