#!/bin/sh
# Installed exclusively as ,browse inside a separately prepared private glibc
# Debian armhf browser root. No chroot, deployment, mounts or device mutation.
set -eu
export LC_ALL=C

fail() { printf 'NuraBrowser: %s\n' "$*" >&2; exit 1; }
usage() {
    printf 'Usage: ,browse [--renderer software|grate] [--platform headless|wayland|drm] [--url https://host/]\n'
}

renderer=software
platform=headless
url=https://example.org/
while [ "$#" -gt 0 ]; do
    case "$1" in
        --help|-h) usage; exit 0 ;;
        --renderer)
            [ "$#" -ge 2 ] || fail '--renderer needs a value'
            renderer=$2; shift 2 ;;
        --renderer=*) renderer=${1#*=}; shift ;;
        --platform)
            [ "$#" -ge 2 ] || fail '--platform needs a value'
            platform=$2; shift 2 ;;
        --platform=*) platform=${1#*=}; shift ;;
        --url)
            [ "$#" -ge 2 ] || fail '--url needs a value'
            url=$2; shift 2 ;;
        --url=*) url=${1#*=}; shift ;;
        --*) fail "unknown option: $1" ;;
        *) fail 'positional arguments are forbidden; use --url' ;;
    esac
done

case "$renderer" in software|grate) ;; *) fail "invalid renderer: $renderer" ;; esac
case "$platform" in headless|wayland|drm) ;; *) fail "invalid platform: $platform" ;; esac
# A URL is an argument to our native engine, never a command or option.
# Reject controls, whitespace, and URLs without an absolute http(s) origin.
# grep operates line-wise; reject embedded newlines before the regexp gate.
case "$url" in
    *[[:space:][:cntrl:]]*) fail 'URL must be an absolute whitespace-free http(s) URL' ;;
esac
if ! printf '%s\n' "$url" | grep -Eq '^https?://[^[:space:][:cntrl:]]+$'; then
    fail 'URL must be an absolute whitespace-free http(s) URL'
fi
case "${WEBKIT_DISABLE_SANDBOX_THIS_IS_DANGEROUS:-}" in
    '') ;; *) fail 'WebKit sandbox disable is forbidden' ;;
esac
case "${WEBKIT_USE_SANDBOX:-}" in
    ''|1) ;; *) fail 'WebKit sandbox must remain enabled' ;;
esac

# Fail closed if invoked against the host root or an arbitrary chroot.
[ "${NURABROWSER_PRIVATE_ROOT:-}" = / ] ||
    fail 'not inside the prepared private browser root (NURABROWSER_PRIVATE_ROOT=/ required)'
marker=/etc/nura-browser/private-root-id
[ -r "$marker" ] || fail "private root marker missing: $marker"
[ "$(cat "$marker")" = SL101-NURABROWSER-GLIBC-ARMHF-2.54.0-2 ] ||
    fail 'private root marker mismatch'
status=/var/lib/dpkg/status
[ -r "$status" ] || fail 'Debian dpkg status missing'
expected=${NURABROWSER_EXPECTED_STATUS_SHA256:-}
case "$expected" in
    *[!0-9a-f]*|'') fail 'expected dpkg status SHA256 required (64 lowercase hex)' ;;
esac
[ "${#expected}" -eq 64 ] || fail 'expected dpkg status SHA256 must be 64 characters'
command -v sha256sum >/dev/null 2>&1 || fail 'sha256sum missing'
actual=$(sha256sum "$status") || fail 'cannot hash private root status'
[ "${actual%% *}" = "$expected" ] || fail 'private root status hash mismatch'
# Debian armhf status verification: do not mistake an unpacked or stale package
# for the precisely archived WPE WebKit 2.54.0-2 engine.
awk '
  BEGIN { RS=""; FS="\n"; ok=0 }
  {
    p=""; v=""; a=""; s=""
    for (i=1;i<=NF;i++) {
      if ($i ~ /^Package: /) p=substr($i,10)
      if ($i ~ /^Version: /) v=substr($i,10)
      if ($i ~ /^Architecture: /) a=substr($i,15)
      if ($i ~ /^Status: /) s=substr($i,9)
    }
    if (p=="libwpewebkit-2.0-1" && v=="2.54.0-2" &&
        a=="armhf" && s=="install ok installed") ok=1
  }
  END { exit(ok ? 0 : 1) }
