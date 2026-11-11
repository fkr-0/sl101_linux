#!/bin/sh
# SPDX-License-Identifier: MIT
# Executed INSIDE the CI Docker image, with /src read-only, /out writable.
set -eu

project=/src/nura-browser
out=/out
target=/out/build
sha=${GITHUB_SHA:-}
run=${GITHUB_RUN_ID:-}
attempt=${GITHUB_RUN_ATTEMPT:-1}
case "$sha" in *[!0-9a-f]*|'') echo 'Invalid CI SHA' >&2; exit 2 ;; esac
[ "${#sha}" -eq 40 ] || exit 2
case "$run:$attempt" in *[!0-9:]*|'') exit 2 ;; esac
[ -d "$project" ] && [ -d "$out" ] || exit 2
[ ! -e "$target" ] || { echo 'CI build target already exists' >&2; exit 2; }

python3 -m unittest discover -s "$project/tests" -p 'test_*.py' -q
sh "$project/src/engine/tests/run-host-smoke.sh"
sh "$project/src/navigation/tests/run-host-tests.sh"
sh "$project/src/control/tests/run-host-tests.sh"
sh "$project/tests/run-crosslane-host.sh"
sh "$project/tests/run-remote-host.sh"

sh "$project/scripts/build-armhf.sh" / "$target"

# Real ARMHF code runs under Cortex A9 with NEON/D32 explicitly disabled.
# This is only a targeted math/ABI probe, not full browser qualification.
arm-linux-gnueabihf-gcc -std=c11 -O0 -Wall -Wextra -Werror \
    -march=armv7-a -mfpu=vfpv3-d16 -mfloat-abi=hard \
    "$project/tests/isa/probe_tegra2_no_neon.c" -ldl -lm -o "$out/isa-probe"
qemu-arm -cpu cortex-a9,neon=off,vfp-d32=off -L / "$out/isa-probe" \
    >"$out/NO-NEON-QEMU.txt"
grep -q '^TEGRA2_NO_NEON_QEMU_PROBE=PASS$' "$out/NO-NEON-QEMU.txt"

python3 "$project/packaging/create-manifest.py" \
    --build-dir "$target" --output "$out/nurabrowser-artifacts.json"
mkdir -p "$out/release/bin"
install -m 0755 "$target/nurabrowser-core" "$out/release/bin/nurabrowser-core"
install -m 0755 "$project/scripts/launch.sh" "$out/release/bin/,browse"

dpkg-query -W -f='${Package}\t${Version}\t${Architecture}\n' \
    >"$out/BUILDER-PACKAGES.tsv"
arm-linux-gnueabihf-readelf -h "$out/release/bin/nurabrowser-core" \
    >"$out/ELF-HEADER.txt"
arm-linux-gnueabihf-readelf -A "$out/release/bin/nurabrowser-core" \
    >"$out/ELF-ATTRIBUTES.txt"
arm-linux-gnueabihf-readelf -d "$out/release/bin/nurabrowser-core" \
    >"$out/ELF-NEEDED.txt"

python3 - "$out" "$sha" "$run" "$attempt" <<'PY'
import hashlib, json, pathlib, sys
out=pathlib.Path(sys.argv[1])
sha,run,attempt=sys.argv[2:]
elf=out/'release/bin/nurabrowser-core'
launcher=out/'release/bin/,browse'
manifest=json.loads((out/'nurabrowser-artifacts.json').read_text())
assert manifest['status']=='static-armhf-audited-not-runtime-qualified'
actual={entry['install_path']:entry for entry in manifest['artifacts']}
for path,destination in [
    ('/usr/libexec/nura-browser/nurabrowser-core',elf),
    ('/usr/bin/,browse',launcher),
]:
    digest=hashlib.sha256(destination.read_bytes()).hexdigest()
    assert actual[path]['sha256']==digest and actual[path]['size']==destination.stat().st_size
receipt={
    'schema':'sl101.nurabrowser.github-ci.v1',
    'source_repo':'fkr-0/sl101_linux',
    'source_sha':sha,
    'run_id':run,
    'run_attempt':int(attempt),
    'wpe_debian_version':'2.54.0-2',
    'target':'armv7-linux-gnueabihf-vfpv3-d16-no-neon',
    'status':'static-armhf-audited-not-runtime-qualified',
    'browser_sha256':hashlib.sha256(elf.read_bytes()).hexdigest(),
    'launcher_sha256':hashlib.sha256(launcher.read_bytes()).hexdigest(),
}
(out/'release/CI-PROVENANCE.json').write_text(json.dumps(receipt,sort_keys=True,indent=2)+'\n')
(out/'release/nurabrowser-artifacts.json').write_bytes((out/'nurabrowser-artifacts.json').read_bytes())
PY
(
    cd "$out"
    tar --sort=name --mtime='@0' --owner=0 --group=0 --numeric-owner \
        -cf nurabrowser-ci.tar release
    sha256sum nurabrowser-ci.tar > SHA256SUMS.txt
    sha256sum release/bin/nurabrowser-core release/bin/,browse > BIN-SHA256SUMS.txt
)
printf 'CI_BUILD_READY=%s RUN=%s\n' "$sha" "$run"
