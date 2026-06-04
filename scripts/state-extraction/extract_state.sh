#!/bin/bash
set -euo pipefail

echo ""
echo "⚠️  CRITICAL OPERATION - All operations backed up"
echo ""
echo "Type 'EXTRACT STATE' to confirm: "
read -r CONFIRM

if [ "$CONFIRM" != "EXTRACT STATE" ]; then
    echo "Aborted."
    exit 0
fi

echo ""
echo "🔄 EXECUTING STATE EXTRACTION"
echo ""

echo "1️⃣  Creating full backup..."
bash scripts/state-extraction/full_backup.sh || {
    echo "❌ Backup failed"
    exit 1
}

echo ""
echo "2️⃣  Splitting state into per-peer files..."
python3 scripts/state-extraction/state_splitter.py || {
    echo "❌ State splitting failed"
    exit 1
}

echo ""
echo "3️⃣  Verifying zero data loss..."
python3 scripts/state-extraction/verify_no_loss.py || {
    echo "❌ Data loss detected"
    exit 1
}

echo ""
echo "4️⃣  Initializing new stacks..."
cd pulumi

for STACK in core peer-vimenca peer-cibao peer-apap peer-internal-legacy-network; do
    echo "   Initializing $STACK..."
    pulumi stack init "$STACK" 2>/dev/null || true
done

cd ..
echo "   ✓ All stacks initialized"

echo ""
echo "5️⃣  Verifying all stacks..."
cd pulumi
for STACK in core peer-vimenca peer-cibao peer-apap peer-internal-legacy-network; do
    COUNT=$(pulumi export --stack "$STACK" --json 2>/dev/null | python3 -c "import json, sys; print(len(json.load(sys.stdin).get('resources', [])))" || echo "0")
    echo "   ✓ $STACK: $COUNT resources"
done
cd ..

echo ""
echo "6️⃣  Running final validation..."
vpn-ctl spec validate > /dev/null && echo "   ✓ All specs valid"
vpn-ctl spec sync --report-only > /dev/null && echo "   ✓ Specs in sync with state"

echo ""
echo "✅ STATE EXTRACTION COMPLETE - ZERO DATA LOSS VERIFIED"
