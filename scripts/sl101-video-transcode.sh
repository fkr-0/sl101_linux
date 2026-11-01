#!/bin/sh
# Host-side compatibility transcode: deliberately no playback/device mutation.
set -eu
usage() {
    cat <<'EOF'
usage: sl101-video-transcode.sh [--height 360|480] [--codec mpeg4|h264] -- INPUT OUTPUT.mp4

Creates a low-complexity 24fps 8-bit 4:2:0 MP4 for software playback on
the non-NEON Tegra20. MPEG-4 Part 2 is the default CPU-friendly choice.
H.264 Baseline/CAVLC is an optional VDE research fixture, NOT proof of
hardware decoding. Refuses to replace existing files.
EOF
}
die() { printf 'sl101-video-transcode: %s\n' "$*" >&2; exit 1; }
height=360
codec=mpeg4
while [ "$#" -gt 0 ]; do
    case "$1" in
        --height) [ "$#" -ge 2 ] || die '--height needs a value'; height=$2; shift 2 ;;
        --codec) [ "$#" -ge 2 ] || die '--codec needs a value'; codec=$2; shift 2 ;;
        --) shift; break ;;
        -h|--help) usage; exit 0 ;;
        *) usage >&2; die "unknown option: $1" ;;
    esac
done
[ "$#" -eq 2 ] || { usage >&2; die 'input and output required'; }
case "$height" in 360|480) ;; *) die 'height must be 360 or 480';; esac
case "$codec" in mpeg4|h264) ;; *) die 'codec must be mpeg4 or h264';; esac
input=$1
output=$2
[ -r "$input" ] && [ -f "$input" ] || die "unreadable input: $input"
[ ! -e "$output" ] && [ ! -L "$output" ] || die "refusing to overwrite: $output"
case "$output" in *.mp4) ;; *) die 'output must have .mp4 extension';; esac
# Absolute paths keep FFmpeg from interpreting a local filename with a colon
# as a protocol/URL. Reject nonexistent output directories.
input=$(readlink -f "$input") || die 'cannot canonicalize input'
out_dir=$(dirname "$output")
[ -d "$out_dir" ] || die 'output directory does not exist'
out_dir=$(readlink -f "$out_dir") || die 'cannot canonicalize output directory'
output=$out_dir/$(basename "$output")
[ ! -e "$output" ] && [ ! -L "$output" ] || die "refusing to overwrite: $output"
command -v ffmpeg >/dev/null 2>&1 || die 'ffmpeg is required on the host'
# -n is fail-closed for races with a newly created output.
# min(ih,N) preserves small sources without upscaling.
filter="scale=w=-2:h='min(ih,$height)':flags=fast_bilinear,fps=24,format=yuv420p"
if [ "$codec" = h264 ]; then
    exec ffmpeg -hide_banner -nostdin -n -i "$input" \
        -map 0:v:0 -map '0:a:0?' -sn -dn -vf "$filter" \
        -c:v libx264 -preset ultrafast -profile:v baseline -level:v 3.0 \
        -x264-params cabac=0:ref=1:bframes=0 -crf 25 -maxrate 1000k -bufsize 2000k \
        -c:a aac -b:a 96k -ac 2 -movflags +faststart "$output"
fi
exec ffmpeg -hide_banner -nostdin -n -i "$input" \
    -map 0:v:0 -map '0:a:0?' -sn -dn -vf "$filter" \
    -c:v mpeg4 -q:v 6 -c:a aac -b:a 96k -ac 2 \
    -movflags +faststart "$output"
