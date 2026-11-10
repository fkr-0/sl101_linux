#!/bin/sh
# Debian SL101 .100 only. Safe offline (no active Sway) keyd/Sway/VT install.
set -eu
mode=$1
b=/var/lib/sl101-debian-input-20261109
old=08ee8b348ccc13cd050dd714bbb23fe08592ee8bb1d1613beb6d67570d3a3d21
new=b91be7d5e318b3d2d0be8b9052689ac87d41b50ebe65c3fdb26d8832c99daf84
swnew=378d51dd859f11d21c758f0da92c10fa5f4b9827b1c4148b47d56452582b4422
vtnew=d210218aee4d5672d80e20c0eca55f0004ce87200637627d779e43f216fee711
k=/etc/keyd/sl101.conf
s=/home/user/.config/sway/config
v=/usr/local/bin/sl101-chvt
ks=/tmp/sl101-debian-keyd-20261109.conf
ss=/tmp/sl101-debian-sway-20261109.conf
vs=/tmp/sl101-debian-chvt-20261109.sh
die() { echo "FAIL: $*" >&2; exit 1; }
sha() { sha256sum "$1" | cut -d ' ' -f1; }
check_sha() { test -f "$1" && test "$(sha "$1")" = "$2" || die "hash mismatch $1"; }
no_sway() { ! pgrep -x sway >/dev/null || die "active Sway process (stop before apply)"; }
restart_keyd() {
    systemctl restart keyd
    sleep 2
    systemctl is-active --quiet keyd || die "keyd restart failed"
    test "$(systemctl show -p MainPID --value keyd)" -gt 0 || die "keyd PID missing"
}
restore() {
    check_sha "$b/keyd.before" "$old"
    install -o root -g root -m 0644 "$b/keyd.before" /etc/keyd/.sl101.input-next
    mv -f /etc/keyd/.sl101.input-next "$k"
    rm -f "$s" "$v"
    rmdir /home/user/.config/sway 2>/dev/null || :
    restart_keyd
    check_sha "$k" "$old"
    echo ROLLBACK_OK
}
changed=0
on_exit() {
    rc=$?
    trap - EXIT
    if test "$rc" -ne 0 && test "$changed" = 1; then
        echo 'APPLY_FAILED, restoring original keyd and removing new files' >&2
        restore || echo 'ROLLBACK_FAILURE, inspect root backup' >&2
    fi
    exit "$rc"
}
trap on_exit EXIT

test "$(id -u)" = 0 || die "not root"
test "$(hostname)" = sltwrpbootdebian || die "wrong host"
test "$(uname -r)" = 7.0.1-postmarketos-grate || die "wrong kernel"
test "$(dpkg --print-architecture)" = armhf || die "wrong architecture"
test "$(findmnt -n -o SOURCE /)" = /dev/mmcblk1p1 || die "wrong root"
test "$(cat /sys/block/mmcblk0/device/cid)" = 7001004d4d43333247447e682c336e00 || die "wrong eMMC"
test "$(cat /sys/block/mmcblk1/device/cid)" = 03534453553332478030be3f6400b900 || die "wrong SD"
exec 9>/run/lock/sl101-debian-input-20261109.lock
flock -n 9 || die "deploy lock is held"

if test "$mode" = --rollback; then
    no_sway
    check_sha "$k" "$new"
    check_sha "$s" "$swnew"
    check_sha "$v" "$vtnew"
    restore
    exit 0
fi
case "$mode" in --check|--apply) : ;; *) die "usage: --check|--apply|--rollback" ;; esac
if test -e "$b" && test -f "$k" && test -f "$s" && test -f "$v" &&
    test "$(sha "$k")" = "$new" && test "$(sha "$s")" = "$swnew" &&
    test "$(sha "$v")" = "$vtnew"; then
    check_sha "$b/keyd.before" "$old"
    systemctl is-active --quiet keyd || die "keyd not active"
    echo 'ALREADY_DEPLOYED changed=0'
    exit 0
fi
no_sway
check_sha "$k" "$old"
test ! -e "$s" && test ! -e "$v" || die "destination drift"
test ! -e /home/user/.config/sway || die "existing Sway directory"
test ! -e "$b" || die "backup directory already exists"
test -x /usr/bin/chvt || die "Debian kbd/chvt missing"
systemctl is-active --quiet keyd || die "keyd inactive"
check_sha "$ks" "$new"
check_sha "$ss" "$swnew"
check_sha "$vs" "$vtnew"
sh -n "$vs" || die "shell syntax"
sudo -n -u user env XDG_RUNTIME_DIR=/run/user/1000 WLR_BACKENDS=headless WLR_RENDERER=pixman sway -C -c "$ss" || die "Sway syntax"
if test "$mode" = --check; then echo PREFLIGHT_OK; exit 0; fi

mkdir -m 0700 "$b"
cp -p "$k" "$b/keyd.before"
check_sha "$b/keyd.before" "$old"
printf 'absent\n' >"$b/sway.before.state"
printf 'absent\n' >"$b/chvt.before.state"
changed=1
install -o root -g root -m 0644 "$ks" /etc/keyd/.sl101.input-next
mv -f /etc/keyd/.sl101.input-next "$k"
mkdir -m 0700 /home/user/.config/sway
chown user:user /home/user/.config/sway
install -o user -g user -m 0644 "$ss" /home/user/.config/sway/.config.input-next
mv -f /home/user/.config/sway/.config.input-next "$s"
install -o root -g root -m 0755 "$vs" /usr/local/bin/.sl101-chvt.input-next
mv -f /usr/local/bin/.sl101-chvt.input-next "$v"
restart_keyd
check_sha "$k" "$new"
check_sha "$s" "$swnew"
check_sha "$v" "$vtnew"
no_sway
echo "DEPLOY_OK backup=$b"
changed=0
