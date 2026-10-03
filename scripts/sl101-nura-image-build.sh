#!/bin/sh
# Build a private recovery image from a trusted SL101 rootfs snapshot.
set -eu
[ "$(id -u)" = 0 ] || { echo 'Run with sudo; only the output image is partitioned.' >&2; exit 1; }
[ "$#" = 2 ] || [ "$#" = 3 ] || { echo "Usage: $0 ROOTFS.tar.gz NEW-IMAGE.img [PACKAGE-REFRESH.tar.gz]" >&2; exit 1; }
archive=$(realpath "$1")
image=$(realpath -m "$2")
refresh=''
[ "$#" != 3 ] || refresh=$(realpath "$3")
[ -f "$archive" ] && [ ! -e "$image" ] || { echo 'Archive missing or output already exists' >&2; exit 1; }
umask 077
work=$(mktemp -d)
loop=''
cleanup() {
    mountpoint -q "$work/root" && umount "$work/root" || true
    [ -z "$loop" ] || losetup -d "$loop"
    rmdir "$work/root" "$work" 2>/dev/null || true
}
trap cleanup EXIT HUP INT TERM
mkdir "$work/root"
truncate -s 4G "$image"
printf 'label: dos\nstart=2048, type=83, bootable\n' | sfdisk "$image" >/dev/null
loop=$(losetup --find --show --partscan "$image")
udevadm settle
mkfs.ext4 -q -L nura_root -U 6dd3675d-b5cf-41bd-9262-103c59321451 "${loop}p1"
mount "${loop}p1" "$work/root"
tar -xzf "$archive" --numeric-owner -C "$work/root"
[ -z "$refresh" ] || tar -xzf "$refresh" --numeric-owner -C "$work/root"
root="$work/root"
mkdir -p "$root"/proc "$root"/sys "$root"/dev "$root"/run "$root"/tmp "$root"/mnt "$root"/media "$root"/var/log "$root"/var/cache/apk
chmod 1777 "$root/tmp"
test -e "$root/lib/modules/6.18.45"
test -x "$root/usr/sbin/labwc"
test -x "$root/etc/init.d/networkmanager"
printf 'UUID=6dd3675d-b5cf-41bd-9262-103c59321451 / ext4 defaults 0 0\n' > "$root/etc/fstab"
mkdir -p "$root/usr/local/bin" "$root/etc/runlevels/default" "$root/root/.config/labwc"
cat > "$root/usr/local/bin/sl101-desktop" <<'EOF'
#!/bin/sh
set -eu
export XDG_RUNTIME_DIR=/run/user/0
mkdir -p "$XDG_RUNTIME_DIR"
chmod 700 "$XDG_RUNTIME_DIR"
export LIBSEAT_BACKEND=seatd WLR_RENDERER=pixman
unset LD_LIBRARY_PATH GBM_BACKENDS_PATH MESA_LOADER_DRIVER_OVERRIDE
exec dbus-run-session -- labwc
EOF
cat > "$root/etc/init.d/sl101-desktop" <<'EOF'
#!/sbin/openrc-run
description="SL101 ad hoc pixman desktop"
command="/usr/local/bin/sl101-desktop"
command_background=yes
pidfile="/run/sl101-desktop.pid"
output_log="/var/log/sl101-desktop.log"
error_log="/var/log/sl101-desktop.log"
depend() { need seatd dbus; after local; }
EOF
cat > "$root/root/.config/labwc/autostart" <<'EOF'
#!/bin/sh
foot >/tmp/sl101-foot.log 2>&1 &
netsurf >/tmp/sl101-netsurf.log 2>&1 &
EOF
chmod 755 "$root/usr/local/bin/sl101-desktop" "$root/etc/init.d/sl101-desktop" "$root/root/.config/labwc/autostart"
for service in seatd dbus networkmanager sshd local sl101-desktop; do
    test -x "$root/etc/init.d/$service"
    ln -sf "/etc/init.d/$service" "$root/etc/runlevels/default/$service"
done
# Machine-local backup: retain Wi-Fi, authorized keys and host identity.
# Never distribute this image as a public release.
sync
umount "$root"
e2fsck -fn "${loop}p1"
losetup -d "$loop"
loop=''
sha256sum "$image" > "$image.sha256"
echo "Built $image; cold-boot and desktop service qualification still required."
