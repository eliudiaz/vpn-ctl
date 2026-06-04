#!/bin/bash
set -euo pipefail

echo ""
echo "⚠️  ROLLBACK: Restore monolithic dev stack"
echo ""

# Find the most recent backup
BACKUP_FILE=$(ls -t .pulumi-backups/dev-full-state-*.json 2>/dev/null | head -1)

if [ -z "$BACKUP_FILE" ]; then
    echo "❌ No backup file found"
    exit 1
fi

echo "Restoring from: $BACKUP_FILE"
echo ""
echo "Type 'ROLLBACK' to confirm: "
read -r CONFIRM

if [ "$CONFIRM" != "ROLLBACK" ]; then
    echo "Aborted."
    exit 0
fi

echo ""
echo "Deleting new stacks..."
cd pulumi

for STACK in core peer-vimenca peer-cibao peer-apap peer-internal-legacy-network; do
    if pulumi stack ls | grep -q "^$STACK\$"; then
        echo "   Deleting $STACK..."
        pulumi stack rm "$STACK" --force --yes 2>/dev/null || true
    fi
done

cd ..
echo "   ✓ New stacks deleted"

echo ""
echo "Restoring dev stack..."
cd pulumi
pulumi stack import --file "../$BACKUP_FILE" || {
    echo "❌ Restore failed"
    exit 1
}
cd ..

echo "   ✓ dev stack restored"

echo ""
echo "Verifying restore..."
DEV_COUNT=$(cd pulumi && pulumi export --json | python3 -c "import json, sys; print(len(json.load(sys.stdin).get('resources', [])))")
echo "   ✓ Restored $DEV_COUNT resources"

echo ""
echo "✅ ROLLBACK COMPLETE"
echo "   Monolithic dev stack restored"
echo "   Ready to investigate and retry"
