#!/bin/sh
# Runs the inbox guard with whichever Python this machine has. The guard reads the tool call on standard
# input and exits non-zero only for a direct edit to the owner's inbox file. It uses no network.
GUARD="${CLAUDE_PLUGIN_ROOT}/scripts/inbox_guard.py"
if command -v python >/dev/null 2>&1; then
  exec python "$GUARD"
fi
exec python3 "$GUARD"
