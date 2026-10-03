#!/bin/sh
# Run inside the existing ARMv7 Debian build environment, never on the tablet.
set -eu
archive=${1:?usage: sl101-webp-no-neon-build.sh ARCHIVE NEW_OUTPUT_DIRECTORY}
output=${2:?output directory required}
expected=e4ab7009bf0629fd11982d4c2aa83964cf244cffba7347ecd39019a9e38c4564
test "$(uname -m)" = armv7l
test "$(sha256sum "$archive" | cut -d' ' -f1)" = "$expected"
test ! -e "$output"
mkdir -p "$output"
output=$(realpath "$output")
tar xzf "$archive" -C "$output"
cd "$output/libwebp-1.6.0"
export CFLAGS='-O2 -march=armv7-a -mfpu=vfpv3-d16 -mfloat-abi=hard'
./configure --prefix=/opt/sl101-webp-no-neon --disable-neon \
    --disable-sse2 --disable-sse4.1 --disable-avx2 \
    --enable-shared --disable-static --disable-libwebpmux --disable-libwebpdemux
make -j4
make install DESTDIR="$output/install"
find "$output/install" -type f -name '*.so.*' -exec sha256sum {} \; > "$output/SHA256SUMS"
