#!/bin/bash
# Setup development hooks and environment
# Run from backend/ directory
set -e

cd "$(dirname "$0")/.." || exit 1

echo "=== Backend Dev Setup ==="

# Install pre-commit hook
HOOK_SRC="scripts/pre-commit.hook"
HOOK_DST="../.git/hooks/pre-commit"

if [ -f "$HOOK_SRC" ]; then
    cp "$HOOK_SRC" "$HOOK_DST"
    chmod +x "$HOOK_DST"
    echo "✅ Pre-commit hook installed"
else
    echo "⚠️  Pre-commit hook source not found"
fi

# Check Python environment
if [ -f "../.venv311/bin/python" ] || [ -f "../.venv311/Scripts/python.exe" ]; then
    echo "✅ Python 3.11 venv detected"
else
    echo "⚠️  Python 3.11 venv not found at ../.venv311"
    echo "   Create it with: python3.11 -m venv ../.venv311"
fi

echo ""
echo "Done! Available commands:"
echo "  ./scripts/quality.sh          # Full lint + tests"
echo "  ./scripts/quality.sh --lint   # Lint only"
echo "  ./scripts/quality.sh --fix    # Autofix lint issues"
echo "  ./scripts/quality.sh --test   # Tests only"
