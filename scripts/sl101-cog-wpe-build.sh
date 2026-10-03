#!/bin/sh
set -eu

BASE_ROOTFS=work/sl101-firefox-debian-20261003/base-rootfs.tar.gz
BASE_ROOTFS_SHA256=9312e8243384574a9ab866dedfdd93bccf5359b4163b9bf22db6a770bc0afdc9
GRATE_OVERLAY=
OUT=work/sl101-cog-wpe-20261003/bundle
ALLOW_LEGACY_GRATE=0
LEGACY_GRATE_SHA256=366aadb732af038ccc527a1a5a5ccb788532b39a93e0772f5105c9fea911da66

usage() {
    cat <<'EOF'
usage: scripts/sl101-cog-wpe-build.sh [options]
  --base-rootfs PATH
  --grate-overlay PATH
  --out DIR
  --allow-legacy-grate
EOF
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --base-rootfs) BASE_ROOTFS=$2; shift 2 ;;
        --grate-overlay) GRATE_OVERLAY=$2; shift 2 ;;
        --out) OUT=$2; shift 2 ;;
        --allow-legacy-grate) ALLOW_LEGACY_GRATE=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *) echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
    esac
done

[ -f "$BASE_ROOTFS" ] || { echo "missing base rootfs: $BASE_ROOTFS" >&2; exit 1; }
base_sha=$(sha256sum "$BASE_ROOTFS" | awk '{print $1}')
[ "$base_sha" = "$BASE_ROOTFS_SHA256" ] || {
    echo "base rootfs hash mismatch: got $base_sha expected $BASE_ROOTFS_SHA256" >&2
    exit 1
}

mkdir -p "$OUT"
cp "$BASE_ROOTFS" "$OUT/base-rootfs.tar.gz"

grate_sha=
grate_status=absent
if [ -n "$GRATE_OVERLAY" ]; then
    [ -f "$GRATE_OVERLAY" ] || { echo "missing Grate overlay: $GRATE_OVERLAY" >&2; exit 1; }
    grate_sha=$(sha256sum "$GRATE_OVERLAY" | awk '{print $1}')
    if [ "$grate_sha" = "$LEGACY_GRATE_SHA256" ] && [ "$ALLOW_LEGACY_GRATE" -ne 1 ]; then
        echo "refusing archived legacy Grate overlay $grate_sha" >&2
        echo "rebuild the current accepted Grate fixes for Debian armhf/glibc" >&2
        exit 1
    fi
    tar -tf "$GRATE_OVERLAY" | grep -Eq '(^/|(^|/)\.\.(/|$))' && {
        echo "unsafe Grate archive paths" >&2
        exit 1
    }
    tar -tf "$GRATE_OVERLAY" | grep -q 'usr/lib/arm-linux-gnueabihf/' || {
        echo "overlay does not look like Debian armhf/glibc Mesa" >&2
        exit 1
    }
    cp "$GRATE_OVERLAY" "$OUT/grate-glibc.tar.gz"
    if [ "$grate_sha" = "$LEGACY_GRATE_SHA256" ]; then
        grate_status=legacy-diagnostic-only
    else
        grate_status=current-candidate-review-required
    fi
fi

cat >"$OUT/manifest.env" <<EOF
SL101_COG_BUNDLE_VERSION=1
SL101_BASE_ROOTFS_SHA256=$base_sha
SL101_DEBIAN_SNAPSHOT=20261003T000000Z
SL101_COG_VERSION=0.18.5-1
SL101_WPE_VERSION=2.54.0-2
SL101_GRATE_OVERLAY_SHA256=$grate_sha
SL101_GRATE_OVERLAY_STATUS=$grate_status
SL101_TARGET_CID=035344534c31323880ac79a543010300
SL101_TARGET_KERNEL=7.0.1-postmarketos-grate
EOF

(
    cd "$OUT"
    sha256sum base-rootfs.tar.gz manifest.env >SHA256SUMS
    [ ! -f grate-glibc.tar.gz ] || sha256sum grate-glibc.tar.gz >>SHA256SUMS
)

printf 'prepared %s\n' "$OUT"
cat "$OUT/manifest.env"
