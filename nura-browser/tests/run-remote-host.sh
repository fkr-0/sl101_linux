#!/bin/sh
# SPDX-License-Identifier: MIT
# Host-only real AF_UNIX client tests. No browser, compositor or tablet.
set -eu
here=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
root=$(CDPATH='' cd -- "$here/.." && pwd)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT HUP INT TERM
# Meson also registers this host-only test in ARMHF cross-builds.
# Never accidentally compile x86 test code against the cross sysroot.
unset PKG_CONFIG_LIBDIR PKG_CONFIG_SYSROOT_DIR PKG_CONFIG_PATH
if ! pkg-config --exists glib-2.0 gio-2.0 gio-unix-2.0 json-glib-1.0; then
    echo 'SKIP: native GLib/GIO/JSON-GLib development headers unavailable' >&2
    exit 77
fi
cat >"$tmp/main.c" <<'EOF'
#include "remote.h"
int main(int argc, char **argv) {
    return nurabrowser_remote_main(argc - 1, argv + 1);
}
EOF
# Deliberate word splitting of pkg-config's flags in POSIX sh.
# shellcheck disable=SC2086
cc -std=c11 -D_POSIX_C_SOURCE=200809L -Wall -Wextra -Wpedantic -Werror -O2 \
  -I"$root/src/control" \
  $(pkg-config --cflags glib-2.0 gio-2.0 gio-unix-2.0 json-glib-1.0) \
  "$root/src/control/remote.c" "$tmp/main.c" \
  $(pkg-config --libs glib-2.0 gio-2.0 gio-unix-2.0 json-glib-1.0) \
  -o "$tmp/remote-host"
python3 "$here/test_remote_host.py" "$tmp/remote-host"
