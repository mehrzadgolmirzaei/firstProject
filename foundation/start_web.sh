#!/usr/bin/env sh
# سامانه وب روی لینوکس/مک
cd "$(dirname "$0")"
[ -x .venv/bin/python ] || python3 -m venv .venv
.venv/bin/python -m pip install -q -r requirements.txt
cd web && FOUNDATION_OPEN_BROWSER=1 ../.venv/bin/python server.py
