#!/usr/bin/env bash
# Run the account report in a small pixi environment (Python + matplotlib only).
set -euo pipefail
cd "$(dirname "$0")"
exec nice -n 10 "${PIXI:-$HOME/.pixi/bin/pixi}" exec --spec python=3.12 --spec matplotlib-base \
    python -s report.py "$@"
