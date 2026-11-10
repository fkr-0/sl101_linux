#!/bin/sh
# SPDX-License-Identifier: MIT
# Actual control + navigation linked with a CPU-only fake WebKit fixture.
# This never qualifies WPE, ARMHF, sandbox, or hardware.
set -eu
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
src=$(CDPATH= cd -- "$here/.." && pwd)
tmp=$(mktemp -d)
trap 'rm -rf -- "$tmp"' EXIT HUP INT TERM
pkg-config --exists glib-2.0 gio-2.0 gio-unix-2.0 gobject-2.0 json-glib-1.0
# shellcheck disable=SC2086
cc -std=c11 -D_POSIX_C_SOURCE=200809L -O1 -g \
    -Wall -Wextra -Werror -Wpedantic \
    -I"$src/include" -I"$src/src/navigation/tests/stubs" \
    $(pkg-config --cflags glib-2.0 gio-2.0 gio-unix-2.0 gobject-2.0 json-glib-1.0) \
    "$src/src/navigation/url.c" \
    "$src/src/navigation/state.c" \
    "$src/src/navigation/navigation.c" \
    "$src/src/navigation/tests/fake_webkit.c" \
    "$src/src/control/control.c" \
    "$here/test_crosslane_ipc.c" \
    $(pkg-config --libs glib-2.0 gio-2.0 gio-unix-2.0 gobject-2.0 json-glib-1.0) \
    -o "$tmp/test-crosslane"
G_DEBUG=fatal-warnings "$tmp/test-crosslane" "$@"
