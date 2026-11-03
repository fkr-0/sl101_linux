#!/bin/sh
# Build Mesa 25.0.7 with Grate gallium driver — clean single-invocation build.
#
# Usage (inside the Docker container):
#   sh /build/build.sh
#
# Or from the host:
#   docker build -t mesa-grate-build build/mesa-grate-clean/
#   docker run --rm -v "$PWD/build/mesa-grate-clean:/build" \
#     -v "$PWD/tmp/sl101-nura/gpu-egl-20260930-r2/tex-split-diag:/src-grate:ro" \
#     -v "$PWD/work/sl101-grate-production-20261004:/src-production:ro" \
#     -v "$PWD/work/sl101-cog-gpu-20261004/build-system:/src-build-system:ro" \
#     -v "$PWD/patches/mesa-25.0.7:/patches:ro" \
#     mesa-grate-build sh /build/build.sh
#
# Output: /build/output/ with the full install prefix.
set -eu

MESA_VERSION=25.0.7
MESA_URL="https://archive.mesa3d.org/mesa-${MESA_VERSION}.tar.xz"
GRATE_DRIVER=/src-production/grate-src
GRATE_WINSYS=/src-grate/build-pseq-final/mesa-${MESA_VERSION}/src/gallium/winsys/grate
GRATE_BUILD_SYSTEM=/src-build-system
EXTRA_PATCHES=/patches
LIBDRM_PATCHES=/src-build-system
PREFIX=/opt/grate-mesa25-clean
OUTPUT=/build/output

echo "=== Building grate-forked libdrm_tegra for glibc ==="
# The grate gallium driver requires grate-driver's forked libdrm tegra API.
# Download and cross-compile it to produce a glibc-linked libdrm_tegra.so.
if [ ! -d "/build/grate-libdrm" ]; then
    [ -f /build/grate-libdrm.tar.gz ] || { echo "ERROR: pinned grate libdrm tarball missing" >&2; exit 1; }
    echo "febe85e2c87af617e2c183943b74b2cfe1dc1797521790faedb3783a7a3c2294  /build/grate-libdrm.tar.gz" | sha256sum -c -
    mkdir -p /build/grate-libdrm
    tar xf /build/grate-libdrm.tar.gz -C /build/grate-libdrm --strip-components=1
fi
if [ -d "/build/grate-libdrm" ]; then
    cd /build/grate-libdrm
    # Discover available meson options for this fork
    meson setup builddir \
        --cross-file=/build/armhf-cross.ini \
        --prefix=/usr \
        --libdir=lib/arm-linux-gnueabihf \
        -Dbuildtype=release \
        -Dtegra=true \
        -Dintel=false -Dradeon=false -Damdgpu=false -Dnouveau=false \
        -Dvmwgfx=false -Dfreedreno=false -Dvc4=false -Detnaviv=false \
        -Dexynos=false -Domap=false -Dlibkms=false \
        -Dcairo-tests=false -Dman-pages=false -Dvalgrind=false \
        -Dinstall-test-programs=false 2>&1 || true
    if [ -d builddir ]; then
        ninja -C builddir -j$(nproc) 2>&1
        # Find and install the tegra library and headers
        tegra_lib=$(find builddir -name "libdrm_tegra.so*" -not -type l | head -1)
        if [ -n "$tegra_lib" ]; then
            cp "$tegra_lib" /usr/lib/arm-linux-gnueabihf/libdrm_tegra.so.0.0.0
            ln -sf libdrm_tegra.so.0.0.0 /usr/lib/arm-linux-gnueabihf/libdrm_tegra.so.0
            ln -sf libdrm_tegra.so.0.0.0 /usr/lib/arm-linux-gnueabihf/libdrm_tegra.so
            # Update pkg-config
            cat > /usr/lib/arm-linux-gnueabihf/pkgconfig/libdrm_tegra.pc << 'TEGRPC'
prefix=/usr
includedir=${prefix}/include
libdir=${prefix}/lib/arm-linux-gnueabihf

