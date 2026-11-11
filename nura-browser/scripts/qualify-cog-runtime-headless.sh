#!/bin/sh
# SPDX-License-Identifier: MIT
# SL101 .106: isolated native ARMHF WPEPlatform headless smoke.
# Execute as root with STAGE EXPECTED_CORE_SHA256. Never edits the Cog
# installation: a bind mount overlays /var/tmp in a PRIVATE mount namespace.
# No DRM, Wayland socket, GPU, compositor access, or sandbox bypass.
set -eu

root=/opt/sl101-cog-wpe-debian
webkit_hash=e198f5d4c9a7abe072545338780a0d99e5e7388c44a03760ce78be72af832c71
webp_hash=e1469642b7c28c1ababafcf49ac1874b4f27ce9f4693fbdc76410ef52b2a87e7
sharpyuv_hash=5f55ca48c13c2477dd5e3114a897dcdbafc9c0f2b662ad6b9101e6c8744be295
libc_hash=3c1f1b2519ed30dd35f7ff36aaca0729ca1abfa777f939c853ff0a61a2c5f709
loader_hash=6c97751a29d861ad32a919edb7e2ad8dcd425ec07278c2890683996c8d9a1702

fail() { printf 'nura-cog-headless: %s\n' "$*" >&2; exit 1; }
file_sha() { sha256sum "$1" | cut -d ' ' -f 1; }

if [ "${1:-}" = --inner ]; then
    # An accidental manual --inner invocation MUST NOT alter global mounts.
    [ "$(id -u)" -eq 0 ] || fail 'root required inside namespace'
    [ "$(readlink /proc/self/ns/mnt)" != "$(readlink /proc/1/ns/mnt)" ] ||
        fail 'refusing to run --inner in the host mount namespace'
    [ "$#" -eq 3 ] || fail 'internal argument count'
    stage=$2
    expected=$3
    [ "$(file_sha "$root/usr/lib/arm-linux-gnueabihf/libWPEWebKit-2.0.so.1")" = "$webkit_hash" ] ||
        fail 'unexpected WPE runtime'
    [ "$(file_sha "$stage/nurabrowser-core")" = "$expected" ] ||
        fail 'staged core changed'
    # This affects only the new namespace, never host mount propagation.
    mount --make-rprivate /
    mount --rbind "$root" "$root"
    # Only this mount namespace sees the stage as /var/tmp.
    mount --bind "$stage" "$root/var/tmp"
    cd "$root"
    [ -d .sl101-host-root ] || fail 'existing pivot-root placeholder missing'
    pivot_root . .sl101-host-root
    cd /
    umount -l /.sl101-host-root
    # WebKit sandbox remains ON. Software/HEADLESS; no DRM node or Wayland.
    exec /usr/bin/setpriv --reuid=1000 --regid=1000 --clear-groups \
        /usr/bin/env -i HOME=/home/browser USER=browser LOGNAME=browser \
        PATH=/usr/bin:/bin LANG=C.UTF-8 \
        XDG_RUNTIME_DIR=/run/user/1000 XDG_STATE_HOME=/var/tmp/state \
        WPE_PLATFORM=headless WEBKIT_SKIA_ENABLE_CPU_RENDERING=1 \
        WEBKIT_USE_SKIA_FOR_COMPOSITION=0 \
        LD_LIBRARY_PATH=/opt/sl101-webp-nosimd/lib \
        LIBGL_ALWAYS_SOFTWARE=1 GALLIUM_DRIVER=softpipe \
        MESA_LOADER_DRIVER_OVERRIDE=swrast \
        /usr/bin/dbus-run-session -- \
        /var/tmp/nurabrowser-core --platform=headless --no-control \
        --url=about:blank --exit-after-ms=7500
fi

preflight_only=0
if [ "${1:-}" = --preflight ]; then
    preflight_only=1
    shift
