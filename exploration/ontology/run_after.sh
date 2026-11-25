#!/bin/bash
# Runs after run_local.sh (started while it was running): reference baseline, then figures.
cd "$(dirname "$0")"
while pgrep -f "run_local.sh" > /dev/null; do sleep 60; done
for attempt in 1 2 3; do ./py.sh reference-baseline.py --max_documents 500 && break; done
./py.sh make-figures.py