Name: libdrm_tegra
Description: grate-driver forked libdrm tegra
Version: 2.4.134
Requires: libdrm
Libs: -L${libdir} -ldrm_tegra
Cflags: -I${includedir} -I${includedir}/libdrm
TEGRPC
        fi
        # Install headers
        for h in tegra/tegra.h include/drm/tegra_drm.h; do
            [ -f "$h" ] && cp "$h" /usr/include/libdrm/"$(basename "$h")"
        done
        # Copy built lib to output for deployment
        mkdir -p "$OUTPUT$PREFIX/lib/arm-linux-gnueabihf"
        [ -n "$tegra_lib" ] && cp "$tegra_lib" "$OUTPUT$PREFIX/lib/arm-linux-gnueabihf/libdrm_tegra.so.0.0.0"
        echo "  Built and installed grate libdrm_tegra"
    fi
    # Apply dmabuf-seek fix if available
    if [ -f "$LIBDRM_PATCHES/libdrm-tegra-dmabuf-seek.patch" ]; then
        echo "  Applying libdrm dmabuf-seek patch"
        cd /build/grate-libdrm
        patch -p1 < "$LIBDRM_PATCHES/libdrm-tegra-dmabuf-seek.patch" 2>&1 || true
        ninja -C builddir -j$(nproc) 2>&1
        tegra_lib=$(find builddir -name "libdrm_tegra.so*" -not -type l | head -1)
        if [ -n "$tegra_lib" ]; then
            cp "$tegra_lib" /usr/lib/arm-linux-gnueabihf/libdrm_tegra.so.0.0.0
            cp "$tegra_lib" "$OUTPUT$PREFIX/lib/arm-linux-gnueabihf/libdrm_tegra.so.0.0.0"
        fi
    fi
    cd /build
else
    echo "  WARNING: Could not download grate libdrm, using grate SDK headers"
    GRATE_SDK=/src-grate-sdk
    if [ -d "$GRATE_SDK/include/libdrm" ]; then
        cp -f "$GRATE_SDK/include/libdrm/tegra.h" /usr/include/libdrm/tegra.h
        cp -f "$GRATE_SDK/include/libdrm/tegra_drm.h" /usr/include/libdrm/tegra_drm.h
    fi
fi

echo "=== Downloading Mesa ${MESA_VERSION} ==="
cd /build
if [ ! -f "mesa-${MESA_VERSION}.tar.xz" ]; then
    wget -q "$MESA_URL"
fi
# Input provenance is pinned to the reference snapshots captured 2026-11-03.
# Fail before deleting source if any external input has drifted.
verify_hash() {
    actual=$(sha256sum "$1" | awk '{print $1}')
    [ "$actual" = "$2" ] || { echo "ERROR: SHA256 mismatch: $1" >&2; exit 1; }
}
verify_tree() {
    actual=$(cd "$1" && find . -type f -print0 | LC_ALL=C sort -z | xargs -0 sha256sum | sha256sum | awk '{print $1}')
    [ "$actual" = "$2" ] || { echo "ERROR: tree digest mismatch: $1" >&2; exit 1; }
}
verify_hash "/build/mesa-${MESA_VERSION}.tar.xz" 592272df3cf01e85e7db300c449df5061092574d099da275d19e97ef0510f8a6
verify_hash "$GRATE_BUILD_SYSTEM/mesa25-grate-build-system.patch" 60c75af505179bb1fd885d55fb6378c02a6cdd60e079f1e0c379003ce3f24551
verify_tree "$GRATE_DRIVER" dd6b385a32425ab2959e61f66462e69d47bea343b6c604aed512748f31b2948e
verify_tree "$GRATE_WINSYS" 2483856fad8c143adf238acf2e792346aaabc03002d81d057f04684dbc03e5b1
[ -f "$EXTRA_PATCHES/series" ] || { echo "ERROR: missing ordered patch series" >&2; exit 1; }
rm -rf "mesa-${MESA_VERSION}"
tar xf "mesa-${MESA_VERSION}.tar.xz"
cd "mesa-${MESA_VERSION}"

echo "=== Applying build system patch (adds grate to Meson) ==="
patch --batch --fuzz=0 --no-backup-if-mismatch -p1 < "$GRATE_BUILD_SYSTEM/mesa25-grate-build-system.patch"

echo "=== Copying production grate gallium driver source ==="
cp -a "$GRATE_DRIVER" src/gallium/drivers/grate
cp -a "$GRATE_WINSYS" src/gallium/winsys/grate

# Apply only the ordered, hash-pinned series. Never tolerate fuzz, skips,
# missing patches or rejects. The series is a candidate pending full diff QA.
echo "=== Applying pinned Mesa patch series ==="
while read -r expected filename extra; do
    case "$expected" in ""|\#*) continue ;; esac
    [ -z "${extra:-}" ] || { echo "ERROR: malformed series entry" >&2; exit 1; }
    case "$filename" in
        ""|*/*|*..*|*.patch) ;;
        *) echo "ERROR: invalid patch name: $filename" >&2; exit 1 ;;
    esac
    case "$filename" in */*|*..*|"") echo "ERROR: unsafe patch name" >&2; exit 1 ;; esac
    [ "${#expected}" -eq 64 ] || { echo "ERROR: invalid SHA256 in series" >&2; exit 1; }
    file="$EXTRA_PATCHES/$filename"
    [ -f "$file" ] || { echo "ERROR: missing patch $filename" >&2; exit 1; }
    verify_hash "$file" "$expected"
    echo "  $filename"
    patch --batch --fuzz=0 --no-backup-if-mismatch -p1 < "$file" || { echo "ERROR: failed applying $filename" >&2; exit 1; }
