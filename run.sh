#!/usr/bin/env bash
# ./run.sh            serve on http://127.0.0.1:${PORT:-8110} with auto-reload
# ./run.sh test       run the test suite (offline, mock engine)
# ./run.sh setup      create the venv and install everything
# ./run.sh manual     digest conversations by hand, no AI calls (see app/manual.py)
# ./run.sh compare    try several Together models on one conversation (see app/compare.py)
set -euo pipefail
cd "$(dirname "$0")"

# ROS puts itself on PYTHONPATH system-wide on this machine and breaks imports.
unset PYTHONPATH

# Load .env if present, so a key set there reaches the app.
if [ -f .env ]; then set -a; . ./.env; set +a; fi

PY=./venv/bin/python
case "${1:-serve}" in
  setup)
    python3 -m venv venv
    # The Bee library lives next door until it's pushed to GitHub.
    if [ -d ../bee-cli-python ]; then ./venv/bin/pip install -q -e ../bee-cli-python; fi
    grep -v '^bee-cli-python' requirements.txt > .req.tmp && ./venv/bin/pip install -q -r .req.tmp && rm -f .req.tmp
    ./venv/bin/pip install -q pytest
    echo "ready: ./run.sh"
    ;;
  serve)
    [ -x "$PY" ] || { echo "run ./run.sh setup first"; exit 1; }
    exec "$PY" -m uvicorn app.main:app --reload --host 127.0.0.1 --port "${PORT:-8110}"
    ;;
  test)
    shift
    PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 exec "$PY" -m pytest -q "$@"
    ;;
  manual)
    shift
    exec "$PY" -m app.manual "$@"
    ;;
  compare)
    shift
    exec "$PY" -m app.compare "$@"
    ;;
  *) echo "usage: ./run.sh [serve|test|setup|manual|compare]"; exit 1 ;;
esac
