#!/bin/sh
# Tegra VDE hardware-decoded video playback via GStreamer on the SL101.
# H.264 Baseline/Constrained Baseline/Main profile only (VDE hardware limit).
# High profile content must be transcoded first with sl101-video-transcode.sh --profile main.
set -eu

usage() {
    cat <<'EOF'
usage: sl101-video-play-vde.sh [--kms|--wayland] [--dry-run] [--fullscreen] [--mute] [--no-audio] [--fps N] -- FILE

Hardware-decoded H.264 playback using the Tegra20 VDE (Video Decoder Engine)
via GStreamer's V4L2 stateless codec pipeline.

Display modes:
  --kms      (default) Direct KMS/DRM output via kmssink. VDE DMABuf goes
             straight to the panel — zero-copy, no software conversion.
             Requires DRM master; stops the Wayland compositor during playback
             and restarts it afterwards.
  --wayland  Wayland SHM output via waylandsink. Requires a running Wayland
             session. Forces I420 system-memory copy and software colorspace
             conversion; --fps caps display rate (default 12) to avoid drops.

Requires: gst-launch-1.0, v4l2slh264dec (gst-plugins-bad v4l2codecs),
gst-libav (avdec_aac for AAC audio), and /dev/video0 (tegra-vde).

Only H.264 Baseline, Constrained Baseline and Main profiles are supported
by the VDE hardware. High-profile content will fail at decode time.
EOF
}

die() { printf 'sl101-video-vde: %s\n' "$*" >&2; exit 1; }
dry=0
fullscreen=0
mute=0
no_audio=0
fps=12
display_mode=kms
while [ "$#" -gt 0 ]; do
    case "$1" in
        --dry-run) dry=1; shift ;;
        --kms) display_mode=kms; shift ;;
        --wayland) display_mode=wayland; shift ;;
        --fullscreen) fullscreen=1; shift ;;
        --mute) mute=1; shift ;;
        --no-audio) no_audio=1; shift ;;
        --fps) [ "$#" -ge 2 ] || die '--fps needs a value'; fps=$2; shift 2 ;;
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
case "$fps" in *[!0-9]*|0|'') die "fps must be a positive integer: $fps";; esac
[ "$fps" -le 60 ] || die "fps too high: $fps (max 60)"

if [ "$dry" -eq 1 ]; then
    printf 'mode: VDE hardware H.264 decode via GStreamer v4l2slh264dec\n'
    printf 'file: %s\n' "$source"
    if [ "$display_mode" = kms ]; then
        printf 'display: kmssink (direct DRM/KMS, VDE DMABuf zero-copy)\n'
    else
        printf 'display: waylandsink (Wayland SHM, I420 system-memory copy)\n'
        printf 'fps_cap: %s\n' "$fps"
    fi
    printf 'audio: %s\n' "$([ "$no_audio" -eq 1 ] && echo 'disabled' || echo 'autoaudiosink (PulseAudio/PipeWire)')"
    printf 'profiles: Baseline, Constrained Baseline, Main only (VDE hardware limit)\n'
    exit 0
fi

command -v gst-launch-1.0 >/dev/null 2>&1 || die 'gst-launch-1.0 not installed'
gst-inspect-1.0 v4l2slh264dec >/dev/null 2>&1 || die 'v4l2slh264dec not available (need gst-plugins-bad v4l2codecs)'
[ -c /dev/video0 ] || die '/dev/video0 not present (tegra-vde not loaded?)'
[ -r /dev/video0 ] || die '/dev/video0 not readable by current user'

