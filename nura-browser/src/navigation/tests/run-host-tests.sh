#!/bin/sh
# SPDX-License-Identifier: MIT
# Builds against an isolated test double: not a WPE/ARMHF build.
set -eu
cd "$(dirname "$0")"
: "${CC:=cc}"
pkg-config --exists glib-2.0 gio-2.0 gobject-2.0
build_dir="$(mktemp -d)"
trap 'rm -rf "$build_dir"' EXIT HUP INT TERM
"$CC" -std=c11 -D_POSIX_C_SOURCE=200809L -Wall -Wextra -Werror -pedantic \
    -g -O1 \
    -Istubs -I../../../include \
    $(pkg-config --cflags glib-2.0 gio-2.0 gobject-2.0) \
    ../url.c ../state.c ../navigation.c fake_webkit.c test_navigation.c \
    $(pkg-config --libs glib-2.0 gio-2.0 gobject-2.0) \
    -o "$build_dir/test-navigation"
"$build_dir/test-navigation" "$@"
