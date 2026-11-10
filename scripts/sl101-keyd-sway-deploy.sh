#!/bin/sh
# SL101 Nura: one-target, hash-gated keyd + Sway input deployment.
# Stage candidate files at the explicit /tmp paths below; run via sudo.
# The graphical session is NOT restarted. A failed postflight restores backups.
set -eu

mode=$1
target=sl101-nura
keyd_file=/etc/keyd/sl101.conf
sway_file=/home/user/.config/sway/config
keyd_stage=/tmp/sl101-keyd-20261109-candidate.conf
sway_stage=/tmp/sl101-sway-20261109-live-merged.conf
backup=/var/lib/sl101-keyd-sway-20261109
old_keyd=08ee8b348ccc13cd050dd714bbb23fe08592ee8bb1d1613beb6d67570d3a3d21
old_sway=0e6369dbffed4caac7a9f2712cebd8e0bf056aaba1a41c7f0f5db19fc1c8c058
new_keyd=b91be7d5e318b3d2d0be8b9052689ac87d41b50ebe65c3fdb26d8832c99daf84
new_sway=2308762641127b6bf472d46fa71e1cc36cc19a637ef88d8b8b46c919cec5cbb0
runtime=/run/sl101-desktop-user
installed=0

die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
hash() { sha256sum "$1" | cut -d ' ' -f 1; }

[ "$(id -u)" = 0 ] || die "must run as root"
[ "$(hostname)" = "$target" ] || die "wrong host"
[ "$(uname -r)" = 7.0.1-postmarketos-grate ] || die "wrong kernel"
[ "$(cat /sys/block/mmcblk1/device/cid)" = 035344534c31323880ac79a543010300 ] || die "wrong SD CID"

# Standard SL101 live qualification lock; abort rather than displace another owner.
exec 9>/run/lock/sl101-nura-qualification.lock
flock -n 9 || die "graphics qualification lock is busy"
pid=$(cat /run/sl101-desktop.pid) || die "no desktop pid"
case "$pid" in *[!0-9]*|'') die "invalid compositor pid";; esac
kill -0 "$pid" || die "compositor not alive"
socket="$runtime/sway-ipc.10000.$pid.sock"
[ -S "$socket" ] || die "Sway IPC socket absent"
sway_user() {
    sudo -n -u user env XDG_RUNTIME_DIR="$runtime" SWAYSOCK="$socket" swaymsg -s "$socket" -r "$@"
}
get_loaded_hash() {
    sway_user -t get_config |
       python3 -c 'import sys,json,hashlib; print(hashlib.sha256(json.load(sys.stdin)["config"].encode()).hexdigest())'
}
reload_sway() {
    response=$(sway_user reload)
    printf '%s\n' "$response" | grep -Eq '"success"[[:space:]]*:[[:space:]]*true' ||
        die "Sway reload denied: $response"
}
install_keyd() {
    install -o root -g root -m 0644 "$1" /etc/keyd/.sl101.conf.input-next
    mv -f /etc/keyd/.sl101.conf.input-next "$keyd_file"
}
install_sway() {
    install -o user -g user -m 0644 "$1" /home/user/.config/sway/.config.input-next
    mv -f /home/user/.config/sway/.config.input-next "$sway_file"
}
restore() {
    [ -f "$backup/keyd.before" ] || die "keyd rollback backup missing"
    [ -f "$backup/sway.before" ] || die "Sway rollback backup missing"
    install_keyd "$backup/keyd.before"
    install_sway "$backup/sway.before"
    keyd check "$keyd_file"
    keyd reload
    reload_sway
    [ "$(get_loaded_hash)" = "$old_sway" ] || die "Sway rollback IPC mismatch"
    printf 'ROLLBACK_OK keyd=%s sway=%s\n' "$(hash "$keyd_file")" "$(hash "$sway_file")"
}
on_exit() {
    status=$?
    trap - EXIT
    if [ "$status" -ne 0 ] && [ "$installed" = 1 ]; then
        printf 'POSTFLIGHT_FAILED, restoring original files\n' >&2
        restore || printf 'ROLLBACK_FAILED: manual recovery from %s required\n' "$backup" >&2
    fi
    exit "$status"
}
trap on_exit EXIT

