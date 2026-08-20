#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source /opt/homebrew/Caskroom/miniconda/base/etc/profile.d/conda.sh
conda activate vEffect
cd "$ROOT"
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
exec uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 "$@"
