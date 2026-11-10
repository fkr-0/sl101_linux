#!/bin/sh
# Offline, non-deploying build against EXACT prepared Debian 2.54.0-2 sysroot.
set -eu
if [ "$#" -ne 2 ]; then
    echo 'Usage: build-armhf.sh ABSOLUTE_PREPARED_ARMHF_SYSROOT ABSOLUTE_BUILD_DIR' >&2
    exit 2
fi
sysroot=$(realpath -e "$1")
builddir=$2
case "$sysroot" in /*) ;; *) echo 'sysroot must be absolute' >&2; exit 2 ;; esac
case "$builddir" in /*) ;; *) echo 'builddir must be absolute' >&2; exit 2 ;; esac
project=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)

# First qualify headers and compiler; no fake success if either is unavailable.
export PKG_CONFIG_LIBDIR=$sysroot/usr/lib/arm-linux-gnueabihf/pkgconfig:$sysroot/usr/share/pkgconfig
export PKG_CONFIG_SYSROOT_DIR=$sysroot
export PKG_CONFIG_PATH=
python3 "$project/scripts/qualify.py" --mode armhf --sysroot "$sysroot"

export CFLAGS="--sysroot=$sysroot -march=armv7-a -mfpu=vfpv3-d16 -mfloat-abi=hard -fno-tree-vectorize"
export LDFLAGS="--sysroot=$sysroot -march=armv7-a -mfpu=vfpv3-d16 -mfloat-abi=hard"
meson setup "$builddir" "$project" \
    --cross-file "$project/packaging/armhf-gnueabihf.ini" \
    --prefix=/usr -Dlibexecdir=libexec -Darmhf_qualification=true
meson compile -C "$builddir"
# Cross target is never run on the host. Static audit is necessary, not enough.
python3 "$project/scripts/qualify.py" --mode armhf --sysroot "$sysroot" \
    --elf "$builddir/nurabrowser-core"