if [ "$display_mode" = kms ]; then
    [ -c /dev/dri/card0 ] || die '/dev/dri/card0 not present'

    video_pipeline="queue max-size-buffers=3 ! h264parse ! v4l2slh264dec"
    video_sink="kmssink"

    compositor_pid=""
    had_pipewire=0
    if pgrep -x labwc >/dev/null 2>&1; then
        compositor_pid=$(pgrep -x labwc)
        printf 'sl101-video-vde: stopping compositor (pid %s) for DRM master\n' "$compositor_pid" >&2
        # Stop PipeWire/WirePlumber first — they hold audio resources and
        # fail to restart if killed after the compositor they depend on.
        if pgrep -x wireplumber >/dev/null 2>&1; then
            had_pipewire=1
            pkill -x wireplumber 2>/dev/null || true
            pkill -x pipewire-pulse 2>/dev/null || true
            pkill -x pipewire 2>/dev/null || true
            sleep 1
        fi
        kill "$compositor_pid" 2>/dev/null || true
        sleep 2
    fi

    # Blank VT and hide cursor so console text doesn't bleed over the video
    active_vt=""
    for vt in /dev/tty1 /dev/tty0 /dev/console; do
        [ -c "$vt" ] && { active_vt=$vt; break; }
    done
    if [ -n "$active_vt" ]; then
        printf '\033[2J\033[H\033[?25l' >"$active_vt" 2>/dev/null || true
    fi

    restart_compositor() {
        # Restore VT cursor
        if [ -n "$active_vt" ]; then
            printf '\033[?25h' >"$active_vt" 2>/dev/null || true
        fi
        if [ -n "$compositor_pid" ]; then
            printf 'sl101-video-vde: restarting compositor\n' >&2
            # Restart PipeWire/WirePlumber before the compositor
            if [ "$had_pipewire" -eq 1 ]; then
                su -s /bin/sh user -c "
                    export XDG_RUNTIME_DIR=/run/sl101-desktop-user
                    export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/sl101-desktop-user/sl101-desktop-bus
                    nohup pipewire </dev/null >/dev/null 2>&1 &
                    sleep 1
                    nohup wireplumber </dev/null >/dev/null 2>&1 &
                    nohup pipewire-pulse </dev/null >/dev/null 2>&1 &
                "
                sleep 1
            fi
            su -s /bin/sh user -c "
                export LIBSEAT_BACKEND=seatd
                export XDG_RUNTIME_DIR=/run/sl101-desktop-user
                export WLR_RENDERER=pixman
                export XKB_DEFAULT_LAYOUT=de
                export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/sl101-desktop-user/sl101-desktop-bus
                nohup labwc -V </dev/null >/dev/null 2>&1 &
            "
            sleep 1
        fi
    }
    trap restart_compositor EXIT
else
    runtime=${XDG_RUNTIME_DIR:-}
    display=${WAYLAND_DISPLAY:-wayland-0}
    case "$display" in
        /*) socket=$display ;;
        *) [ -n "$runtime" ] || die 'XDG_RUNTIME_DIR not set'
           socket=$runtime/$display ;;
    esac
    [ -S "$socket" ] || die "no Wayland socket at $socket"
    [ -r "$socket" ] && [ -w "$socket" ] || die "Wayland socket not accessible: $socket"

    video_pipeline="queue max-size-buffers=3 max-size-time=0 max-size-bytes=0 ! h264parse ! v4l2slh264dec ! video/x-raw,format=I420 ! videorate ! video/x-raw,framerate=${fps}/1 ! videoconvert"
    video_sink="waylandsink max-lateness=200000000"
    [ "$fullscreen" -eq 0 ] || video_sink="waylandsink fullscreen-on-show=true max-lateness=200000000"
fi

if [ "$display_mode" = kms ]; then
    audio_sink="alsasink"
else
    audio_sink="autoaudiosink"
fi

run_gst() {
    if [ "$display_mode" = kms ]; then
        gst-launch-1.0 "$@"
    else
        exec gst-launch-1.0 "$@"
    fi
}

if [ "$no_audio" -eq 1 ] || [ "$mute" -eq 1 ]; then
    audio_label="no audio"
    [ "$mute" -eq 1 ] && audio_label="muted"
    printf 'sl101-video-vde: VDE playback (%s, %s), file=%s\n' "$display_mode" "$audio_label" "$source" >&2
    run_gst \
        filesrc location="$source" ! qtdemux name=demux \
        demux.video_0 ! $video_pipeline ! $video_sink \
        demux.audio_0 ! queue ! fakesink
else
    printf 'sl101-video-vde: VDE playback (%s, audio=%s), file=%s\n' "$display_mode" "$audio_sink" "$source" >&2
    run_gst \
        filesrc location="$source" ! qtdemux name=demux \
        demux.video_0 ! $video_pipeline ! $video_sink \
        demux.audio_0 ! queue max-size-buffers=0 max-size-time=3000000000 max-size-bytes=0 ! \
        aacparse ! avdec_aac ! audioconvert ! audioresample ! $audio_sink
fi
