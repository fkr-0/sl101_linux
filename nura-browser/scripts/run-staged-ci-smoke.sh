#!/bin/sh
# SPDX-License-Identifier: MIT
# Run only the *deployed GitHub-CI binary* on SL101 .106 using the existing
# mount-isolated/sandboxed Cog runtime headless test. No local ELF copies.
# --check is strictly read-only. --run requires independent explicit gate.
set -eu

release_sha=e0c2b0424c1244596bd0b2e9f40dd1ae54e968ac
ci_run=43032042301
tar_hash=a15c922ac9e8e49a499e4b128c42cadbfb4ce96f5e44d2ecf2acc1dc8259920a
core_hash=67b5a5d6961ccb4ee100e40a6cb8300571e6a986978fd20e2fd20381a2e3a06b
launcher_hash=c5ef1b3422dbc68949fe58b4d23dce49a5f0f400c405c3e78ddb85b66300b5e4
runner_hash=92fbbbb8383630e71092948519719eb93c8761f6dff450bdebce9cb2a7278b4c
expected_boot_id=48d4a72f-146f-43c7-a308-496466246821
expected_kernel=7.0.1-postmarketos-grate-dmavde1
expected_sd_cid=035344534c31323880ac79a543010300
expected_emmc_cid=7001004d4d43333247448d402a656e00
rel=/opt/nura-browser/releases/$release_sha
fail() { printf 'nura-ci-smoke: REFUSED: %s\n' "$*" >&2; exit 1; }
hash_file() { sha256sum "$1" | cut -d ' ' -f 1; }

[ "$#" -eq 1 ] || fail 'usage: run-staged-ci-smoke.sh --check|--run'
case "$1" in --check|--run) action=$1 ;; *) fail 'invalid operation' ;; esac
[ "$(hostname)" = sl101-nura ] || fail 'wrong physical hostname'
[ "$(uname -m)" = armv7l ] || fail 'wrong architecture'
[ "$(uname -r)" = "$expected_kernel" ] || fail 'kernel changed'
[ "$(cat /proc/sys/kernel/random/boot_id)" = "$expected_boot_id" ] ||
    fail 'device rebooted since CI staging receipt'
[ "$(cat /sys/block/mmcblk1/device/cid)" = "$expected_sd_cid" ] ||
    fail 'SD identity changed'
[ "$(cat /sys/block/mmcblk0/device/cid)" = "$expected_emmc_cid" ] ||
    fail 'eMMC identity changed'
[ "$(findmnt -n -o SOURCE /)" = /dev/mmcblk1p1 ] || fail 'root changed'
# No file is executed from release until the CI-STAGED provenance and two
# independently pinned binary digests have been verified.
[ -d "$rel" ] && [ ! -L "$rel" ] || fail 'CI release directory absent'
[ "$(stat -c %u "$rel")" = 0 ] || fail 'CI release not root-owned'
for f in CI-STAGED nurabrowser-ci.tar release/bin/nurabrowser-core release/bin/,browse; do
    [ -f "$rel/$f" ] && [ ! -L "$rel/$f" ] || fail "missing/symlinked $f"
    [ "$(stat -c %u "$rel/$f")" = 0 ] || fail "unowned release member $f"
done
for line in \
    NURABROWSER_CI_STAGED=true \
    "GIT_SHA=$release_sha" \
    "RUN_ID=$ci_run" \
    "TAR_SHA256=$tar_hash" \
    RUNTIME_QUALIFIED=false \
    ACTIVATED=false; do
    grep -Fxq "$line" "$rel/CI-STAGED" || fail "CI-STAGED mismatch: $line"
done
[ "$(hash_file "$rel/nurabrowser-ci.tar")" = "$tar_hash" ] ||
    fail 'original CI release tar SHA changed'
[ "$(hash_file "$rel/release/bin/nurabrowser-core")" = "$core_hash" ] ||
    fail 'CI browser core SHA changed'
[ "$(hash_file "$rel/release/bin/,browse")" = "$launcher_hash" ] ||
    fail 'CI launcher SHA changed'
# Qualification helper must be copied alongside this script from the
# exact reviewed repository version; it is not a product binary.
script_dir=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
runner=$script_dir/qualify-cog-runtime-headless.sh
[ -f "$runner" ] && [ ! -L "$runner" ] || fail 'runner missing/symlinked'
[ "$(hash_file "$runner")" = "$runner_hash" ] ||
    fail 'qualification runner SHA mismatch'
if [ "$action" = --check ]; then
    printf 'nura-ci-smoke: PASS read-only device/boot/CI provenance preflight\n'
    exit 0
fi
[ "$(id -u)" = 0 ] || fail '--run requires root (sudo -n)'
[ "§{NURABROWSER_NATIVE_HEADLESS_TEST:-}" = YES ] ||
    fail 'explicit NURABROWSER_NATIVE_HEADLESS_TEST=YES gate required'
# No existing browser instance may be disturbed by the qualifier.
if pgrep -x nurabrowser-core >/dev/null 2>&1; then
    fail 'another NuraBrowser process is running'
fi
stage=$(mktemp -d /tmp/nurabrowser-smoke-XXXXXXXX) || fail 'mktemp failed'
cleanup() {
    # The only writable location is our unique, real temporary directory.
    case "$stage" in /tmp/nurabrowser-smoke-????????) ;; *) return 1 ;; esac
    if [ -d "$stage" ] && [ ! -L "$stage" ]; then
        rm -rf -- "$stage"
    fi
}
trap 'cleanup' EXIT
trap 'exit 143' TERM
trap 'exit 130' INT
trap 'exit 129' HUP
install -m 0755 "$rel/release/bin/nurabrowser-core" "$stage/nurabrowser-core"
install -d -o 1000 -g 1000 -m 0700 "$stage/state"
chmod 0755 "$stage"
sh "$runner" --preflight "$stage" "$core_hash"
printf 'nura-ci-smoke: starting isolated CI ARMHF headless WPEPlatform with sandbox enabled\n'
sh "$runner" "$stage" "$core_hash"
