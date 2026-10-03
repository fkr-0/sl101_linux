#!/bin/sh
# Install a supplied qualified ARMv7 binary set; never change renderer/session.
set -eu
source_dir=${1:?usage: sl101-panel-install.sh DIRECTORY RELEASE}
release=${2:?release required}
case "$release" in ''|*[!a-zA-Z0-9._-]*) echo 'invalid release' >&2; exit 2;; esac
base=/opt/nuraloumi
destination=$base/releases/$release
[ -x "$source_dir/nuraloumi-panel" ] || { echo 'source panel missing or not executable' >&2; exit 1; }
[ ! -e "$destination" ]
mkdir -p "$destination"
for binary in nuraloumi-panel nuraloumi-menu nuraloumi-probe nuraloumi-thumbnail-helper; do
    [ ! -f "$source_dir/$binary" ] || install -m 755 "$source_dir/$binary" "$destination/$binary"
done
[ -x "$destination/nuraloumi-panel" ]
(cd "$destination" && sha256sum nuraloumi-* > SHA256SUMS && sha256sum -c SHA256SUMS)
if [ -L "$base/current" ]; then
    previous=$(readlink "$base/current")
    ln -sfn "$previous" "$base/previous"
fi
ln -s "releases/$release" "$base/.current-new"
mv -Tf "$base/.current-new" "$base/current"
printf 'Installed %s; restart the panel/session to activate. Rollback: point current to previous.\n' "$release"
