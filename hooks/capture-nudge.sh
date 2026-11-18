#!/bin/sh
# Runs the capture nudge with whichever Python this machine has. It reads the stop event on standard input and
# prints a request to capture finished work, or nothing. It never fails the session and uses no network.
NUDGE="${CLAUDE_PLUGIN_ROOT}/scripts/capture_nudge.py"
if command -v python >/dev/null 2>&1; then
  exec python "$NUDGE"
fi
exec python3 "$NUDGE"