' "$status" || fail 'pinned Debian ARMHF WPE runtime not installed'

command -v bwrap >/dev/null 2>&1 || fail 'bubblewrap missing (sandbox mandatory)'
command -v xdg-dbus-proxy >/dev/null 2>&1 || fail 'xdg-dbus-proxy missing (sandbox mandatory)'
command -v readelf >/dev/null 2>&1 || fail 'readelf missing for ELF ABI gate'
core=/usr/libexec/nura-browser/nurabrowser-core
wpe=/usr/lib/arm-linux-gnueabihf/libWPEWebKit-2.0.so.1
[ -x "$core" ] || fail "native engine missing: $core"
[ -r "$wpe" ] || fail "WPE runtime missing: $wpe"
for binary in "$core" "$wpe"; do
    readelf -h "$binary" | grep -Eq 'Machine:[[:space:]]*ARM' ||
        fail "non-ARM ELF: $binary"
    readelf -h "$binary" | grep -q 'hard-float ABI' ||
        fail "non-ARMHF ELF: $binary"
    readelf -A "$binary" | grep -Eq 'Tag_CPU_arch: v7' ||
        fail "non-ARMv7 ELF: $binary"
    readelf -A "$binary" | grep -q 'Tag_FP_arch: VFPv3-D16' ||
        fail "non-VFPv3-D16 ELF: $binary"
    if readelf -A "$binary" | grep -q 'Tag_Advanced_SIMD_arch:'; then
        fail "NEON attribute forbidden: $binary"
    fi
done

case "$platform" in
    headless) ;;
    wayland)
        [ -n "${XDG_RUNTIME_DIR:-}" ] && [ -n "${WAYLAND_DISPLAY:-}" ] ||
            fail 'Wayland requires XDG_RUNTIME_DIR and WAYLAND_DISPLAY'
        case "$WAYLAND_DISPLAY" in
            /*) wayland_socket=$WAYLAND_DISPLAY ;;
            */*) fail 'WAYLAND_DISPLAY must be basename or absolute path' ;;
            *) wayland_socket=$XDG_RUNTIME_DIR/$WAYLAND_DISPLAY ;;
        esac
        [ -S "$wayland_socket" ] || fail 'Wayland socket missing' ;;
    drm)
        [ "${NURABROWSER_ALLOW_DRM:-}" = 1 ] ||
            fail 'DRM requires explicit NURABROWSER_ALLOW_DRM=1 gate'
        [ -c /dev/dri/card0 ] || fail 'DRM card device missing' ;;
esac
export WPE_PLATFORM=$platform

case "$renderer" in
    software)
        export LIBGL_ALWAYS_SOFTWARE=1 GALLIUM_DRIVER=softpipe
        export MESA_LOADER_DRIVER_OVERRIDE=swrast
        unset LIBGL_DRIVERS_PATH GBM_BACKENDS_PATH LD_LIBRARY_PATH || true ;;
    grate)
        overlay=/opt/nura-browser/grate
        [ -d "$overlay/usr/lib/arm-linux-gnueabihf/dri" ] ||
            fail 'private pinned Grate overlay missing'
        actual_overlay=$(sha256sum "$overlay/.sl101-overlay-sha256" 2>/dev/null) ||
            fail 'Grate overlay integrity receipt missing'
        expected_overlay=${NURABROWSER_EXPECTED_OVERLAY_SHA256:-}
        case "$expected_overlay" in
            *[!0-9a-f]*|'') fail 'pinned Grate overlay receipt hash required' ;;
        esac
        [ "${#expected_overlay}" -eq 64 ] && [ "${actual_overlay%% *}" = "$expected_overlay" ] ||
            fail 'Grate overlay integrity receipt mismatch'
        lib=$overlay/usr/lib/arm-linux-gnueabihf
        export LD_LIBRARY_PATH=$lib:$lib/dri:$lib/gbm
        export LIBGL_DRIVERS_PATH=$lib/dri GBM_BACKENDS_PATH=$lib/gbm
        export MESA_LOADER_DRIVER_OVERRIDE=grate
        unset LIBGL_ALWAYS_SOFTWARE GALLIUM_DRIVER || true ;;
esac

exec "$core" --url "$url"
