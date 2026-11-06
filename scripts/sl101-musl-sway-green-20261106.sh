#!/usr/bin/env bash
# Supervised deployment to the real SL101, with an automatic remote rollback.
# Default: dry-run. Explicit --apply is required for live Sway changes.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET="${SL101_TARGET:-root@192.168.23.106}"
ARCHIVE="$ROOT/work/sl101-grate-musl-20261106/grate-mesa25-musl-20261106.tar.gz"
EXPECTED="09dc5991a18c3449c163c5ff8f8426f5d3e0f0a7a0210a764b055e19395234db"
PREFIX="/opt/grate-mesa25-musl-20261106"
OLD_PREFIX="/usr/local/lib/sl101-grate-38b7bd1f600d2889a3caeec609e7520842701eab8aa10193f98966ce4e33987c"
REMOTE_ARCHIVE="/tmp/sl101-grate-mesa25-musl-20261106.tar.gz"
STATE="/run/sl101-musl-sway-green-20261106"
SSH=(ssh -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=8)
SCP=(scp -q -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=8)
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

test -f "$ARCHIVE" || die "missing archive"
test "$(sha256sum "$ARCHIVE" | cut -d ' ' -f1)" = "$EXPECTED" || die "host SHA drift"
case "${1:---dry-run}" in
  --dry-run)
    "${SSH[@]}" "$TARGET" "uname -r; cat /etc/sl101-desktop-renderer.conf; cat /sys/block/mmcblk1/device/cid; cat /run/sl101-desktop.pid; ls -ld $PREFIX 2>/dev/null || true"
    printf 'DRY RUN only. Apply: %s --apply\n' "$0"
    exit 0
    ;;
  --apply) ;;
  *) die "usage: $0 [--dry-run|--apply]" ;;
esac

"${SSH[@]}" "$TARGET" "set -eu
  test \"\$(uname -r)\" = 7.0.1-postmarketos-grate
  test \"\$(cat /sys/block/mmcblk1/device/cid)\" = 035344534c31323880ac79a543010300
  grep -qx SL101_DESKTOP_RENDERER=grate /etc/sl101-desktop-renderer.conf
  grep -qx SL101_COMPOSITOR=sway /etc/sl101-desktop-renderer.conf
  grep -Fxq 'GRATE_PREFIX=$OLD_PREFIX' /usr/local/bin/sl101-desktop
  test ! -e $STATE
  /usr/local/sbin/sl101-renderer-verify >/dev/null
"
# Atomic upload and separate install prefix; no system .so or ld-musl.path replaced.
"${SCP[@]}" "$ARCHIVE" "$TARGET:$REMOTE_ARCHIVE"
"${SSH[@]}" "$TARGET" "set -eu
  test \"\$(sha256sum '$REMOTE_ARCHIVE' | cut -d ' ' -f1)\" = '$EXPECTED'
  if test ! -d '$PREFIX'; then
     tar -xzf '$REMOTE_ARCHIVE' -C /
  fi
  test -f '$PREFIX/lib/libgallium-25.0.7.so'
  LD_LIBRARY_PATH='$PREFIX/lib' /lib/ld-musl-armhf.so.1 --list '$PREFIX/lib/libEGL.so.1.0.0' >/dev/null
"
# Remote preparation: launcher is copied verbatim first, rollback disarmed only
# after exact pid+library-map proof and a successful Sway background command.
"${SSH[@]}" "$TARGET" sh -s <<'REMOTE'
set -eu
STATE=/run/sl101-musl-sway-green-20261106
LAUNCHER=/usr/local/bin/sl101-desktop
CFG=/home/user/.config/sway/config
OLD=/usr/local/lib/sl101-grate-38b7bd1f600d2889a3caeec609e7520842701eab8aa10193f98966ce4e33987c
NEW=/opt/grate-mesa25-musl-20261106
mkdir -m 700 "$STATE"
cp -p "$LAUNCHER" "$STATE/launcher.before"
cp -p "$CFG" "$STATE/sway-config.before"
# Keep rollback backups across reboot as /run is tmpfs.
test ! -e "$LAUNCHER.pre-musl-20261106"
test ! -e "$CFG.pre-musl-20261106"
cp -p "$LAUNCHER" "$LAUNCHER.pre-musl-20261106"
cp -p "$CFG" "$CFG.pre-musl-20261106"
sed "s|^GRATE_PREFIX=$OLD$|GRATE_PREFIX=$NEW|" "$LAUNCHER" > "$STATE/launcher.after"
grep -Fxq "GRATE_PREFIX=$NEW" "$STATE/launcher.after"
install -m 755 -o root -g root "$STATE/launcher.after" "$LAUNCHER"
cat >"$STATE/rollback.sh" <<'ROLLBACK'
#!/bin/sh
set -eu
STATE=/run/sl101-musl-sway-green-20261106
if [ -f "$STATE/success" ] || [ -f "$STATE/rolled-back" ]; then exit 0; fi
cp -p "$STATE/launcher.before" /usr/local/bin/sl101-desktop
cp -p "$STATE/sway-config.before" /home/user/.config/sway/config
touch "$STATE/rolled-back"
rc-service sl101-desktop restart >>"$STATE/rollback.log" 2>&1 || true
ROLLBACK
chmod 700 "$STATE/rollback.sh"
# No persistent daemon: fails back after 90s if supervisor disappears.
nohup sh -c "sleep 90; sh '$STATE/rollback.sh'" > "$STATE/watchdog.log" 2>&1 < /dev/null &
echo "ROLLBACK_ARMED_PID=$!"
REMOTE

