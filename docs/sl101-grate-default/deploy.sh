#!/bin/sh
set -eu
OUT=/var/lib/sl101-grate-default/20261003
P=/opt/grate-mesa25-qualified-541e60b7ef948852be32f9d75c22f5f8aaa8e2e6e3548298aae2f4d0fc2c7815
exec 9>/run/lock/sl101-nura-qualification.lock
flock -n 9
[ "$(cat /sys/block/mmcblk1/device/cid)" = 035344534c31323880ac79a543010300 ]
[ "$(uname -r)" = 7.0.1-postmarketos-grate ]
[ "$(sha256sum /usr/local/bin/sl101-desktop | awk '{print $1}')" = f3715f69622fa43405cffa6e9f83ce510ce54ae61cde77c0240b21fb26cfda54 ]
(cd "$P" && sha256sum -c runtime.sha256)
[ ! -e "$OUT" ]
mkdir -p "$OUT"
cp -p /usr/local/bin/sl101-desktop "$OUT/pixman-wrapper"
cp -p /etc/init.d/sl101-desktop "$OUT/pixman-init"
dmesg >"$OUT/dmesg.before"
rollback() {
    code=$?
    trap - EXIT HUP INT TERM
    if [ "$code" -ne 0 ]; then
        rc-service sl101-desktop stop || true
        cp "$OUT/pixman-wrapper" /usr/local/bin/sl101-desktop
        printf 'SL101_DESKTOP_RENDERER=pixman\n' >/etc/sl101-desktop-renderer.conf
        rc-service sl101-desktop start 9>&-
    fi
    exit "$code"
}
trap rollback EXIT
trap 'exit 143' TERM
trap 'exit 130' INT
cp /tmp/sl101-desktop-grate-default /usr/local/bin/sl101-desktop.new
chmod 755 /usr/local/bin/sl101-desktop.new
mv /usr/local/bin/sl101-desktop.new /usr/local/bin/sl101-desktop
cp /tmp/sl101-desktop-renderer.conf /etc/sl101-desktop-renderer.conf
rc-service sl101-desktop restart 9>&-
i=0
while [ "$i" -lt 30 ]; do
    pid=$(cat /run/sl101-desktop.pid 2>/dev/null || true)
    if [ -n "$pid" ] && [ -r "/proc/$pid/maps" ] &&
       grep -q "$P/lib/libgallium" "/proc/$pid/maps" &&
       pidof nuraloumi-panel >/dev/null && test -S /run/user/0/wayland-0; then
        break
    fi
    sleep 1
    i=$((i+1))
done
[ "$i" -lt 30 ]
[ "$(cat "/proc/$pid/comm")" = labwc ]
tr '\0' '\n' <"/proc/$pid/environ" >"$OUT/renderer.env"
grep -qx WLR_RENDERER=gles2 "$OUT/renderer.env"
grep -q "$P/lib/libgallium" "/proc/$pid/maps"
cp "/proc/$pid/maps" "$OUT/renderer.maps"
sleep 30
kill -0 "$pid"
rc-service sl101-desktop status
pidof nuraloumi-panel
rc-service sl101-wayvnc restart 9>&-
sleep 3
rc-service sl101-wayvnc status
pidof wayvnc
dmesg >"$OUT/dmesg.after"
diff -u "$OUT/dmesg.before" "$OUT/dmesg.after" >"$OUT/dmesg.diff" || true
grep -Ei '^\+.*(host1x.*(fault|reset|timeout)|gr3d.*(fault|reset|timeout)|gpu.*(fault|reset|timeout)|oom|killed process|segfault)' "$OUT/dmesg.diff" >"$OUT/faults" || true
[ ! -s "$OUT/faults" ]
printf 'PASS pid=%s kernel=%s renderer=gles2 prefix=%s\n' "$pid" "$(uname -r)" "$P" | tee "$OUT/result"
