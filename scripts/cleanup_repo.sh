#!/usr/bin/env bash
set -euo pipefail
echo "Cleaning up repository: removing __pycache__ and untracking .env if present..."
find . -type d -name '__pycache__' -print0 | xargs -0 rm -rf || true
git rm -f --quiet --ignore-unmatch .env || true
echo "Cleanup complete. Don't forget to commit any changes: git add -A && git commit -m 'cleanup' && git push" 