#!/usr/bin/env bash
# Cross-build the *matched* Mesa 25.0.7 Grate/EGL/GLES/GBM set for the Alpine
# armv7 hard-float musl host. No SL101 SSH access, rootfs changes or deployment.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="${SL101_MUSL_WORK:-$REPO/work/sl101-grate-musl-20261106}"
SYSROOT="${SL101_MUSL_SYSROOT:-/tmp/sl101-mesa-musl-20261106/sysroot}"
TOOLCHAIN="${SL101_MUSL_TOOLCHAIN:-/tmp/arm-linux-musleabihf-cross/bin}"
MESA="${SL101_MUSL_SOURCE:-$REPO/build/mesa-grate-clean/mesa-25.0.7}"
FORK="$REPO/build/mesa-grate-clean/grate-libdrm"
PREFIX="${SL101_MUSL_PREFIX:-/opt/grate-mesa25-musl-20261106}"
CROSS="$WORK/armv7-musl-cross.ini"
JOBS="${SL101_MUSL_JOBS:-2}"
PHASE="${1:-all}"

die() { echo "ERROR: $*" >&2; exit 1; }
# Fail closed: below we rm an owned builddir and mount/chown the temporary SDK.
# Never allow environment overrides to redirect either operation into a live
# rootfs or an unrelated workspace.
case "$(realpath -m "$WORK")" in "$REPO"/work/sl101-grate-musl-*) ;; *) die "unsafe work directory $WORK" ;; esac
case "$(realpath -m "$SYSROOT")" in /tmp/sl101-mesa-musl-*/sysroot) ;; *) die "unsafe sysroot $SYSROOT" ;; esac
case "$PREFIX" in /opt/grate-mesa25-musl-*) ;; *) die "unsafe install prefix $PREFIX" ;; esac
[ -f "$MESA/meson.build" ] || die "missing pinned patched Mesa source $MESA"
[ -f "$FORK/meson.build" ] || die "missing grate libdrm source"
grep -q 'server advertised no formats but render node' "$MESA/src/egl/drivers/dri2/platform_wayland.c" || die "Cog nested Wayland EGL format fallback missing"
grep -q 'dri_screen_render_gpu or its pipe_screen is NULL' "$MESA/src/egl/drivers/dri2/egl_dri2.c" || die "Mesa EGL DRI screen guard missing"
[ -x "$TOOLCHAIN/arm-linux-musleabihf-gcc" ] || die "missing musl ARM cross-compiler"
mkdir -p "$WORK" "$SYSROOT" "$WORK/output"

if [ ! -f "$SYSROOT/usr/lib/pkgconfig/libdrm.pc" ]; then
    command -v docker >/dev/null || die "docker needed to provision Alpine armv7 SDK"
    docker run --rm --platform linux/arm/v7 -v "$SYSROOT:/sysroot" alpine:3.20 sh -ec '
        apk add --no-cache libdrm-dev wayland-dev expat-dev zlib-dev elfutils-dev libffi-dev libstdc++ wayland-protocols
        mkdir -p /sysroot/usr
        cp -a /usr/include /usr/lib /usr/share /sysroot/usr/
        cp -a /lib /sysroot/
    '
fi
# Alpine images run as root, but all subsequent builds/installations must be
# writable by this non-root host account (never chmod system directories).
if [ ! -w "$SYSROOT/usr" ]; then
    docker run --rm -v "$SYSROOT:/sysroot" alpine:3.20 \
        chown -R "$(id -u):$(id -g)" /sysroot
fi

# The protocol XML is a build-time data dependency, not a target library.
# Existing SDK snapshots might predate its installation.
if [ ! -d "$SYSROOT/usr/share/wayland-protocols" ] && [ -d /usr/share/wayland-protocols ]; then
    mkdir -p "$SYSROOT/usr/share"
    cp -a /usr/share/wayland-protocols "$SYSROOT/usr/share/"
fi
if [ ! -f "$SYSROOT/usr/share/pkgconfig/wayland-protocols.pc" ] && [ -f /usr/share/pkgconfig/wayland-protocols.pc ]; then
    mkdir -p "$SYSROOT/usr/share/pkgconfig"
    cp /usr/share/pkgconfig/wayland-protocols.pc "$SYSROOT/usr/share/pkgconfig/"
fi