# Restart only the OpenRC-owned desktop; must not spawn a second DRM compositor.
if ! "${SSH[@]}" "$TARGET" "rc-service sl101-desktop restart"; then
  "${SSH[@]}" "$TARGET" "sh '$STATE/rollback.sh'" || true
  die "restart failed; rollback requested"
fi

healthy=0
for _attempt in $(seq 1 28); do
  if "${SSH[@]}" "$TARGET" sh -s <<'HEALTH' >/dev/null 2>&1
set -eu
PID=$(cat /run/sl101-desktop.pid)
test -r "/proc/$PID/maps"
tr '\000' '\n' <"/proc/$PID/environ" | grep -Fxq 'WLR_RENDERER=gles2'
grep -Fq '/opt/grate-mesa25-musl-20261106/lib/libgallium-25.0.7.so' "/proc/$PID/maps"
grep -Fq '/opt/grate-mesa25-musl-20261106/lib/libEGL.so.1.0.0' "/proc/$PID/maps"
SOCK=$(find /run/sl101-desktop-user -maxdepth 1 -name 'sway-ipc.*.sock' | head -1)
test -S "$SOCK"
SWAYSOCK="$SOCK" XDG_RUNTIME_DIR=/run/sl101-desktop-user swaymsg -t get_outputs >/dev/null
HEALTH
  then healthy=1; break; fi
  sleep 1
done
if test "$healthy" != 1; then
  "${SSH[@]}" "$TARGET" "sh '$STATE/rollback.sh'" || true
  die "Sway never reached EGL+Grate+IPC health; rollback requested"
fi

# Green background only after verifiably loading the NEW Mesa libraries.
if ! "${SSH[@]}" "$TARGET" sh -s <<'GREEN'
set -eu
STATE=/run/sl101-musl-sway-green-20261106
CFG=/home/user/.config/sway/config
SOCK=$(find /run/sl101-desktop-user -maxdepth 1 -name 'sway-ipc.*.sock' | head -1)
test -S "$SOCK"
if ! grep -Fxq 'output LVDS-1 bg #00b050 solid_color' "$CFG"; then
    printf '\n# New Mesa Grate musl visual indicator (2026-11-06)\noutput LVDS-1 bg #00b050 solid_color\n' >> "$CFG"
fi
SWAYSOCK="$SOCK" XDG_RUNTIME_DIR=/run/sl101-desktop-user swaymsg -t command 'output LVDS-1 bg #00b050 solid_color' | grep -q '"success": true'
PID=$(cat /run/sl101-desktop.pid)
grep -Fq '/opt/grate-mesa25-musl-20261106/lib/libgallium-25.0.7.so' "/proc/$PID/maps"
grep -Fq '/opt/grate-mesa25-musl-20261106/lib/libEGL.so.1.0.0' "/proc/$PID/maps"
touch "$STATE/success"
echo "SUCCESS_NEW_MESA_SWAY_AND_GREEN_BG PID=$PID"
GREEN
then
  "${SSH[@]}" "$TARGET" "sh '$STATE/rollback.sh'" || true
  die "Green swaybg command failed; rollback requested"
fi
"${SSH[@]}" "$TARGET" "PID=\$(cat /run/sl101-desktop.pid); echo SWAY_PID=\$PID; grep -m 1 -E '/opt/grate-mesa25-musl-20261106/lib/lib(gallium|EGL)' /proc/\$PID/maps; cat '$STATE/success' >/dev/null; ls -l '$STATE/launcher.before' '$STATE/sway-config.before'"
printf 'SUCCESS: Sway now uses new musl Mesa and green background; preserved rollback in %s\n' "$STATE"
