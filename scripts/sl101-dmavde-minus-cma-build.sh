#!/usr/bin/env bash
# Build the three-patch A/B benchmark control with a unique kernel ABI.
# All build flags/config and DTB source are the same as the four-patch RC.
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
B="$REPO/work/sl101-prod-dmavde-minus-cma-20261110"
SRC="$B/source"
OUT="$B/out"
INSTALL="$B/modules"
REL="7.0.1-postmarketos-grate-dmavde1-minus-cma"
JOBS="${SL101_JOBS:-12}"
test -f "$SRC/.sl101-three-patches-minus-cma-applied" || {
  echo "Unverified minus-CMA source; run prepare first" >&2; exit 72;
}
test ! -e "$SRC/.sl101-four-patches-applied"
grep -q 'static bool cached_capture;' "$SRC/drivers/media/platform/nvidia/tegra-vde/v4l2.c"
mkdir -p "$OUT"
if [[ ! -e "$OUT/.config" ]]; then
  cp -p "$B/backup/production.config" "$OUT/.config"
fi
"$SRC/scripts/config" --file "$OUT/.config" --set-str LOCALVERSION "-postmarketos-grate-dmavde1-minus-cma" -d DEBUG_INFO_DWARF5 -d DEBUG_INFO_DWARF4 -d DEBUG_INFO_BTF -d DEBUG_INFO_BTF_MODULES -d DEBUG_INFO_COMPRESSED_ZLIB -d DEBUG_INFO_COMPRESSED_ZSTD -e DEBUG_INFO_NONE
make -C "$SRC" O="$OUT" ARCH=arm LLVM=1 CROSS_COMPILE=arm-linux-gnueabi- olddefconfig
grep -qx 'CONFIG_LOCALVERSION="-postmarketos-grate-dmavde1-minus-cma"' "$OUT/.config"
make -C "$SRC" O="$OUT" ARCH=arm LLVM=1 CROSS_COMPILE=arm-linux-gnueabi- -j"$JOBS" zImage modules dtbs
test "$(cat "$OUT/include/config/kernel.release")" = "$REL"
make -C "$SRC" O="$OUT" ARCH=arm LLVM=1 CROSS_COMPILE=arm-linux-gnueabi- -j"$JOBS" modules_install INSTALL_MOD_PATH="$INSTALL" INSTALL_MOD_STRIP=1
test -f "$OUT/arch/arm/boot/zImage"
test -f "$OUT/arch/arm/boot/dts/nvidia/tegra20-asus-sl101.dtb"
echo "CONTROL_BUILD_SUCCESS RELEASE=$REL"
sha256sum "$OUT/arch/arm/boot/zImage" "$OUT/arch/arm/boot/dts/nvidia/tegra20-asus-sl101.dtb"
