#!/bin/sh
# On-device, isolated input-visibility proof ONLY. No Cog, chroot, or rootfs mutation.
# Run as: timeout 15s ssh user@192.168.23.106 'sudo -n sh -s' < this-file
set -eu
[ "$#" -eq 0 ] || exit 64
[ "$(id -u)" -eq 0 ] || exit 77
[ "$(hostname)" = "sl101-nura" ] || exit 65
[ "$(uname -r)" = "7.0.1-postmarketos-grate" ] || exit 65
[ "$(cat /sys/block/mmcblk1/device/cid)" = "035344534c31323880ac79a543010300" ] || exit 65
[ "$(cat /etc/sl101-desktop-renderer.conf)" = "SL101_DESKTOP_RENDERER=grate" ] || exit 65
[ -n "$(pgrep -xo labwc || true)" ] || exit 75
[ -z "$(pgrep -xo cog || true)" ] || exit 75
[ -c /dev/input/event0 ] && [ -c /dev/input/event5 ] || exit 69
[ "$(stat -c %g /dev/input/event0)" = 23 ] || exit 69
[ "$(stat -c %g /dev/input/event5)" = 23 ] || exit 69
[ -d /run/udev/data ] || exit 69
command -v setpriv >/dev/null 2>&1 || exit 69
command -v unshare >/dev/null 2>&1 || exit 69
parent_ns=$(readlink /proc/self/ns/mnt)
dir=$(mktemp -d /tmp/sl101-input-smoke.XXXXXXXX)
case "$dir" in /tmp/sl101-input-smoke.*) ;; *) exit 70 ;; esac
cleanup() {
    rm -f "$dir/event0" "$dir/event5"
    rmdir "$dir/udev" "$dir" 2>/dev/null || true
}
trap cleanup EXIT
touch "$dir/event0" "$dir/event5"
mkdir "$dir/udev"
chmod 755 "$dir"
# All bind mounts occur in a new private namespace, on separate scratch paths.
SL101_INPUT_PARENT_NS="$parent_ns" \
unshare --mount --fork /bin/sh -s "$dir" <<'INNER'
set -eu
dir=$1
this_ns=$(readlink /proc/self/ns/mnt)
[ "$this_ns" != "$SL101_INPUT_PARENT_NS" ] || exit 75
mount --make-rprivate /
mount --bind /dev/input/event0 "$dir/event0"
mount --bind /dev/input/event5 "$dir/event5"
mount --bind /run/udev "$dir/udev"
mount -o remount,bind,ro,nosuid,nodev,noexec "$dir/udev"
[ -c "$dir/event0" ] && [ -c "$dir/event5" ] || exit 69
[ "$(stat -c %t:%T "$dir/event0")" = "$(stat -c %t:%T /dev/input/event0)" ] || exit 69
[ "$(stat -c %t:%T "$dir/event5")" = "$(stat -c %t:%T /dev/input/event5)" ] || exit 69
[ -d "$dir/udev/data" ] || exit 69
setpriv --reuid=1000 --regid=1000 --groups 23 /bin/sh -c \
    'test -r "$1/event0" && test -r "$1/event5" && test -r "$1/udev/data"' sh "$dir" || exit 69
printf 'PASS_PRIVATE_NAMESPACE input_nodes=event0,event5 input_gid=23 udev=visible\n'
INNER
# Host namespace must not see child mounts.
if grep -F "$dir/" /proc/self/mountinfo >/dev/null; then
    echo "host mount propagation detected" >&2
    exit 70
fi
[ "$(readlink /proc/self/ns/mnt)" = "$parent_ns" ] || exit 70
printf 'PASS_NO_HOST_MOUNT_LEAK\n'
