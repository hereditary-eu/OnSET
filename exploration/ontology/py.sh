#!/bin/sh
# Python 3.13 with backend/.venv's packages (CUDA llama-cpp-python) and backend/src importable.
HERE=$(cd "$(dirname "$0")" && pwd)
SITE="$HERE/../../backend/.venv/lib/python3.13/site-packages"
export PYTHONPATH="$SITE:$HERE/../../backend/src:$HERE"
export LD_LIBRARY_PATH="$SITE/nvidia/cu13/lib:$LD_LIBRARY_PATH"
exec "$(uv python find 3.13)" -s -u -X faulthandler "$@"