case "$mode" in
    --check)
        if [ "$(hash "$keyd_file")" = "$new_keyd" ] &&
           [ "$(hash "$sway_file")" = "$new_sway" ]; then
            [ "$(get_loaded_hash)" = "$new_sway" ] || die "active Sway postflight mismatch"
            [ "$(hash "$backup/keyd.before")" = "$old_keyd" ] || die "keyd rollback missing or corrupt"
            [ "$(hash "$backup/sway.before")" = "$old_sway" ] || die "Sway rollback missing or corrupt"
            rc-service keyd status >/dev/null || die "keyd not running"
            printf 'POSTFLIGHT_OK (already deployed)\n'
            exit 0
        fi
        [ "$(hash "$keyd_file")" = "$old_keyd" ] || die "live keyd drift"
        [ "$(hash "$sway_file")" = "$old_sway" ] || die "live Sway drift"
        [ "$(get_loaded_hash)" = "$old_sway" ] || die "active Sway differs from installed config"
        [ "$(hash "$keyd_stage")" = "$new_keyd" ] || die "keyd candidate hash mismatch"
        [ "$(hash "$sway_stage")" = "$new_sway" ] || die "Sway candidate hash mismatch"
        keyd check "$keyd_stage"
        sudo -n -u user env XDG_RUNTIME_DIR="$runtime" WLR_BACKENDS=headless WLR_RENDERER=pixman \
            sway -C -c "$sway_stage"
        [ ! -e "$backup" ] || die "backup destination already exists"
        printf 'PREFLIGHT_OK old_keyd=%s old_sway=%s new_keyd=%s new_sway=%s\n' \
            "$old_keyd" "$old_sway" "$new_keyd" "$new_sway"
        ;;
    --apply)
        if [ "$(hash "$keyd_file")" = "$new_keyd" ] &&
           [ "$(hash "$sway_file")" = "$new_sway" ]; then
            [ "$(get_loaded_hash)" = "$new_sway" ] || die "Sway IPC mismatch after existing deployment"
            [ "$(hash "$backup/keyd.before")" = "$old_keyd" ] || die "keyd rollback missing or corrupt"
            [ "$(hash "$backup/sway.before")" = "$old_sway" ] || die "Sway rollback missing or corrupt"
            rc-service keyd status >/dev/null || die "keyd not running"
            printf 'ALREADY_DEPLOYED (changed=0)\n'
            exit 0
        fi
        # Recheck after taking the lock, before any filesystem mutation.
        [ "$(hash "$keyd_file")" = "$old_keyd" ] || die "live keyd drift"
        [ "$(hash "$sway_file")" = "$old_sway" ] || die "live Sway drift"
        [ "$(get_loaded_hash)" = "$old_sway" ] || die "Sway IPC config drift"
        [ "$(hash "$keyd_stage")" = "$new_keyd" ] || die "bad keyd candidate"
        [ "$(hash "$sway_stage")" = "$new_sway" ] || die "bad Sway candidate"
        keyd check "$keyd_stage"
        sudo -n -u user env XDG_RUNTIME_DIR="$runtime" WLR_BACKENDS=headless WLR_RENDERER=pixman \
            sway -C -c "$sway_stage"
        [ ! -e "$backup" ] || die "backup destination already exists"
        mkdir -m 0700 "$backup"
        cp -p "$keyd_file" "$backup/keyd.before"
        cp -p "$sway_file" "$backup/sway.before"
        [ "$(hash "$backup/keyd.before")" = "$old_keyd" ] || die "keyd backup failed"
        [ "$(hash "$backup/sway.before")" = "$old_sway" ] || die "Sway backup failed"
        installed=1
        install_keyd "$keyd_stage"
        install_sway "$sway_stage"
        keyd check "$keyd_file"
        keyd reload
        reload_sway
        [ "$(hash "$keyd_file")" = "$new_keyd" ] || die "installed keyd changed"
        [ "$(hash "$sway_file")" = "$new_sway" ] || die "installed Sway changed"
        [ "$(get_loaded_hash)" = "$new_sway" ] || die "Sway IPC did not load new config"
        rc-service keyd status >/dev/null || die "keyd is not running"
        printf 'DEPLOY_OK backup=%s keyd=%s sway=%s\n' \
            "$backup" "$new_keyd" "$new_sway"
        installed=0
        ;;
    --rollback)
        [ "$(hash "$keyd_file")" = "$new_keyd" ] || die "refusing rollback over keyd drift"
        [ "$(hash "$sway_file")" = "$new_sway" ] || die "refusing rollback over Sway drift"
        restore
        ;;
    *)
        die "usage: $0 --check | --apply | --rollback"
        ;;
esac