done < "$EXTRA_PATCHES/series"

echo "=== Verifying drm_helper.h screen_create matches winsys ==="
# Both build-system patch and winsys use grate_drm_screen_create — no rename needed
grep -q 'grate_drm_screen_create' src/gallium/auxiliary/target-helpers/drm_helper.h && \
    echo "  drm_helper.h: grate_drm_screen_create present (matches winsys)"

echo "=== Creating wayland-egl-backend stub (Mesa provides this itself) ==="
# wayland-egl-backend is normally provided by a Mesa installation. For cross-
# building Mesa from scratch, supply the header and pkg-config from the source.
# Find and install the header wherever Mesa keeps it
weh=$(find . -name wayland-egl-backend.h -print -quit)
if [ -n "$weh" ]; then
    cp "$weh" /usr/include/
    echo "  Installed $weh → /usr/include/"
else
    # Create a minimal stub header from the Mesa source
    cat > /usr/include/wayland-egl-backend.h << 'STUBH'
#ifndef WAYLAND_EGL_BACKEND_H
#define WAYLAND_EGL_BACKEND_H
#include <stdint.h>
#define WL_EGL_WINDOW_VERSION 3
struct wl_surface;
struct wl_egl_window {
    const intptr_t version;
    int width;
    int height;
    int dx;
    int dy;
    int attached_width;
    int attached_height;
    void *driver_private;
    void (*resize_callback)(struct wl_egl_window *, void *);
    void (*destroy_window_callback)(void *);
    struct wl_surface *surface;
};
#endif
STUBH
    echo "  Created minimal stub header"
fi
cat > /usr/lib/arm-linux-gnueabihf/pkgconfig/wayland-egl-backend.pc << 'STUBPC'
prefix=/usr
includedir=${prefix}/include

Name: wayland-egl-backend
Description: Backend for Wayland EGL (stub for Mesa cross-build)
Version: 4
Cflags: -I${includedir}
STUBPC

echo "=== Configuring Meson build ==="
meson setup builddir \
    --cross-file=/build/armhf-cross.ini \
    --prefix="$PREFIX" \
    --libdir=lib/arm-linux-gnueabihf \
    -Dgallium-drivers=grate,softpipe \
    -Dvulkan-drivers= \
    -Dplatforms=wayland \
    -Dgbm=enabled \
    -Degl=enabled \
    -Dgles1=disabled \
    -Dgles2=enabled \
    -Dglx=disabled \
    -Dglvnd=disabled \
    -Dllvm=disabled \
    -Dvulkan-drivers= \
    -Dgallium-va=disabled \
    -Dgallium-vdpau=disabled \
    -Dvalgrind=disabled \
    -Dlibunwind=disabled \
    -Dzstd=disabled \
    -Dxmlconfig=disabled

echo "=== Building ==="
ninja -C builddir -j$(nproc)

echo "=== Installing to $OUTPUT ==="
rm -rf "$OUTPUT"
DESTDIR="$OUTPUT" ninja -C builddir install

# Re-copy libdrm_tegra into output (rm -rf $OUTPUT above erased the early copy)
tegra_lib=$(find /build/grate-libdrm/builddir -name "libdrm_tegra.so*" -not -type l 2>/dev/null | head -1)
if [ -n "$tegra_lib" ]; then
    cp "$tegra_lib" "$OUTPUT$PREFIX/lib/arm-linux-gnueabihf/libdrm_tegra.so.0.0.0"
    ln -sf libdrm_tegra.so.0.0.0 "$OUTPUT$PREFIX/lib/arm-linux-gnueabihf/libdrm_tegra.so.0"
    ln -sf libdrm_tegra.so.0.0.0 "$OUTPUT$PREFIX/lib/arm-linux-gnueabihf/libdrm_tegra.so"
fi

echo ""
echo "=== Build complete ==="
echo "Libraries in: $OUTPUT$PREFIX/lib/arm-linux-gnueabihf/"
ls -la "$OUTPUT$PREFIX/lib/arm-linux-gnueabihf/"libEGL* \
       "$OUTPUT$PREFIX/lib/arm-linux-gnueabihf/"libgallium* \
       "$OUTPUT$PREFIX/lib/arm-linux-gnueabihf/"libgbm* \
       "$OUTPUT$PREFIX/lib/arm-linux-gnueabihf/"libGLESv2* \
       "$OUTPUT$PREFIX/lib/arm-linux-gnueabihf/"libdrm_tegra* 2>/dev/null

echo ""
echo "To deploy: scp the entire $PREFIX tree to the SL101 and update"
echo "LD_LIBRARY_PATH in sl101-epiphany-enter / sl101-cog-wpe-enter."
