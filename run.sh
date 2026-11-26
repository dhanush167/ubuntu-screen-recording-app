#!/bin/sh
# Run Screen Recorder from this folder, without installing it.
here="$(dirname "$(readlink -f "$0")")"
export SCREEN_RECORDER_CMD="$here/run.sh"
export PYTHONPATH="$here${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONDONTWRITEBYTECODE=1
exec /usr/bin/python3 -P -m screen_recorder "$@"
