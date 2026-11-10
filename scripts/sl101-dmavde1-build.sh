#!/usr/bin/env bash
# Host-only: original 7.0.1-r4 source/config with DMA-CMA, DMA-direct and Tegra VDE v2.
set -euo pipefail
R="$(cd "$(dirname "$0")/.." && pwd)/work/sl101-prod-dmavde-rc3-20261110"
SRC="$R/source"; O="$R/out"; M="$R/modules"
REL="7.0.1-postmarketos-grate-dmavde1"
JOBS=$(printenv SL101_JOBS || printf 12)
[[ -e "$SRC/.sl101-four-patches-applied" ]] || { echo "source not provenance-verified" >&2; exit 3; }
grep -q 'static bool cached_capture;' "$SRC/drivers/media/platform/nvidia/tegra-vde/v4l2.c"
mkdir -p "$O"
if [[ ! -f "$O/.config" ]]; then
  cp -p "$R/backup/production.config" "$O/.config"
fi
"$SRC/scripts/config" --file "$O/.config" --set-str LOCALVERSION "-postmarketos-grate-dmavde1" -d DEBUG_INFO_DWARF5 -d DEBUG_INFO_DWARF4 -d DEBUG_INFO_BTF -d DEBUG_INFO_BTF_MODULES -d DEBUG_INFO_COMPRESSED_ZLIB -d DEBUG_INFO_COMPRESSED_ZSTD -e DEBUG_INFO_NONE
make -C "$SRC" O="$O" ARCH=arm LLVM=1 CROSS_COMPILE=arm-linux-gnueabi- olddefconfig
grep -q '^CONFIG_LOCALVERSION="-postmarketos-grate-dmavde1"$' "$O/.config"
make -C "$SRC" O="$O" ARCH=arm LLVM=1 CROSS_COMPILE=arm-linux-gnueabi- -j"$JOBS" zImage modules dtbs
test "$(cat "$O/include/config/kernel.release")" = "$REL"
make -C "$SRC" O="$O" ARCH=arm LLVM=1 CROSS_COMPILE=arm-linux-gnueabi- -j"$JOBS" modules_install INSTALL_MOD_PATH="$M" INSTALL_MOD_STRIP=1
echo "RELEASE=$(cat "$O/include/config/kernel.release")"
sha256sum "$O/arch/arm/boot/zImage" "$O/arch/arm/boot/dts/nvidia/tegra20-asus-sl101.dtb"
echo BUILD_SUCCESS
