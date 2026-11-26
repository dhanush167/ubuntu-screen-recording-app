#!/bin/sh
# Remove Screen Recorder. Your recordings are never touched.
set -eu
if [ "$(id -u)" -eq 0 ]; then sudo=""; else sudo="sudo"; fi

# The hotkey lives in your own desktop settings, so remove it before the app.
if [ -x /usr/bin/screen-recorder ]; then
    /usr/bin/screen-recorder --remove-hotkey || echo "Could not remove the hotkey."
fi

$sudo apt-get remove -y screen-recorder

echo "Removed. Settings remain in ~/.config/screen-recorder (delete it if you like)."
