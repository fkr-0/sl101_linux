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
# Host-only tests extract this remote body and mock commands; no live execute here.
command -v setsid >/dev/null || exit 38
command -v rc-service >/dev/null || exit 39
desktop_was_started=0
if rc-service sl101-desktop status 2>&1 | grep -q started; then desktop_was_started=1; fi
out=/tmp/sl101-fbl01-kms-atomic-20261103
capture_pid=
stop_capture() {
  [ -n "$capture_pid" ] || return 0
  kill -TERM "-$capture_pid" 2>/dev/null || :
  sleep 2
  kill -KILL "-$capture_pid" 2>/dev/null || :
  wait "$capture_pid" 2>/dev/null || :
  capture_pid=
}
restore() {
  rc=$?
  trap - EXIT HUP INT TERM
  stop_capture
  if ! printf "%s\n" "$old" > /sys/module/drm/parameters/debug; then
    echo "CRITICAL: manually restore drm.debug to $old" >&2
    rc=90
  fi
  if [ "$desktop_was_started" -eq 1 ]; then
    if ! rc-service sl101-desktop status 2>&1 | grep -q started; then
      if ! rc-service sl101-desktop start; then
        echo "CRITICAL: desktop restart failed" >&2
        rc=91
      fi
      if ! rc-service sl101-desktop status 2>&1 | grep -q started; then
        echo "CRITICAL: desktop not running after restart attempt" >&2
        rc=92
      fi
    fi
  fi
  exit "$rc"
}
trap restore EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM
dmesg > "$out.before-dmesg.log" || :
printf "%s\n" 0x1f > /sys/module/drm/parameters/debug
# Own the deadline and kill descendants as a process group. BusyBox timeout
# can leave a strace -> launcher -> Cog grandchild running after termination.
setsid sh -c 'exec strace -f -tt -v -s 256 -e trace=ioctl -o "$1" sl101-kms-run --timeout 35 -- /usr/local/bin/sl101-cog-drm-root-cpu --gpu https://example.org' sh "$out.strace.log" > "$out.launch.log" 2>&1 &
capture_pid=$!
deadline=$(($(date +%s) + 75))
launcher_rc=0
while kill -0 "$capture_pid" 2>/dev/null; do
  if [ "$(date +%s)" -ge "$deadline" ]; then
    launcher_rc=124
    break
  fi
  sleep 1
done
if [ "$launcher_rc" -eq 0 ]; then
  wait "$capture_pid" || launcher_rc=$?
fi
stop_capture
dmesg > "$out.after-dmesg.log" || :
echo "capture_prefix=$out launcher_rc=$launcher_rc"
exit "$launcher_rc"
REMOTE
