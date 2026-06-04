#!/bin/bash
set -euo pipefail

echo ""
echo "🧪 DRY-RUN: Test state extraction"
echo "   (No changes to actual stacks)"
echo ""

echo "1️⃣  Running pre-extraction checks..."
python3 scripts/state-extraction/state_extractor.py validate > /dev/null && echo "   ✓ All checks passed" || {
    echo "   ❌ Validation failed"
    exit 1
}

echo ""
echo "2️⃣  Testing state splitting..."
python3 scripts/state-extraction/state_splitter.py > /dev/null && echo "   ✓ State split successful" || {
    echo "   ❌ State splitting failed"
    exit 1
}

echo ""
echo "3️⃣  Verifying zero data loss..."
python3 scripts/state-extraction/verify_no_loss.py > /dev/null && echo "   ✓ No data loss detected" || {
    echo "   ❌ Data loss detected"
    exit 1
}

echo ""
echo "✅ DRY-RUN PASSED"
echo "   Safe to proceed with actual extraction"
