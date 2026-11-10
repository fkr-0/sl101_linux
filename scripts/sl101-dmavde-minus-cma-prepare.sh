#!/usr/bin/env bash
# A/B control: reproduce the production source while excluding ONLY the CMA remap.
# Host-only: no SSH, flash, reboot, KMS or running-kernel changes.
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
A="$REPO/work/sl101-prod-dmavde-rc3-20261110"
B="$REPO/work/sl101-prod-dmavde-minus-cma-20261110"
SRC="/tmp/sl101-prod-dmavde-minus-cma-20261110-source"
ARCHIVE="$REPO/work/sl101-0076-dontkmap-kernel-20261109/pmos-source-dl/linux-postmarketos-grate-stable.tar.gz"
ARCHIVE_SHA512="fa6a723db93d0c4c799ca8fb69a37ce13cc98a80ff688bc45dea7bd6d36df05b8f0deaa15a416e271a4ea0c5bb2097e63fc2d0a02903f11e6c404fbec82718a2"
CONFIG_SHA256="6b09863a5f4356ce615f7d5d4cdecbba4cd2cc208c34125954af9534648f9248"
PATCHES=(
  0002-dma-direct-zero-no-kmap.patch
  0003-vde-cached-capture-v2.patch
  0004-vde-async-semaphore.patch
)
mkdir -p "$B/patches" "$B/backup" "$B/evidence"
for name in "${PATCHES[@]}"; do
  cmp "$REPO/patches/linux-postmarketos-grate-7.0.1/dmavde1/$name" "$A/patches/$name"
  cp -n "$REPO/patches/linux-postmarketos-grate-7.0.1/dmavde1/$name" "$B/patches/$name"
  cmp "$B/patches/$name" "$A/patches/$name"
done
test ! -e "$B/patches/0001-arm-dma-cma-no-kmap-attributes.patch"
cp -n "$A/backup/production.config" "$B/backup/production.config"
printf '%s  %s\n' "$CONFIG_SHA256" "$B/backup/production.config" | sha256sum -c -
printf '%s  %s\n' "$ARCHIVE_SHA512" "$ARCHIVE" | sha512sum -c -
if [[ -L "$B/source" ]]; then
  [[ "$(readlink "$B/source")" == "$SRC" ]] || { echo "Unexpected source symlink" >&2; exit 72; }
elif [[ -e "$B/source" ]]; then
  echo "Refusing preexisting non-symlink source" >&2; exit 72
else
  ln -s "$SRC" "$B/source"
fi
MARKER="$SRC/.sl101-three-patches-minus-cma-applied"
if [[ -f "$MARKER" ]]; then
  for name in "${PATCHES[@]}"; do
    patch --batch --dry-run --fuzz=0 -R -p1 -d "$SRC" < "$B/patches/$name" >/dev/null
  done
  patch --batch --dry-run --fuzz=0 -p1 -d "$SRC" < "$A/patches/0001-arm-dma-cma-no-kmap-attributes.patch" >/dev/null
  echo "CONTROL_SOURCE_ALREADY_PREPARED"
  exit 0
fi
if [[ -e "$SRC" ]]; then
  echo "Refusing unverified preexisting control source tree $SRC" >&2
  exit 72
fi
mkdir -p "$SRC"
tar -xzf "$ARCHIVE" -C "$SRC" --strip-components=1
for name in "${PATCHES[@]}"; do
  patch --dry-run --fuzz=0 --batch -p1 -d "$SRC" < "$B/patches/$name"
  patch --fuzz=0 --batch -p1 -d "$SRC" < "$B/patches/$name"
done
# It must still accept the omitted CMA patch with zero fuzz.
patch --dry-run --fuzz=0 --batch -p1 -d "$SRC" < "$A/patches/0001-arm-dma-cma-no-kmap-attributes.patch" >/dev/null
sha256sum "$B"/patches/*.patch > "$B/evidence/patch-sha256.txt"
printf '%s\n' "Three production patches only: DMA zeroing, VDE cached capture v2, VDE async semaphore" > "$MARKER"
echo "CONTROL_SOURCE_READY"
