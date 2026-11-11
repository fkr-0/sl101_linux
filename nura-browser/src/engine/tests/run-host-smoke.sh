#!/bin/sh
# SPDX-License-Identifier: MIT
# Self-contained offline checks; never contacts or alters a tablet.
set -eu

here=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
engine=$(dirname "$here")
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT HUP INT TERM

python3 - "$engine" <<'PY'
import pathlib
import re
import sys

engine = pathlib.Path(sys.argv[1])
source = (engine / "engine.c").read_text()
entry = (engine / "main.c").read_text()
contract = (engine / "../../include/nurabrowser/contract.h").read_text()

for symbol in (
    "g_object_new(WEBKIT_TYPE_WEB_VIEW",
    "webkit_web_view_get_wpe_view",
    "g_main_loop_run",
    'g_signal_connect(engine.wpe_view, "closed"',
    '"web-process-terminated"',
    '"load-failed"',
    '"load-changed"',
    "WEBKIT_LOAD_FINISHED",
    "headless CI PASS",
    "headless CI deadline failed",
    "nurabrowser_nav_attach",
    "nurabrowser_nav_shutdown",
    "nurabrowser_control_start",
    "nurabrowser_control_stop",
    "WEBKIT_DISABLE_SANDBOX_THIS_IS_DANGEROUS",
):
    assert symbol in source, f"Missing engine API/lifecycle use: {symbol}"

for forbidden in (
    "webkit_web_view_backend_new", "wpe_loader_init(",
    "wpe_view_backend_", "webkit_web_view_run_javascript",
    "system(", "popen(", "execvp(", "fork(",
):
    assert forbidden not in source + entry, f"Forbidden API in engine: {forbidden}"

for symbol in ("typedef struct {", "nurabrowser_nav_attach", "nurabrowser_control_start"):
    assert symbol in contract, f"ABI mismatch: {symbol}"
print("PASS: static API and integration guards")
PY

if ! pkg-config --exists glib-2.0 gio-2.0; then
    echo "GATE: GLib/GIO development files unavailable (host option tests skipped)" >&2
    exit 77
fi

cc -std=c11 -Wall -Wextra -Werror -Wpedantic -O2 \
   -I"$engine" \
   "$here/test_options.c" "$engine/options.c" \
   $(pkg-config --cflags --libs glib-2.0 gio-2.0) \
   -o "$tmp/engine-option-tests"
"$tmp/engine-option-tests"

# This is a syntax gate, never an asserted successful crossbuild without
# real 2.54+ WPE headers. Worker D supplies Meson and an ARMHF link test.
if pkg-config --atleast-version=2.54 wpe-webkit-2.0 &&
   pkg-config --exists wpe-platform-2.0; then
    cc -std=c11 -Wall -Wextra -Wpedantic -fsyntax-only \
       -I"$engine" -I"$engine/../../include" \
       $(pkg-config --cflags glib-2.0 gio-2.0 wpe-webkit-2.0 wpe-platform-2.0) \
       "$engine/main.c" "$engine/engine.c" "$engine/options.c"
    echo "PASS: native WPE 2.54+ host-header syntax check (not an ARMHF link)"
else
    echo "GATE: WPE 2.54+ headers unavailable; real WPE compile/crosslink NOT verified"
fi
