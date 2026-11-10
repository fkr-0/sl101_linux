#!/usr/bin/env bash
set -euo pipefail
# Host-only production source extraction; no device changes.
R="$(cd "$(dirname "$0")/.." && pwd)/work/sl101-prod-dmavde-rc3-20261110"
REPO="$(cd "$R/../.." && pwd)"
SRC="/tmp/sl101-prod-dmavde-rc3-20261110-source"
ARCHIVE="$REPO/work/sl101-0076-dontkmap-kernel-20261109/pmos-source-dl/linux-postmarketos-grate-stable.tar.gz"
EXPECTED_SHA512="fa6a723db93d0c4c799ca8fb69a37ce13cc98a80ff688bc45dea7bd6d36df05b8f0deaa15a416e271a4ea0c5bb2097e63fc2d0a02903f11e6c404fbec82718a2"
EXPECTED_CONFIG_SHA256="6b09863a5f4356ce615f7d5d4cdecbba4cd2cc208c34125954af9534648f9248"
mkdir -p "$R/patches" "$R/backup" "$R/evidence"
# Track the real patch files in Git; the work lane is disposable.
for p in "$REPO"/patches/linux-postmarketos-grate-7.0.1/dmavde1/*.patch; do
  cp -n "$p" "$R/patches/"
done
if [[ ! -f "$R/backup/production.config" ]]; then
  cp "$REPO/work/sl101-prod-dma-init-20261110/backup-prod-7.0.1/device-export/boot/config" "$R/backup/production.config"
fi
echo "$EXPECTED_SHA512  $ARCHIVE" | sha512sum -c -
echo "$EXPECTED_CONFIG_SHA256  $R/backup/production.config" | sha256sum -c -
if [[ -L "$R/source" ]]; then
  [[ $(readlink "$R/source") == "$SRC" ]] || { echo 'unmanaged source link' >&2; exit 3; }
elif [[ -e "$R/source" ]]; then
  echo 'unmanaged source path' >&2; exit 4
else
  ln -s "$SRC" "$R/source"
fi
if [[ -e "$SRC/.sl101-four-patches-applied" ]]; then
  echo SOURCE_ALREADY_PREPARED
  exit 0
fi
if [[ -e "$SRC/Makefile" ]]; then
  echo 'Existing unverified source tree; refusing to apply twice' >&2
  exit 5
fi
mkdir -p "$SRC"
tar -xzf "$ARCHIVE" -C "$SRC" --strip-components=1
for name in 0001-arm-dma-cma-no-kmap-attributes.patch 0002-dma-direct-zero-no-kmap.patch 0003-vde-cached-capture-v2.patch 0004-vde-async-semaphore.patch; do
  patch --dry-run --fuzz=0 --batch -p1 -d "$SRC" < "$R/patches/$name"
  patch --fuzz=0 --batch -p1 -d "$SRC" < "$R/patches/$name"
done
sha256sum "$R"/patches/*.patch > "$R/evidence/patch-sha256.txt"
touch "$SRC/.sl101-four-patches-applied"
echo SOURCE_READY
