#!/usr/bin/env bash
set -euo pipefail
echo "Running tests with pytest..."
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt
pytest -q
echo "Tests finished." 