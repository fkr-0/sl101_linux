#!/bin/sh
# Minimal WPEPlatform-native reference launcher for use inside the prepared
# Debian armhf private browser root. It performs no mounts, deployment or SSH.
set -eu

MINIBROWSER=${SL101_WPE_MINIBROWSER:-/usr/lib/arm-linux-gnueabihf/wpe-webkit-2.0/MiniBrowser}
RENDERER=${SL101_WPE_RENDERER:-software}
GRATE_ROOT=${SL101_WPE_GRATE_ROOT:-/opt/grate-glibc}
URL=${1:-https://example.org/}

[ -x "$MINIBROWSER" ] || {
    echo "missing WPE 2.54 MiniBrowser: $MINIBROWSER" >&2
    exit 1
}
command -v bwrap >/dev/null 2>&1 || {
    echo "bubblewrap is required; refusing unsandboxed launch" >&2
    exit 1
}
command -v xdg-dbus-proxy >/dev/null 2>&1 || {
    echo "xdg-dbus-proxy is required; refusing weakened sandbox launch" >&2
    exit 1
}

case "${WEBKIT_DISABLE_SANDBOX_THIS_IS_DANGEROUS:-0}" in
    0|"") ;;
    *) echo "sandbox-disable environment is forbidden" >&2; exit 2 ;;
esac

: "${XDG_RUNTIME_DIR:=/run/user/1000}"
: "${WAYLAND_DISPLAY:=wayland-0}"
export XDG_RUNTIME_DIR WAYLAND_DISPLAY
[ -S "$XDG_RUNTIME_DIR/$WAYLAND_DISPLAY" ] || {
    echo "Wayland socket missing: $XDG_RUNTIME_DIR/$WAYLAND_DISPLAY" >&2
    exit 1
}

# WPE 2.54 uses Skia by default. Keep that default unless an explicit
# qualification comparison requests the compatibility setting.
case "${SL101_WPE_SKIA_COMPOSITION:-default}" in
    default) unset WEBKIT_USE_SKIA_FOR_COMPOSITION || true ;;
    1|on) export WEBKIT_USE_SKIA_FOR_COMPOSITION=1 ;;
    0|off) export WEBKIT_USE_SKIA_FOR_COMPOSITION=0 ;;
    *) echo "SL101_WPE_SKIA_COMPOSITION must be default, on/1 or off/0" >&2; exit 2 ;;
esac

case "$RENDERER" in
    software)
        export LIBGL_ALWAYS_SOFTWARE=1
        export GALLIUM_DRIVER=softpipe
        export MESA_LOADER_DRIVER_OVERRIDE=swrast
        unset LIBGL_DRIVERS_PATH GBM_BACKENDS_PATH || true
        ;;
    grate)
        lib="$GRATE_ROOT/usr/lib/arm-linux-gnueabihf"
        [ -r "$GRATE_ROOT/.sl101-overlay-sha256" ] || {
            echo "missing reviewed Grate overlay receipt" >&2
            exit 1
        }
        [ -d "$lib/dri" ] || { echo "missing private Grate DRI tree" >&2; exit 1; }
        export LD_LIBRARY_PATH="$lib:$lib/dri:$lib/gbm${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
        export LIBGL_DRIVERS_PATH="$lib/dri"
        export GBM_BACKENDS_PATH="$lib/gbm"
        export MESA_LOADER_DRIVER_OVERRIDE=grate
        unset LIBGL_ALWAYS_SOFTWARE GALLIUM_DRIVER || true
        ;;
    *)
        echo "SL101_WPE_RENDERER must be software or grate" >&2
        exit 2
        ;;
esac

# No sandbox bypass is passed. WebKit's normal Bubblewrap process sandbox is
# part of acceptance and is verified separately on-device.
exec "$MINIBROWSER" "$URL"
