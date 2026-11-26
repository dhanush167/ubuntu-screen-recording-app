#!/bin/sh
# Build the package and install it with its dependencies (Ubuntu 24.04 / 25.x).
set -eu
here="$(dirname "$(readlink -f "$0")")"

command -v apt-get >/dev/null || { echo "This installer needs apt (Ubuntu)." >&2; exit 1; }
if [ "$(id -u)" -eq 0 ]; then sudo=""; else sudo="sudo"; fi

package="$(sh "$here/packaging/build-deb.sh")"

# apt reads local packages as an unprivileged user, so hand it a readable copy.
copy="$(mktemp -d)"
trap 'rm -rf "${copy:?}"' EXIT
chmod 755 "$copy"
install -m644 "$package" "$copy/"

$sudo apt-get update
$sudo apt-get install -y --reinstall "$copy/$(basename "$package")"

echo
echo "Installed. Open 'Screen Recorder' from the app menu, or run: screen-recorder"
