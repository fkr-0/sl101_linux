#!/usr/bin/env bash
# Build the ARMv7 musl fixture using a configured cross compiler and target lib.
set -euo pipefail
if [[ $# != 3 ]]; then
    echo "usage: $0 CROSS_COMPILER TARGET_LIBWAYLAND_CLIENT OUTPUT_DIR" >&2
    exit 2
fi
compiler=$1
target_lib=$(realpath "$2")
mkdir -p "$3"
out=$(realpath "$3")
repo=$(cd "$(dirname "$0")/.." && pwd)
for header in wayland-client.h wayland-client-core.h wayland-client-protocol.h wayland-util.h wayland-version.h; do
    cp "/usr/include/$header" "$out/"
done
xml=/usr/share/wayland-protocols/stable/xdg-shell/xdg-shell.xml
wayland-scanner client-header "$xml" "$out/xdg-shell-client-protocol.h"
wayland-scanner private-code "$xml" "$out/xdg-shell-protocol.c"
"$compiler" -std=c11 -O2 -Wall -Wextra -Werror \
    -march=armv7-a -mfpu=vfpv3-d16 -mfloat-abi=hard \
    -I "$out" "$repo/tests/fixtures/sl101-visual/client.c" \
    "$out/xdg-shell-protocol.c" "$target_lib" -o "$out/sl101-visual-client"
