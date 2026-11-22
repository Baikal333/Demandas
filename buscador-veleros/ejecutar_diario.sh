#!/usr/bin/env bash
# Búsqueda diaria de veleros. Prográmelo con cron (ver README).
set -euo pipefail
cd "$(dirname "$0")"
[ -d .venv ] && source .venv/bin/activate
mkdir -p registros
python -m veleros ejecutar "$@" >> "registros/$(date +%F).log" 2>&1
