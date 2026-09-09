#!/bin/sh
# Panchayat -- enable the shared git hooks. Run once, per machine.
#
#   sh scripts/setup-hooks.sh
#
# macOS / Linux equivalent of setup-hooks.ps1.

set -e

repo=$(git rev-parse --show-toplevel 2>/dev/null) || {
    echo "Not inside a git repository."
    exit 1
}
cd "$repo"

git config core.hooksPath .githooks
chmod +x .githooks/pre-commit

if [ "$(git config core.hooksPath)" = ".githooks" ]; then
    echo ""
    echo "  Hooks enabled."
    echo ""
    echo "  Commits to main are now blocked, and staged AWS keys or .env"
    echo "  files are refused before they can reach the repo."
    echo ""
    echo "  Override when you genuinely mean to:  git commit --no-verify"
    echo ""
else
    echo "Failed to set core.hooksPath."
    exit 1
fi
