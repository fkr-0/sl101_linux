#!/bin/sh
# SPDX-License-Identifier: MIT
# Host-only CPU test. NEVER used as evidence for WebKit or ARMHF compilation.
set -eu
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
root=$(CDPATH= cd -- "$here/../../.." && pwd)
out=$(mktemp -d)
trap 'rm -rf -- "$out"' EXIT HUP INT TERM
cflags=$(pkg-config --cflags glib-2.0 gio-2.0 gio-unix-2.0 json-glib-1.0)
libs=$(pkg-config --libs glib-2.0 gio-2.0 gio-unix-2.0 json-glib-1.0)
# Deliberate word splitting for flags from pkg-config.
# shellcheck disable=SC2086
cc -std=c11 -O2 -g -Wall -Wextra -Werror \
  -DNURABROWSER_CONTROL_IDLE_SECONDS=1 \
  -I"$root/include" -I"$here/stubs" -I"$root/src/control" \
  $cflags "$root/src/control/control.c" "$here/test-control.c" \
  $libs -o "$out/test-control"
G_DEBUG=fatal-warnings "$out/test-control" "$@"
