#!/bin/sh
# Detached VDE KMS playback wrapper for the SL101.
# Stops the audio session + compositor, plays via VDE/KMS, restarts both.
# Designed to run as root, detached from SSH/TUI (nohup/setsid).
# Logs to /tmp/sl101-vde-kms-play.log.
set -u
FILE=${1:?usage: sl101-video-kms-play FILE}
LOG=/tmp/sl101-vde-kms-play.log

main() {
echo "$(date): starting VDE KMS playback of $FILE"

# Stop audio session (PipeWire/WirePlumber/Pulse) cleanly via manager
if [ -x /usr/local/bin/sl101-audio-session ]; then
    echo "stopping audio session..."
    /usr/local/bin/sl101-audio-session stop 2>&1 || true
fi

# Stop compositor
labwc_was_running=0
if pgrep -x labwc >/dev/null 2>&1; then
    labwc_was_running=1
    echo "stopping labwc..."
    rc-service sl101-desktop stop 2>&1 || {
        echo "rc-service stop failed, killing directly"
        pkill -x labwc 2>/dev/null || true
    }
    sleep 2
fi

# Switch to a blank VT so tmux/foot don't bleed through the video
orig_vt=$(cat /sys/class/tty/tty0/active 2>/dev/null || echo tty1)
chvt 2 2>/dev/null || true
for vt in /dev/tty2 /dev/tty1 /dev/tty0; do
    if [ -c "$vt" ]; then
        printf '\033[2J\033[H\033[?25l' >"$vt" 2>/dev/null || true
        break
    fi
done

echo "launching gst-launch-1.0..."
gst-launch-1.0 \
    filesrc location="$FILE" ! qtdemux name=demux \
    demux.video_0 ! queue max-size-buffers=3 ! h264parse ! v4l2slh264dec ! kmssink \
    demux.audio_0 ! queue max-size-buffers=0 max-size-time=3000000000 max-size-bytes=0 ! \
    aacparse ! avdec_aac ! audioconvert ! audioresample ! alsasink 2>&1
echo "gst exit=$?"

# Restore VT
for vt in /dev/tty2 /dev/tty1 /dev/tty0; do
    if [ -c "$vt" ]; then
        printf '\033[?25h' >"$vt" 2>/dev/null || true
        break
    fi
done
# Switch back to the original VT (compositor or tmux)
case "$orig_vt" in tty[0-9]*) chvt "${orig_vt#tty}" 2>/dev/null || true ;; esac

# Restart via service (handles dbus, audio, labwc, autostart)
if [ "$labwc_was_running" -eq 1 ]; then
    echo "restarting desktop service..."
    rc-service sl101-desktop start 2>&1
    sleep 2
    if pgrep -x labwc >/dev/null 2>&1; then
        echo "desktop restarted OK"
    else
        echo "WARNING: desktop failed to restart"
    fi
fi

echo "$(date): done"
}

main > "$LOG" 2>&1
