#!/usr/bin/env bash
set -euo pipefail

# Build the Phase-4 host-only SL101 kernel/rootfs contract without installing
# cross-build or debootstrap packages on the workstation. The tracked checkout
# is mounted read-only; only the selected repo-local work root is writable.

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

WORK_ROOT="${1:-tmp/sl101-rootbind}"
RESUME_SOURCE="${SL101_RESUME_SOURCE:-0}"
CONTAINER_IMAGE='debian@sha256:b6e2a152f22a40ff69d92cb397223c906017e1391a73c952b588e51af8883bf8'
APT_SNAPSHOT='http://snapshot.debian.org/archive/debian/20260821T000000Z/'
ROOTFS_SNAPSHOT='https://snapshot.debian.org/archive/debian/20260821T000000Z/'
KERNEL_REMOTE='https://git.kernel.org/pub/scm/linux/kernel/git/stable/linux.git'
KERNEL_REF='v6.18.45'
KERNEL_COMMIT='bf3be28f6721e24961992ebb9e61c0cf21a56806'

ABS_WORK_ROOT="$(python3 - "$REPO_ROOT" "$WORK_ROOT" <<'PY'
from pathlib import Path
import sys

repo = Path(sys.argv[1]).resolve()
candidate = Path(sys.argv[2])
resolved = (candidate if candidate.is_absolute() else repo / candidate).resolve()
try:
    relative = resolved.relative_to(repo)
except ValueError as exc:
    raise SystemExit(f"work root must stay inside repository: {resolved}") from exc
if relative == Path('.'):
    raise SystemExit("work root must not be the repository root")
print(resolved)
PY
)"
WORK_REL="${ABS_WORK_ROOT#"$REPO_ROOT"/}"

if ! command -v docker >/dev/null 2>&1; then
  echo 'error: docker is required for the isolated SL101 host build' >&2
  exit 2
fi

mkdir -p "$ABS_WORK_ROOT"
if find "$ABS_WORK_ROOT" -mindepth 1 -maxdepth 1 -print -quit | grep -q .; then
  if [[ "$RESUME_SOURCE" != 1 ]]; then
    echo "error: work root is not empty: $WORK_REL" >&2
    echo 'refusing to overwrite or clean an existing build; choose a fresh repo-local work root' >&2
    exit 2
  fi
  if [[ ! -d "$ABS_WORK_ROOT/linux/.git" ]]; then
    echo 'error: SL101_RESUME_SOURCE=1 requires an existing verified linux/.git source tree' >&2
    exit 2
  fi
  for partial in kernel-build module-stage rootfs; do
    if [[ -e "$ABS_WORK_ROOT/$partial" ]]; then
      echo "error: source-only resume refuses partial build directory: $WORK_REL/$partial" >&2
      exit 2
    fi
  done
  if [[ "$(git -C "$ABS_WORK_ROOT/linux" rev-parse HEAD)" != "$KERNEL_COMMIT" ]]; then
    echo 'error: source-only resume kernel commit does not match the pinned contract' >&2
    exit 2
  fi
fi

available_kb="$(df -Pk "$ABS_WORK_ROOT" | awk 'NR == 2 {print $4}')"
if [[ ! "$available_kb" =~ ^[0-9]+$ ]] || (( available_kb < 8 * 1024 * 1024 )); then
  echo "error: at least 8 GiB free space is required under $REPO_ROOT" >&2
  exit 2
fi

host_uid="$(id -u)"
host_gid="$(id -g)"
fix_ownership() {
  docker run --rm \
    --network none \
    --mount "type=bind,src=$ABS_WORK_ROOT,dst=/workspace" \
    "$CONTAINER_IMAGE" \
    chown -R "$host_uid:$host_gid" /workspace >/dev/null 2>&1 || true
}
trap fix_ownership EXIT