cat > "$CROSS" <<EOF
[binaries]
c = '$TOOLCHAIN/arm-linux-musleabihf-gcc'
cpp = '$TOOLCHAIN/arm-linux-musleabihf-g++'
ar = '$TOOLCHAIN/arm-linux-musleabihf-ar'
strip = '$TOOLCHAIN/arm-linux-musleabihf-strip'
readelf = '$TOOLCHAIN/arm-linux-musleabihf-readelf'
pkg-config = 'pkg-config'
[built-in options]
c_args = ['-march=armv7-a','-mfpu=vfpv3-d16','-mfloat-abi=hard','-DNO_FORMAT_ASM','-isystem','$SYSROOT/usr/include']
cpp_args = ['-march=armv7-a','-mfpu=vfpv3-d16','-mfloat-abi=hard','-DNO_FORMAT_ASM','-isystem','$SYSROOT/usr/include']
c_link_args = ['-march=armv7-a','-mfpu=vfpv3-d16','-mfloat-abi=hard','-L$SYSROOT/usr/lib']
cpp_link_args = ['-march=armv7-a','-mfpu=vfpv3-d16','-mfloat-abi=hard','-L$SYSROOT/usr/lib']
[properties]
needs_exe_wrapper = true
sys_root = '$SYSROOT'
pkg_config_libdir = ['$SYSROOT/usr/lib/pkgconfig','$SYSROOT/usr/share/pkgconfig']
[host_machine]
system = 'linux'
cpu_family = 'arm'
cpu = 'armv7a'
endian = 'little'
EOF
export PKG_CONFIG_SYSROOT_DIR="$SYSROOT"
export PKG_CONFIG_LIBDIR="$SYSROOT/usr/lib/pkgconfig:$SYSROOT/usr/share/pkgconfig"
# Mesa asks the native wayland-scanner.pc for its executable, but pkg-config
# sysroot-rewrites the path. Expose only the host *build tool* there; never
# attempt to run an ARM target wayland-scanner via QEMU during cross-building.
command -v wayland-scanner >/dev/null || die "missing native wayland-scanner"
mkdir -p "$SYSROOT/usr/bin"
ln -sfn "$(command -v wayland-scanner)" "$SYSROOT/usr/bin/wayland-scanner"

build_fork() {
    echo "== Build forked libdrm (musl) =="
    mkdir -p "$WORK/libdrm-src"
    if [ ! -f "$WORK/libdrm-src/meson.build" ]; then
        (cd "$FORK" && tar --exclude=builddir -cf - .) | (cd "$WORK/libdrm-src" && tar xf -)
    fi
    local patch="$REPO/work/sl101-cog-gpu-20261004/build-system/libdrm-tegra-dmabuf-seek.patch"
    [ -f "$patch" ] || die "missing Grate dmabuf-seek patch $patch"
    if [ -f "$patch" ]; then
        if grep -Fq 'lseek(fd, 0, SEEK_SET);' "$WORK/libdrm-src/tegra/tegra.c"; then
            echo "libdrm dmabuf-seek patch already present"
        else
            (cd "$WORK/libdrm-src" && patch --batch --forward --fuzz=0 -p1 < "$patch") || die "cannot apply libdrm dmabuf-seek patch"
        fi
        grep -Fq 'lseek(fd, 0, SEEK_SET);' "$WORK/libdrm-src/tegra/tegra.c" || die "missing dmabuf seek fix"
    fi
    if [ ! -f "$WORK/libdrm-build/build.ninja" ]; then
        meson setup "$WORK/libdrm-build" "$WORK/libdrm-src" --wrap-mode=nodownload \
            --cross-file="$CROSS" --prefix=/usr --libdir=lib -Dbuildtype=release \
            -Dtegra=true -Dintel=false -Dradeon=false -Damdgpu=false \
            -Dnouveau=false -Dvmwgfx=false -Dfreedreno=false -Dvc4=false \
            -Detnaviv=false -Dexynos=false -Domap=false -Dlibkms=false \
            -Dcairo-tests=false -Dman-pages=false -Dvalgrind=false \
            -Dinstall-test-programs=false
    fi
    ninja -C "$WORK/libdrm-build" -j "$JOBS"
    DESTDIR="$SYSROOT" ninja -C "$WORK/libdrm-build" install
    # Grate's Gallium driver includes these fork-specific headers.
    mkdir -p "$SYSROOT/usr/include/libdrm"
    cp "$WORK/libdrm-src/tegra/tegra.h" "$SYSROOT/usr/include/libdrm/tegra.h"
    cp "$WORK/libdrm-src/include/drm/tegra_drm.h" "$SYSROOT/usr/include/libdrm/tegra_drm.h"
    # This historical Grate fork declares libdrm 2.4.97, below Mesa 25.0.7's
    # >=2.4.109 requirement. Only its Tegra extension is consumed; restore
    # Alpine's ABI-qualified core libdrm 2.4.120 and matching headers/.pc.
    # Never lie about libdrm's version in a hand-edited pkg-config file.
    docker run --rm --platform linux/arm/v7 -v "$SYSROOT:/sysroot" \
        -e HOST_UID="$(id -u)" -e HOST_GID="$(id -g)" alpine:3.20 sh -ec '
        apk add --no-cache libdrm-dev
        cp -a /usr/lib/libdrm.so* /sysroot/usr/lib/
        cp /usr/lib/pkgconfig/libdrm.pc /sysroot/usr/lib/pkgconfig/libdrm.pc
        cp /usr/include/xf86drm.h /usr/include/xf86drmMode.h /sysroot/usr/include/
        cp -a /usr/include/libdrm/. /sysroot/usr/include/libdrm/
        chown -R "$HOST_UID:$HOST_GID" /sysroot
    '
    # The distro tegra.h is not the private Grate fork interface.
    cp "$WORK/libdrm-src/tegra/tegra.h" "$SYSROOT/usr/include/libdrm/tegra.h"
    cp "$WORK/libdrm-src/include/drm/tegra_drm.h" "$SYSROOT/usr/include/libdrm/tegra_drm.h"
    pkg-config --atleast-version=2.4.109 libdrm || die "core libdrm too old"
}

