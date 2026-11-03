#!/usr/bin/env bash
# Lane 06: glibc ARMHF chroot only. No host Mesa or labwc prefix writes.
# Default is read-only dry-run. Apply is deliberately disabled until authenticated
# native ownership/lease and complete rollback are verified.
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
SOURCE="$ROOT/build/mesa-grate-clean/output/opt/grate-mesa25-clean/lib/arm-linux-gnueabihf"
PREFIX=/opt/sl101-cog-wpe-debian/opt/grate-mesa25-clean/lib/arm-linux-gnueabihf
TARGET=user@192.168.23.106
KERNEL=7.0.1-postmarketos-grate
EXPECTED_CID=
CID_DEVICE=mmcblk1
MANIFEST=
HANDOFF=
APPLY=0
usage() {
    echo "Usage: $0 --manifest FILE --expected-cid HEX [--cid-device mmcblkN] [--target user@HOST] [--handoff-file FILE --apply]" >&2
}
while (($#)); do
    case "$1" in
        --manifest|--expected-cid|--cid-device|--target|--handoff-file)
            (($# >= 2)) || { usage; exit 2; }
            case "$1" in
                --manifest) MANIFEST=$2 ;;
                --expected-cid) EXPECTED_CID=$2 ;;
                --cid-device) CID_DEVICE=$2 ;;
                --target) TARGET=$2 ;;
                --handoff-file) HANDOFF=$2 ;;
            esac
            shift 2 ;;
        --apply) APPLY=1; shift ;;
        --help|-h) usage; exit 0 ;;
        *) usage; exit 2 ;;
    esac
done
# A local text file is not an authoritative ownership/lease record. In particular,
# arbitrary grep matches MUST NOT authorize remote staging or mutation.
# Fail before even the read-only SSH identity probe on an attempted apply.
if (( APPLY )); then
    echo 'DENIED: --apply disabled pending native lease/owner/target verification and atomic bundle rollback qualification' >&2
    exit 3
fi
[[ -f "$MANIFEST" && -d "$SOURCE" ]] || { echo "Missing source or SHA256 manifest" >&2; exit 1; }
[[ "$EXPECTED_CID" =~ ^[[:xdigit:]]{32}$ ]] || { echo "Exact 32-character SD CID required" >&2; exit 1; }
[[ "$CID_DEVICE" =~ ^mmcblk[0-9]+$ ]] || { echo "Invalid SD device" >&2; exit 1; }
[[ "$TARGET" =~ ^[a-zA-Z0-9_-]+@[a-zA-Z0-9_.-]+$ ]] || { echo "Invalid SSH target" >&2; exit 1; }
files=()
while read -r hash filename extra; do
    [[ -z "${hash:-}" || "$hash" == \#* ]] && continue
    [[ -z "${extra:-}" && "$hash" =~ ^[a-f0-9]{64}$ ]] || { echo "Malformed manifest" >&2; exit 1; }
    case "$filename" in
        libEGL.so.1.0.0|libgallium-25.0.7.so|libGLESv2.so.2.0.0|libgbm.so.1.0.0|libdrm_tegra.so.0.0.0|gbm/dri_gbm.so) ;;
        *) echo "Disallowed chroot artifact: $filename" >&2; exit 1 ;;
    esac
    [[ -f "$SOURCE/$filename" && ! -L "$SOURCE/$filename" ]] || { echo "Missing/linked source: $filename" >&2; exit 1; }
    actual=$(sha256sum "$SOURCE/$filename")
    [[ "${actual%% *}" == "$hash" ]] || { echo "SHA256 mismatch: $filename" >&2; exit 1; }
    for old in "${files[@]}"; do
        [[ "$old" != "$filename" ]] || { echo "Duplicate manifest path" >&2; exit 1; }
    done
    files+=("$filename")
done < "$MANIFEST"
(("${#files[@]}" > 0)) || { echo "Empty manifest" >&2; exit 1; }
# Verify physical identity even for dry-run. No writes on this path.
ssh -o BatchMode=yes "$TARGET" sh -s -- "$EXPECTED_CID" "$CID_DEVICE" "$KERNEL" "$PREFIX" <<'REMOTE'
set -eu
expected=$1 dev=$2 kernel=$3 prefix=$4
[ "$(uname -r)" = "$kernel" ] || { echo 'Kernel mismatch' >&2; exit 1; }
[ -f "/sys/block/$dev/device/cid" ] || { echo 'Missing SD CID' >&2; exit 1; }
[ "$(cat "/sys/block/$dev/device/cid")" = "$expected" ] || { echo 'SD CID mismatch' >&2; exit 1; }
[ -d "$prefix" ] || { echo 'Missing chroot Mesa prefix' >&2; exit 1; }
[ "$(readlink -f "$prefix")" = "$prefix" ] || { echo 'Symlinked/noncanonical target prefix' >&2; exit 1; }
echo "Identity OK: kernel=$kernel, CID=$expected, destination=$prefix"
REMOTE
printf 'Validated %d local hashes for chroot-only prefix %s\n' "${#files[@]}" "$PREFIX"
echo 'Dry-run complete; no device state changed.'
exit 0
