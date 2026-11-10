#!/bin/sh
# SPDX-License-Identifier: MIT
# Host-only genuine Debian WPE 2.54.0-2 ARMHF build.
# No SSH, devices, host chroot, deployment or sandbox bypass.
set -eu
project=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
repo=$(CDPATH='' cd -- "$project/.." && pwd)
work="$repo/work/nura-browser-armhf-20261110"
image=sl101-nurabrowser-wpe-dev:2.54.0-2
upstream="$repo/work/sl101-wpe-armhf-build-qualification-20261003/wpe-audit/packages/libwpewebkit-2.0-1_2.54.0-2_armhf.deb"
runtime=libwpewebkit-2.0-1_2.54.0-2_armhf.deb
dev=libwpewebkit-2.0-dev_2.54.0-2_armhf.deb
runtime_sha=0b3713cae5520fb44a6fcb099b0b23b8f2802bf3e3a57415fc36b9616bc84ffb
dev_sha=8fe43cebac76de223b5e181eaa049bb21f788fb935dd620fdc640e3b440486f9

[ "$#" -le 1 ] || { echo 'Usage: prepare-armhf-sysroot.sh [--image-only]' >&2; exit 2; }
[ "$#" -eq 0 ] || [ "$1" = '--image-only' ] || { echo 'unknown option' >&2; exit 2; }
command -v docker >/dev/null || { echo 'docker is required' >&2; exit 1; }
mkdir -p "$work/packages" "$work/out"
if [ ! -f "$work/packages/$runtime" ]; then
    [ -f "$upstream" ] || { echo 'Historical pinned ARMHF runtime archive missing' >&2; exit 1; }
    cp -- "$upstream" "$work/packages/$runtime"
fi
if [ ! -f "$work/packages/$dev" ]; then
    curl -fL --retry 2 --max-time 90 \
      -o "$work/packages/$dev" \
      'https://snapshot.debian.org/archive/debian/20260919T000000Z/pool/main/w/wpewebkit/libwpewebkit-2.0-dev_2.54.0-2_armhf.deb'
fi
(
  cd "$work/packages"
  printf '%s  %s\n' "$runtime_sha" "$runtime" "$dev_sha" "$dev" | sha256sum -c -
)
# Package SHA-256 pinned before the build; do not install on the host.
docker build --pull=false --progress=plain -t "$image" \
  -f "$project/packaging/Dockerfile.armhf-wpe-dev" "$work"

# Record the complete rolling unstable closure and exact resulting image ID.
# These are build evidence, not a claim of immutable dependency pinning.
docker image inspect "$image" --format '{{.Id}}' > "$work/out/builder-image-id.txt"
docker run --rm --network none --entrypoint /bin/sh "$image" \
  -c 'dpkg-query -W -f="${Package}\t${Version}\t${Architecture}\n"' \
  > "$work/out/builder-packages.tsv"

[ "$#" -eq 1 ] && exit 0

# Container root is the isolated sysroot holding installed target
# development packages with a cross compiler. No network, no devices.
docker run --rm --network none --user "$(id -u):$(id -g)" \
  --mount "type=bind,src=$project,dst=/src,readonly" \
  --mount "type=bind,src=$work/out,dst=/out" \
  --entrypoint /bin/sh "$image" \
  -c 'sh /src/scripts/build-armhf.sh / /out/build && \
      python3 /src/packaging/create-manifest.py \
        --build-dir /out/build --output /out/nurabrowser-artifacts.json && \
      DESTDIR=/out/stage meson install -C /out/build'
printf 'ARMHF ELF: %s\n' "$work/out/build/nurabrowser-core"
printf 'Artifact manifest: %s\n' "$work/out/nurabrowser-artifacts.json"
printf 'Local staging only: %s\n' "$work/out/stage"
