#!/bin/sh
# Hash-checked install of the *launcher only*. No package, boot or renderer change.
set -eu

TARGET=user@192.168.23.106
# Privileged remote steps run via sudo -n as the device user.
SOURCE=scripts/sl101-video-play.sh
KNOWN_HOSTS=${SL101_KNOWN_HOSTS:-tmp/sl101-nura/deploy/known-hosts-sl101}
DEST=/usr/local/bin/sl101-video-play
EXPECTED_CID=035344534c31323880ac79a543010300
EXPECTED_ROOT_UUID=6dd3675d-b5cf-41bd-9262-103c59321451
EXPECTED_KERNEL=7.0.1-postmarketos-grate
APPLY=0

usage() {
    cat <<'EOF'
usage: sh scripts/sl101-video-deploy.sh [--apply]
Default is host-only review. --apply deploys only the software video player
to the pinned SL101 after exact CID/kernel/root UUID and flock gates.
Does not install mpv, alter boot/graphics/audio, or overwrite an existing player.
EOF
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --apply) APPLY=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *) usage >&2; echo "unknown argument: $1" >&2; exit 2 ;;
    esac
done

[ -r "$SOURCE" ] || { echo "missing source $SOURCE" >&2; exit 1; }
command -v sha256sum >/dev/null 2>&1 || exit 1
SHA=$(sha256sum "$SOURCE" | awk '{print $1}')
printf 'SL101 video launcher deployment\n'
printf '  target: %s\n  destination: %s\n' "$TARGET" "$DEST"
printf '  SHA256: %s\n  expected CID: %s\n' "$SHA" "$EXPECTED_CID"
printf '  expected kernel: %s\n  expected root UUID: %s\n' "$EXPECTED_KERNEL" "$EXPECTED_ROOT_UUID"
printf '  effect: install launcher only; no player package, compositor or GPU changes\n'
[ "$APPLY" -eq 1 ] || exit 0

[ -r "$KNOWN_HOSTS" ] || {
    echo "pinned known-hosts unavailable: $KNOWN_HOSTS" >&2
    exit 1
}
# Keep the same pinned SSH identity policy as other SL101 lanes.
ssh_opts="-o BatchMode=yes -o IdentitiesOnly=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=yes"
# shellcheck disable=SC2086
ssh $ssh_opts -o "UserKnownHostsFile=$KNOWN_HOSTS" "$TARGET" "test -r /sys/block/mmcblk1/device/cid && test \"\$(cat /sys/block/mmcblk1/device/cid)\" = '$EXPECTED_CID' && test \"\$(uname -r)\" = '$EXPECTED_KERNEL' && test ! -e '$DEST' && test ! -L '$DEST'"

stage=
cleanup() {
    [ -n "$stage" ] || return 0
    # shellcheck disable=SC2086
    ssh $ssh_opts -o "UserKnownHostsFile=$KNOWN_HOSTS" "$TARGET" "rm -f -- '$stage'" >/dev/null 2>&1 || true
}
trap cleanup EXIT HUP INT TERM

# shellcheck disable=SC2086
stage=$(ssh $ssh_opts -o "UserKnownHostsFile=$KNOWN_HOSTS" "$TARGET" 'umask 077; mktemp /var/tmp/sl101-video-play.XXXXXXXX')
case "$stage" in /var/tmp/sl101-video-play.*) ;; *) echo 'unexpected remote stage path' >&2; exit 1 ;; esac
# shellcheck disable=SC2086
scp $ssh_opts -o "UserKnownHostsFile=$KNOWN_HOSTS" "$SOURCE" "$TARGET:$stage"

# shellcheck disable=SC2086
ssh $ssh_opts -o "UserKnownHostsFile=$KNOWN_HOSTS" "$TARGET" "sudo -n sh -s -- '$SHA' '$stage'" <<'REMOTE'
#!/bin/sh
set -eu
expected=$1
stage=$2
dest=/usr/local/bin/sl101-video-play
lock=/run/lock/sl101-nura-qualification.lock

exec 9>"$lock"
flock -n 9 || { echo 'qualification lock busy' >&2; exit 75; }
[ "$(cat /sys/block/mmcblk1/device/cid)" = '035344534c31323880ac79a543010300' ]
[ "$(uname -r)" = '7.0.1-postmarketos-grate' ]
root_uuid=$(findmnt -nro UUID / 2>/dev/null || true)
if [ -z "$root_uuid" ]; then
    source=$(findmnt -nro SOURCE / 2>/dev/null || true)
    root_uuid=$(blkid -s UUID -o value "$source" 2>/dev/null || true)
fi
[ "$root_uuid" = '6dd3675d-b5cf-41bd-9262-103c59321451' ]
[ -f "$stage" ] && [ ! -L "$stage" ] && [ ! -e "$dest" ] && [ ! -L "$dest" ]
echo "$expected  $stage" | sha256sum -c - >/dev/null
tmp=/usr/local/bin/.sl101-video-play.$$.tmp
trap 'rm -f "$tmp"' EXIT HUP INT TERM
install -m 0755 "$stage" "$tmp"
echo "$expected  $tmp" | sha256sum -c - >/dev/null
# Hard link is atomic and cannot clobber an existing destination.
ln "$tmp" "$dest"
echo "$expected  $dest" | sha256sum -c - >/dev/null
printf 'installed %s (%s)\n' "$dest" "$expected"
REMOTE
