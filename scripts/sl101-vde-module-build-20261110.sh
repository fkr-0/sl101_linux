#!/usr/bin/env bash
# Rebuild only tegra-vde.ko against the EXACT dmafix1 production-derived
# config/Module.symvers. No device access, kernel image replacement, or reboot.
set -Eeuo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
base="$repo/work/sl101-prod-dma-init-20261110"
lane="$repo/work/sl101-vde-modfix2-20261110"
archive="$repo/work/sl101-0076-dontkmap-kernel-20261109/pmos-source-dl/linux-postmarketos-grate-stable.tar.gz"
apkbuild="$repo/tmp/sl101-nura-pmaports/device/testing/linux-postmarketos-grate/APKBUILD"
dma_patch="$repo/patches/linux-postmarketos-grate-7.0.1/dmafix1/0002-dma-direct-zero-no-kmap.patch"
vde_patch="$repo/patches/linux-postmarketos-grate-7.0.1/vde-modfix2/0001-media-tegra-vde-async-semaphore.patch"
rel=7.0.1-postmarketos-grate-dmafix1
jobs="${SL101_VDE_BUILD_JOBS:-6}"
case "$jobs" in ''|*[!0-9]*) echo 'invalid job count' >&2; exit 64;; esac
(( jobs >= 1 && jobs <= 12 )) || { echo 'job count must be 1..12' >&2; exit 64; }

[[ -f "$archive" && -r "$apkbuild" && -f "$dma_patch" && -f "$vde_patch" ]]
[[ -f "$base/out/Module.symvers" ]] || { echo 'missing exact base Module.symvers' >&2; exit 65; }
[[ -f "$base/out/arch/arm/boot/zImage" ]] || { echo 'missing dmafix1 build' >&2; exit 65; }
[[ -f "$base/release/lib/modules/$rel/kernel/drivers/media/platform/nvidia/tegra-vde/tegra-vde.ko.zst" ]] ||
    { echo 'missing original VDE module' >&2; exit 65; }
[[ "$(cat "$base/out/include/config/kernel.release")" == "$rel" ]] ||
    { echo 'kernel release mismatch' >&2; exit 65; }
grep -qx 'CONFIG_VIDEO_TEGRA_VDE=m' "$base/out/.config"
[[ "$(sha256sum "$dma_patch" | cut -d' ' -f1)" == b0796b4d6b50feebf0a6281833fbe468a8f89c3a1b9c31747aa9bf6a5b99c96b ]] ||
    { echo 'dmafix1 patch changed' >&2; exit 65; }
want="$(awk '/linux-postmarketos-grate-stable.tar.gz/{print $1}' "$apkbuild")"
[[ -n "$want" && "$(sha512sum "$archive" | cut -d' ' -f1)" == "$want" ]] ||
    { echo 'source archive provenance mismatch' >&2; exit 65; }
[[ ! -e "$lane/out" && ! -e "$lane/stage" ]] ||
    { echo 'existing candidate output: refusing overwrite' >&2; exit 66; }
[[ "$(df --output=avail -k "$repo" | tail -1)" -gt 2200000 ]] ||
    { echo 'not enough host disk for output copy' >&2; exit 66; }
mkdir -p "$lane"
source="$(mktemp -d -p /tmp sl101-vde-modfix2-source.XXXXXXXX)"
cleanup() {
    if [[ "${SL101_VDE_KEEP_SOURCE:-0}" != 1 ]]; then
        rm -rf -- "$source"
    else
        printf 'source retained for review: %s\n' "$source"
    fi
}
trap cleanup EXIT

printf 'SOURCE_SHA512=%s\n' "$want"
tar -xzf "$archive" -C "$source" --strip-components=1
patch --batch --forward -d "$source" -p1 < "$dma_patch"
patch --batch --forward -d "$source" -p1 < "$vde_patch"
cp -a "$base/out" "$lane/out"
out="$lane/out"
# Only the original tegra_vde module is rebuilt; the kernel image and
# every other module remain the proven dmafix1 build.
MAKE=(make -C "$source" O="$out" ARCH=arm LLVM=1 CROSS_COMPILE=arm-linux-gnueabi-)
"${MAKE[@]}" -j"$jobs" M=drivers/media/platform/nvidia/tegra-vde modules
"${MAKE[@]}" M=drivers/media/platform/nvidia/tegra-vde modules_install \
    INSTALL_MOD_PATH="$lane/stage" INSTALL_MOD_STRIP=1
candidate="$(find "$lane/stage/lib/modules/$rel" -type f -name 'tegra-vde.ko.zst' -print -quit)"
[[ -n "$candidate" && -f "$candidate" ]] || { echo 'patched VDE module missing' >&2; exit 67; }
[[ "$(modinfo -F vermagic "$candidate")" == "$rel "* ]] ||
    { echo 'patched module ABI release mismatch' >&2; exit 67; }
base_mod="$base/release/lib/modules/$rel/kernel/drivers/media/platform/nvidia/tegra-vde/tegra-vde.ko.zst"
[[ "$(sha256sum "$candidate" | cut -d' ' -f1)" != "$(sha256sum "$base_mod" | cut -d' ' -f1)" ]] ||
    { echo 'VDE module unchanged despite patch' >&2; exit 67; }
printf 'BASE_VDE_SHA256=%s\n' "$(sha256sum "$base_mod" | cut -d' ' -f1)"
printf 'PATCHED_VDE_SHA256=%s\n' "$(sha256sum "$candidate" | cut -d' ' -f1)"
printf 'PATCH_SHA256=%s\n' "$(sha256sum "$vde_patch" | cut -d' ' -f1)"
printf 'MODULE_VERMAGIC=%s\n' "$(modinfo -F vermagic "$candidate")"
printf 'VDE_MODULE_BUILD_SUCCESS=%s\n' "$candidate"
