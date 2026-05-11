#!/bin/bash
# Pre-commit checks for xsw backend
# Run this before every git commit to catch issues early

set -e

echo "🔍 Running ruff linter..."
ruff check --fix

echo "✨ Running ruff formatter..."
ruff format

echo "🧪 Running unit tests..."
python3 -m pytest tests/test_octile_api.py -k "validate_" -q

echo "✅ All checks passed! Safe to commit."