build_mesa() {
    echo "== Configure and build Mesa 25.0.7 + Grate musl =="
    [ -f "$SYSROOT/usr/lib/libdrm_tegra.so" ] || die "forked musl libdrm_tegra missing"
    if [ -d "$WORK/mesa-build" ] && [ ! -f "$WORK/mesa-build/build.ninja" ]; then
        # A previous failed Meson configure has no usable build.ninja.
        rm -rf "$WORK/mesa-build"
    fi
    if [ ! -f "$WORK/mesa-build/build.ninja" ]; then
        meson setup "$WORK/mesa-build" "$MESA" --wrap-mode=nodownload \
            --cross-file="$CROSS" --prefix="$PREFIX" --libdir=lib \
            -Dbuildtype=release -Dgallium-drivers=grate,softpipe \
            -Dvulkan-drivers= -Dplatforms=wayland -Dgbm=enabled \
            -Degl=enabled -Dgles1=disabled -Dgles2=enabled \
            -Dglx=disabled -Dglvnd=disabled -Dllvm=disabled \
            -Dgallium-va=disabled -Dgallium-vdpau=disabled \
            -Dvalgrind=disabled -Dlibunwind=disabled -Dzstd=disabled \
            -Dxmlconfig=disabled
    fi
    ninja -C "$WORK/mesa-build" -j "$JOBS"
    DESTDIR="$WORK/output" ninja -C "$WORK/mesa-build" install
    mkdir -p "$WORK/output$PREFIX/lib"
    # Install the same fork's *musl-linked* libdrm.so and libdrm_tegra.so.
    for file in "$SYSROOT"/usr/lib/libdrm.so* "$SYSROOT"/usr/lib/libdrm_tegra.so*; do
        [ -e "$file" ] || continue
        cp -a "$file" "$WORK/output$PREFIX/lib/"
    done
}

audit() {
    echo "== Reject glibc and audit ARM hardfloat set =="
    local dir="$WORK/output$PREFIX/lib"
    for name in libEGL.so.1.0.0 libGLESv2.so.2.0.0 libgbm.so.1.0.0 libgallium-25.0.7.so libdrm_tegra.so.0; do
        [ -e "$dir/$name" ] || die "missing $dir/$name"
        file -L "$dir/$name"
        readelf -d "$dir/$name" | grep NEEDED || true
        if readelf -d "$dir/$name" | grep -Eq 'libc\.so\.6|ld-linux|GLIBC_'; then
            die "glibc contamination in $name"
        fi
        readelf -A "$dir/$name" | grep -E 'Tag_CPU_arch:|Tag_FP_arch:|Tag_ABI_VFP_args:' || true
    done
    (cd "$WORK/output" && tar -czf "$WORK/grate-mesa25-musl-20261106.tar.gz" ".$PREFIX")
    sha256sum "$WORK/grate-mesa25-musl-20261106.tar.gz" | tee "$WORK/grate-mesa25-musl-20261106.sha256"
}

case "$PHASE" in
    fork) build_fork ;;
    mesa) build_mesa ;;
    audit) audit ;;
    all) build_fork; build_mesa; audit ;;
    *) die "usage: $0 [all|fork|mesa|audit]" ;;
esac
