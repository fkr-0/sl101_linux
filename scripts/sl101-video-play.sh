#!/bin/sh
# Local-file playback on SL101 with CPU decode and Wayland shared-memory output.
# No GPU/Grate/VDE path or persistent system change is attempted.
set -eu

usage() {
    cat <<'EOF'
usage: sl101-video-play.sh [--dry-run] [--fullscreen] [--mute] -- FILE

Requires a native mpv with the wlshm video output and an active Wayland
session. Software decoding is intentionally forced; Grate EGL is not a
video decoder. Use --dry-run to inspect without launching a player.
Local files only; use scripts/sl101-video-transcode.sh on a faster host
to create a low-complexity compatibility copy when needed.
EOF
}

die() { printf 'sl101-video: %s\n' "$*" >&2; exit 1; }
dry=0
fullscreen=0
mute=0
while [ "$#" -gt 0 ]; do
    case "$1" in
        --dry-run) dry=1; shift ;;
        --fullscreen) fullscreen=1; shift ;;
        --mute) mute=1; shift ;;
        --) shift; break ;;
        -h|--help) usage; exit 0 ;;
        *) usage >&2; die "unknown option (use -- before path): $1" ;;
    esac
done
[ "$#" -eq 1 ] || { usage >&2; die 'exactly one local file is required'; }
source=$1
[ -f "$source" ] && [ -r "$source" ] || die "not a readable regular file: $source"
command -v readlink >/dev/null 2>&1 || die 'readlink is required'
source=$(readlink -f "$source") || die 'unable to resolve input path'
[ -f "$source" ] && [ -r "$source" ] || die 'resolved file is not readable'

if [ "$dry" -eq 1 ]; then
    printf 'mode: local software decode; no GPU, VDE, installs or mount changes\n'
    printf 'file: %s\n' "$source"
    printf 'player: mpv --no-config --hwdec=no --vo=wlshm --framedrop=vo [--fullscreen] [--mute=yes] -- FILE\n'
    exit 0
fi

command -v mpv >/dev/null 2>&1 || die 'mpv not installed; see docs/sl101-video-playback.md'
# Inspect output support without initializing any hardware video decoder.
mpv --no-config --vo=help 2>&1 | grep -Eq '(^|[[:space:]])wlshm([[:space:]]|$)' ||
    die 'this mpv build does not provide the wlshm output'

runtime=${XDG_RUNTIME_DIR:-}
display=${WAYLAND_DISPLAY:-wayland-0}
case "$display" in
    /*) socket=$display ;;
    *) [ -n "$runtime" ] || die 'XDG_RUNTIME_DIR not set'
       socket=$runtime/$display ;;
esac
[ -S "$socket" ] || die "no Wayland socket at $socket"
[ -r "$socket" ] && [ -w "$socket" ] || die "Wayland socket not accessible: $socket"

set -- --no-config --hwdec=no --vo=wlshm --framedrop=vo --no-ytdl --no-load-unsafe-playlists
[ "$fullscreen" -eq 0 ] || set -- "$@" --fullscreen
[ "$mute" -eq 0 ] || set -- "$@" --mute=yes
printf 'sl101-video: software playback (wlshm), file=%s\n' "$source" >&2
exec mpv "$@" -- "$source"