fi
[ "$#" -eq 2 ] || fail 'usage: sh qualify-cog-runtime-headless.sh [--preflight] STAGE CORE_SHA256'
if [ "$preflight_only" -eq 0 ]; then
    [ "$(id -u)" -eq 0 ] || fail 'root required (via sudo -n)'
fi
stage=$1
expected=$2
case "$stage" in
    /tmp/nurabrowser-smoke-[a-zA-Z0-9_-]*) ;;
    *) fail 'stage must be a private /tmp/nurabrowser-smoke-* directory' ;;
esac
[ "$(realpath "$stage")" = "$stage" ] || fail 'stage must be canonical'
case "$expected" in
    *[!0-9a-f]*|'') fail 'invalid SHA256' ;;
esac
[ "${#expected}" -eq 64 ] || fail 'invalid SHA256 length'
[ -d "$stage" ] && [ ! -L "$stage" ] || fail 'missing or symlinked stage'
[ "$(stat -c %u "$stage")" -eq 0 ] &&
[ "$(stat -c %a "$stage")" = 755 ] || fail 'stage must be root-owned 0755'
[ -f "$stage/nurabrowser-core" ] && [ ! -L "$stage/nurabrowser-core" ] ||
    fail 'missing or symlinked core'
[ -x "$stage/nurabrowser-core" ] || fail 'not executable'
[ "$(file_sha "$stage/nurabrowser-core")" = "$expected" ] ||
    fail 'staged core SHA256 mismatch'
[ -d "$stage/state" ] && [ ! -L "$stage/state" ] &&
[ "$(stat -c %u "$stage/state")" -eq 1000 ] &&
[ "$(stat -c %a "$stage/state")" = 700 ] ||
    fail 'state directory must be owned by browser UID 1000 and mode 0700'
[ -f "$root/var/lib/dpkg/status" ] &&
[ -d "$root/.sl101-host-root" ] || fail 'Cog private root incomplete'
grep -q '^Package: libwpewebkit-2.0-1$' "$root/var/lib/dpkg/status" ||
    fail 'WPE package missing'
grep -q '^Version: 2.54.0-2$' "$root/var/lib/dpkg/status" ||
    fail 'WPE version missing'
[ "$(file_sha "$root/usr/lib/arm-linux-gnueabihf/libWPEWebKit-2.0.so.1")" = "$webkit_hash" ] ||
    fail 'Cog WPE ELF hash mismatch'
[ "$(file_sha "$root/usr/lib/arm-linux-gnueabihf/libc.so.6")" = "$libc_hash" ] ||
    fail 'Cog libc6 ELF hash mismatch'
[ "$(file_sha "$root/usr/lib/arm-linux-gnueabihf/ld-linux-armhf.so.3")" = "$loader_hash" ] ||
    fail 'Cog glibc loader mismatch'
[ "$(file_sha "$root/opt/sl101-webp-nosimd/lib/libwebp.so.7")" = "$webp_hash" ] ||
    fail 'Cog no-SIMD WebP hash mismatch'
[ "$(file_sha "$root/opt/sl101-webp-nosimd/lib/libsharpyuv.so.0")" = "$sharpyuv_hash" ] ||
    fail 'Cog no-SIMD SharpYUV hash mismatch'
[ -x "$root/usr/bin/dbus-run-session" ] &&
[ -x "$root/usr/bin/bwrap" ] || fail 'sandbox prerequisites missing'
[ -d "$root/var/tmp" ] || fail 'private bind target missing'
case "${WEBKIT_DISABLE_SANDBOX_THIS_IS_DANGEROUS:-}" in
    '') ;;
    *) fail 'sandbox disable environment forbidden' ;;
esac
if [ "$preflight_only" -eq 1 ]; then
    printf 'nura-cog-headless: PASS read-only Cog/runtime/ELF preflight; no namespace or browser started\n'
    exit 0
fi
printf 'nura-cog-headless: verified Cog root and staged ELF, entering private namespace\n'
exec timeout -s TERM -k 5 30 \
    unshare --mount --fork --kill-child=SIGKILL \
    /bin/sh "$0" --inner "$stage" "$expected"
