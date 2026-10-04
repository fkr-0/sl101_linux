#!/bin/sh
# Install session controls without restarting labwc or changing the boot default.
set -eu
host=${1:-root@192.168.23.106}
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
library=${2:-"$root/work/sl101-grate-production-20261004/libgallium-25.0.7.so"}
wlroots=${3:-"$root/work/sl101-grate-production-20261004/wlroots-build/libwlroots-0.20.so"}
[ -f "$wlroots" ] || { echo "production wlroots required as third argument" >&2; exit 2; }
[ -f "$library" ] || { echo "scanout-corrected library required as second argument" >&2; exit 2; }
stage=/tmp/sl101-renderer-controls-install
ssh "$host" "mkdir -p $stage"
scp "$root/scripts/sl101-renderer-switch.py" "$root/scripts/sl101-user-session/sl101-renderer-verify" "$root/scripts/sl101-user-session/sl101-desktop" "$root/scripts/sl101-user-session/wayvnc.init" "$host:$stage/"
scp "$library" "$host:$stage/libgallium-25.0.7.so"
scp "$wlroots" "$host:$stage/libwlroots-0.20.so"
ssh "$host" sh -s <<'REMOTE'
set -eu
[ "$(cat /etc/hostname)" = sl101-nura ]
[ "$(cat /sys/block/mmcblk1/device/cid)" = 035344534c31323880ac79a543010300 ]
stage=/tmp/sl101-renderer-controls-install
backup=/var/lib/sl101-renderer-switch-backup
mkdir -p "$backup"
[ -e "$backup/desktop" ] || cp -p /usr/local/bin/sl101-desktop "$backup/desktop"
[ -e "$backup/wayvnc" ] || cp -p /etc/init.d/sl101-wayvnc "$backup/wayvnc"
destination=/usr/local/lib/sl101-grate-38b7bd1f600d2889a3caeec609e7520842701eab8aa10193f98966ce4e33987c
if [ ! -e "$destination" ]; then
    mkdir -p "$destination"
    cp -a /opt/grate-mesa25-texfuse-68a78e18af642275d3fec6fc93a4f20cd618d9f951981c7e240d5731e7f29ade/lib "$destination/"
    chown -R root:root "$destination"
    chmod -R go-w "$destination"
fi
install -m 755 "$stage/libwlroots-0.20.so" "$destination/lib/libwlroots-0.20.so"
install -m 755 "$stage/libgallium-25.0.7.so" "$destination/lib/libgallium-25.0.7.so"
install -m 755 "$stage/sl101-renderer-switch.py" /usr/local/sbin/sl101-renderer-switch
install -m 755 "$stage/sl101-renderer-verify" /usr/local/sbin/sl101-renderer-verify
/usr/local/sbin/sl101-renderer-verify
install -m 755 "$stage/sl101-desktop" /usr/local/bin/sl101-desktop
install -m 755 "$stage/wayvnc.init" /etc/init.d/sl101-wayvnc
printf 'user ALL=(root) NOPASSWD: /usr/local/sbin/sl101-renderer-switch pixman, /usr/local/sbin/sl101-renderer-switch grate\n' >/etc/sudoers.d/sl101-renderer
chmod 440 /etc/sudoers.d/sl101-renderer
visudo -cf /etc/sudoers
printf 'Controls installed; labwc and boot renderer untouched. Enable panel with --enable-renderer-switch.\n'
REMOTE
