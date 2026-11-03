#!/bin/sh
set -eu
mode=${1:---dry-run}
case "$mode" in --dry-run|--execute) ;; *) exit 2;; esac
host=${SL101_FBL01_HOST:-user@192.168.23.106}
[ "$host" = user@192.168.23.106 ] || { echo "Refusing non-canonical target" >&2; exit 2; }
ssh -o BatchMode=yes -o ConnectTimeout=5 "$host" "sudo -n sh -s -- $mode" <<'REMOTE'
set -eu
[ "$(hostname)" = sl101-nura ] || exit 31
[ "$(uname -r)" = 7.0.1-postmarketos-grate ] || exit 32
grep -aq 'ASUS Eee Pad Slider SL101' /proc/device-tree/model || exit 33
command -v strace >/dev/null || exit 34
command -v sl101-kms-run >/dev/null || exit 35
test -x /usr/local/bin/sl101-cog-drm-root-cpu || exit 36
test -r /sys/module/drm/parameters/debug && test -w /sys/module/drm/parameters/debug || exit 37
old=$(cat /sys/module/drm/parameters/debug)
echo "hostname=$(hostname) kernel=$(uname -r) original_drm_debug=$old"
if [ "$1" = --dry-run ]; then echo "DRY RUN: no mutation"; exit 0; fi
out=/tmp/sl101-fbl01-kms-atomic-20261103
restore() {
  rc=$?
  trap - EXIT HUP INT TERM
  printf "%s\n" "$old" > /sys/module/drm/parameters/debug || echo "CRITICAL: manually restore drm.debug to $old" >&2
  exit "$rc"
}
trap restore EXIT HUP INT TERM
dmesg > "$out.before-dmesg.log" || :
printf "%s\n" 0x1f > /sys/module/drm/parameters/debug
rc=0
timeout -s TERM -k 5 75 strace -f -tt -v -s 256 -e trace=ioctl -o "$out.strace.log" sl101-kms-run --timeout 35 -- /usr/local/bin/sl101-cog-drm-root-cpu --gpu https://example.org > "$out.launch.log" 2>&1 || rc=$?
dmesg > "$out.after-dmesg.log" || :
echo "capture_prefix=$out launcher_rc=$rc"
REMOTE
