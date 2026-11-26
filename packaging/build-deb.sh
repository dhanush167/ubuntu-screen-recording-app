#!/bin/sh
# Build dist/screen-recorder_<version>_all.deb
set -eu
root="$(dirname "$(dirname "$(readlink -f "$0")")")"
version="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$root/screen_recorder/__init__.py")"
[ -n "$version" ] || { echo "Could not read the version." >&2; exit 1; }
id="io.github.local.ScreenRecorder"

umask 022
stage="$(mktemp -d)"
trap 'rm -rf "${stage:?}"' EXIT
chmod 755 "$stage"

for file in "$root"/screen_recorder/*.py; do
    install -Dm644 "$file" "$stage/usr/lib/screen-recorder/screen_recorder/$(basename "$file")"
done
install -Dm755 "$root/packaging/screen-recorder" "$stage/usr/bin/screen-recorder"
install -Dm644 "$root/data/$id.desktop" "$stage/usr/share/applications/$id.desktop"
install -Dm644 "$root/data/icon.svg" "$stage/usr/share/icons/hicolor/scalable/apps/$id.svg"
install -Dm644 "$root/README.md" "$stage/usr/share/doc/screen-recorder/README.md"

mkdir -p "$stage/DEBIAN" "$root/dist"
size="$(du -sk "$stage/usr" | cut -f1)"
sed -e "s/@VERSION@/$version/" -e "s/@SIZE@/$size/" "$root/packaging/control.in" \
    > "$stage/DEBIAN/control"

package="$root/dist/screen-recorder_${version}_all.deb"
dpkg-deb --root-owner-group --build "$stage" "$package" >/dev/null
echo "$package"
