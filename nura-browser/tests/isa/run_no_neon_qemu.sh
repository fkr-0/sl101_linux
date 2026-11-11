#!/bin/sh
# SPDX-License-Identifier: MIT
# Offline ARMHF QEMU probe, deliberately fail-closed and network-isolated.
# Requires the already prepared WPE 2.54.0-2 development Docker image.
set -eu
root=$(CDPATH='' cd -- "$(dirname -- "$0")/../../.." && pwd)
image=sl101-nurabrowser-wpe-dev:2.54.0-2
expected=sha256:5d7f46c14a1667aa77a7bc17fcbef9e0910e15fa6dd360540dfebdcb33553a17
command -v docker >/dev/null 2>&1 || {
    echo 'Required: docker' >&2; exit 2;
}
actual=$(docker image inspect --format '{{.Id}}' "$image") || {
    echo 'Required: prepared pinned Debian WPE 2.54.0-2 build image' >&2
    exit 2
}
[ "$actual" = "$expected" ] || {
    echo "Refusing unexpected Docker image identity: $actual" >&2
    exit 2
}
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT HUP INT TERM

docker run --rm --network none --user "$(id -u):$(id -g)" \
    -v "$root/nura-browser/tests/isa:/src:ro" \
    -v "$tmp:/out" \
    --entrypoint sh "$image" -ec '
        arm-linux-gnueabihf-gcc -std=c11 -O0 -Wall -Wextra -Werror \
            -march=armv7-a -mfpu=vfpv3-d16 -mfloat-abi=hard \
            /src/probe_tegra2_no_neon.c -ldl -lm -o /out/isa-probe
        qemu-arm -cpu cortex-a9,neon=off,vfp-d32=off -L / /out/isa-probe
    '