docker run --rm \
  --mount "type=bind,src=$REPO_ROOT,dst=/repo,readonly" \
  --mount "type=bind,src=$ABS_WORK_ROOT,dst=/workspace" \
  --workdir /workspace \
  --env "HOST_UID=$host_uid" \
  --env "HOST_GID=$host_gid" \
  --env "WORK_REL=$WORK_REL" \
  --env "SL101_JOBS=${SL101_JOBS:-8}" \
  --env "SL101_RESUME_SOURCE=$RESUME_SOURCE" \
  --env "CONTAINER_IMAGE=$CONTAINER_IMAGE" \
  --env "APT_SNAPSHOT=$APT_SNAPSHOT" \
  --env "ROOTFS_SNAPSHOT=$ROOTFS_SNAPSHOT" \
  --env "KERNEL_REMOTE=$KERNEL_REMOTE" \
  --env "KERNEL_REF=$KERNEL_REF" \
  --env "KERNEL_COMMIT=$KERNEL_COMMIT" \
  "$CONTAINER_IMAGE" \
  bash -euxo pipefail -c '
    export DEBIAN_FRONTEND=noninteractive
    export LC_ALL=C

    printf "deb [check-valid-until=no] %s trixie main\n" "$APT_SNAPSHOT" > /etc/apt/sources.list
    rm -f /etc/apt/sources.list.d/*
    apt-get -o Acquire::Check-Valid-Until=false update
    apt-get install -y --no-install-recommends \
      bc bison build-essential ca-certificates debootstrap device-tree-compiler \
      flex gcc-arm-linux-gnueabihf git kmod libelf-dev libssl-dev \
      perl python3 qemu-user-static rsync xz-utils

    mkdir -p artifacts
    dpkg-query -W -f="\${binary:Package}\t\${Version}\n" | sort > artifacts/build-environment-packages.tsv
    package_sha="$(sha256sum artifacts/build-environment-packages.tsv | awk "{print \$1}")"
    package_rel="$WORK_REL/artifacts/build-environment-packages.tsv"
    export package_sha package_rel
    python3 - <<"PY"
import json
import os
import subprocess

def first_line(argv):
    return subprocess.check_output(argv, text=True).splitlines()[0]

value = {
    "mode": "docker-isolated-host-build",
    "container_image": os.environ["CONTAINER_IMAGE"],
    "apt_snapshot": os.environ["APT_SNAPSHOT"],
    "rootfs_snapshot": os.environ["ROOTFS_SNAPSHOT"],
    "tracked_checkout_mount": "read-only",
    "generated_work_mount": "repo-local-read-write",
    "package_manifest": {
        "path": os.environ["package_rel"],
        "sha256": os.environ["package_sha"],
    },
    "tool_versions": {
        "cross_gcc": first_line(["arm-linux-gnueabihf-gcc", "--version"]),
        "debootstrap": first_line(["debootstrap", "--version"]),
        "make": first_line(["make", "--version"]),
        "qemu_arm_static": first_line(["qemu-arm-static", "--version"]),
    },
}
with open("artifacts/build-environment.json", "w", encoding="utf-8") as handle:
    json.dump(value, handle, indent=2, sort_keys=True)
    handle.write("\n")
PY

    if [ "$SL101_RESUME_SOURCE" = 1 ]; then
      test -d linux/.git
      git config --global --add safe.directory /workspace/linux
      test "$(git -C linux rev-parse HEAD)" = "$KERNEL_COMMIT"
    else
      git clone --filter=blob:none --depth 1 --branch "$KERNEL_REF" "$KERNEL_REMOTE" linux
      test "$(git -C linux rev-parse HEAD)" = "$KERNEL_COMMIT"
    fi
    test -f linux/arch/arm/boot/dts/nvidia/tegra20-asus-sl101.dts

    make -C linux O=/workspace/kernel-build ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- multi_v7_defconfig
    make -C linux O=/workspace/kernel-build ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- \
      -j"$SL101_JOBS" zImage dtbs modules
    make -C linux O=/workspace/kernel-build ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- \
      INSTALL_MOD_PATH=/workspace/module-stage INSTALL_MOD_STRIP=1 modules_install

    rootfs_packages="ca-certificates,iproute2,iputils-ping,iw,kmod,openssh-server,procps,systemd-sysv,udev,wpasupplicant"
    debootstrap --arch=armhf --foreign --variant=minbase --include="$rootfs_packages" \
      trixie /workspace/rootfs "$ROOTFS_SNAPSHOT"
    install -m 0755 /usr/bin/qemu-arm-static /workspace/rootfs/usr/bin/qemu-arm-static
    printf "#!/bin/sh\nexit 101\n" > /workspace/rootfs/usr/sbin/policy-rc.d
    chmod 0755 /workspace/rootfs/usr/sbin/policy-rc.d
    chroot /workspace/rootfs /usr/bin/qemu-arm-static /bin/sh /debootstrap/debootstrap --second-stage

    mkdir -p /workspace/rootfs/lib/modules
    cp -a /workspace/module-stage/lib/modules/. /workspace/rootfs/lib/modules/
    chroot /workspace/rootfs /usr/bin/qemu-arm-static /usr/bin/dpkg-query \
      -W "-f=\${binary:Package}\t\${Version}\n" \
      | sort > /workspace/rootfs/var/lib/dpkg/sl101-package-manifest.tsv

    rm -f /workspace/rootfs/etc/ssh/ssh_host_*
    : > /workspace/rootfs/etc/machine-id
    rm -f /workspace/rootfs/var/lib/dbus/machine-id
    rm -f /workspace/rootfs/usr/sbin/policy-rc.d
    rm -f /workspace/rootfs/usr/bin/qemu-arm-static

    tar --sort=name --mtime=@0 --clamp-mtime --numeric-owner \
      -C /workspace/module-stage -cJf /workspace/artifacts/sl101-modules.tar.xz lib/modules
    tar --sort=name --mtime=@0 --clamp-mtime --numeric-owner --xattrs --acls \
      -C /workspace/rootfs -cJf /workspace/artifacts/debian-trixie-armhf-rootfs.tar.xz .

    chown -R "$HOST_UID:$HOST_GID" /workspace
  '

record_args=(
  scripts/sl101-rootbind-build.py record
  --kernel-source "$WORK_ROOT/linux"
  --kernel-build "$WORK_ROOT/kernel-build"
  --modules-archive "$WORK_ROOT/artifacts/sl101-modules.tar.xz"
  --rootfs-archive "$WORK_ROOT/artifacts/debian-trixie-armhf-rootfs.tar.xz"
  --build-environment "$WORK_ROOT/artifacts/build-environment.json"
  --out "$WORK_ROOT/artifacts/provenance.json"
)
if [[ -n "${SL101_ROOTFS_RECOVERY:-}" ]]; then
  record_args+=(--rootfs-recovery "$SL101_ROOTFS_RECOVERY")
fi
python3 "${record_args[@]}"

trap - EXIT
fix_ownership
printf 'SL101 host artifacts recorded under %s\n' "$WORK_ROOT/artifacts"
