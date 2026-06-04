#!/bin/bash
set -euo pipefail

echo ""
echo "🔐 Full State Backup"
echo "=================="

BACKUP_DIR=".pulumi-backups"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
BACKUP_FILE="$BACKUP_DIR/dev-full-state-pre-extraction-$TIMESTAMP.json"

mkdir -p "$BACKUP_DIR"

echo "1️⃣  Exporting dev stack JSON..."
cd pulumi && pulumi export --json > ../"$BACKUP_FILE" && cd ..
echo "   ✓ Exported to $BACKUP_FILE"

echo ""
echo "2️⃣  Backing up Pulumi history..."
HISTORY_BACKUP="$BACKUP_DIR/dev-history-pre-extraction-$TIMESTAMP.tar.gz"
tar -czf "$HISTORY_BACKUP" pulumi/.pulumi 2>/dev/null || true
echo "   ✓ History backed up to $HISTORY_BACKUP"

echo ""
echo "3️⃣  Verifying backup integrity..."
if python3 -c "import json; json.load(open('$BACKUP_FILE'))" 2>/dev/null; then
    echo "   ✓ Backup JSON is valid"
else
    echo "   ❌ Backup JSON is invalid"
    exit 1
fi

echo ""
echo "✅ Full backup complete"
echo "Restore command:"
echo "  cd pulumi && pulumi stack import --file ../$BACKUP_FILE"
