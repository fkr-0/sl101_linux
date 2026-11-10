# SL101 production-baseline DMA + VDE combined candidate

**Status: host-built, fully packaged and passed offline preflight. NOT device-tested.**
Date: 2026-11-10. Do not promote to default or boot via unattended SSH.

## Scope and provenance

Build lane: `work/sl101-prod-dmavde-rc3-20261110/`.
Canonical build drivers: `scripts/sl101-dmavde1-{prepare,build,package}`;
patches are tracked under `patches/linux-postmarketos-grate-7.0.1/dmavde1/`.
The original production source tarball and config backup remain host-only inputs.

- Baseline: postmarketOS `linux-postmarketos-grate 7.0.1-r4` original
  source tarball (SHA-512 pinned by the original APKBUILD), *not K76*.
- Original stock config SHA-256:
  `6b09863a5f4356ce615f7d5d4cdecbba4cd2cc208c34125954af9534648f9248`;
  this also equals the original Debian .100 running config.
- Distinct kernel release: `7.0.1-postmarketos-grate-dmavde1`.
  Compiler-generated metadata, localversion and disabled debug info are
  intentionally different; functional config otherwise follows stock.
- Source changes (four patches, all strictly applied with zero fuzz):
  1. `0001-arm-dma-cma-no-kmap-attributes.patch` — CMA lowmem alias
     attributes; **experimental**, not yet hardware-qualified.
  2. `0002-dma-direct-zero-no-kmap.patch` — zeroing and DMA sync
     in the generic no-kernel-mapping path.
  3. `0003-vde-cached-capture-v2.patch` — cached V4L2 CAPTURE
     buffers with `cached_capture` module parameter, default OFF;
     separately qualified as an out-of-tree module on Nov 8.
  4. `0004-vde-async-semaphore.patch` — replaces cross-task VDE
     mutex ownership with an ownerless semaphore and balances suspend
     error paths; part of the preexisting combined RC2.
- Kernel image SHA-256:
  `79911fc494207ff0607373ceed2ff848e8b6b9252e97599a0e75913965e941aa`.
- Original matching DTB SHA-256:
  `01fbb5a935e429c42dc5e2793049bbfc91ff3a6f73c15f2063e1fb0af1a289b0`.
- Patched `tegra-vde.ko.zst` SHA-256:
  `625bc023d0df8903f6387b9ff1c7963ed4ebb79eb3a13c8c1884b6ef4fd7b892`.
- **587/587** modules have the new kernel release vermagic. The
  VDE module exports the `cached_capture` parameter and imports
  `down`, `down_interruptible` and `up`, not the old cross-task
  `mutex_lock_interruptible` path.

Portable release archive:

`work/sl101-prod-dmavde-rc3-20261110/sl101-7.0.1-dmavde1-four-patch-candidate.tar.zst`

Archive SHA-256:
`d7781381ee52efb3be6edf885857b2800a4e1e00ce989a63a00955035183d8dc`.

The archive includes zImage, original DTB, current and stock configs,
the entire module tree, all four source patches, provenance JSON and
full-file `SHA256SUMS`. Its manifest was validated for all files.

## Reproduction and gates (host only)

    bash scripts/sl101-dmavde1-prepare.sh
    SL101_JOBS=12 bash scripts/sl101-dmavde1-build.sh
    python3 deploy/ansible/tools/verify_kernel.py \
      --root work/sl101-prod-dmavde-rc3-20261110 \
      --release 7.0.1-postmarketos-grate-dmavde1 \
      --expected-dtb-sha 01fbb5a935e429c42dc5e2793049bbfc91ff3a6f73c15f2063e1fb0af1a289b0 \
      --require-source-patches

After the build and validation, package once with
`python3 scripts/sl101-dmavde1-package.py`.
The packager refuses to overwrite an existing candidate.

Ansible read-only host preflight (three tasks, changed=0):

    ansible-playbook -i deploy/ansible/inventory/hosts.yml \
      deploy/ansible/playbooks/kernel-preflight.yml --check

Read-only post-reboot inventory/boot inspection (only when reachable):

    ansible-playbook -i deploy/ansible/inventory/hosts.yml \
      deploy/ansible/playbooks/hardware-preflight.yml --limit sl101-nura

No playbook in this candidate path installs, flashes, sets boot defaults,
executes kexec or reboots a tablet.

## Existing RC2 caution

The earlier `dmafix1 + VDE-owner-lock RC2` was already staged to
the Nura .106 SD APX extlinux and a one-shot kexec handoff was attempted.
See `docs/sl101-dmafix1-prod-candidate-boot-20261110.md`.
That RC2 contains the DMA-direct patch and VDE async semaphore patch,
**but not** the cached-CAPTURE-v2 patch or the CMA alternative.
Its postboot outcome was not confirmed. Avoid overwriting its recovery
receipt, extlinux backup, or kernel/module slots until .106 comes back
and the exact running release, SD CID, boot ID and rollback state are
verified. No rescue operation was performed by this build.

## Required future hardware qualification

The four-patch build is NOT yet safe for promotion:
- Confirm stock/RC2 boot health and permanent recovery path on .106,
  and compare to .100 without confusing the two SD CIDs.
- Trial `dmavde1` as a non-default one-shot candidate only under
  explicit operator control and a recoverable power/boot path.
- Test Wi-Fi, EC/Atmel input, keyboard and touch, Sway/WayVNC, Grate
  pixel output, fresh BO/DMA behavior (including below-256 cases),
  VDE decoding/frame correctness and `cached_capture` enabled/disabled,
  asynchronous owner-lock failures and video performance.
- Verify complete 587-module ABI, boot config, `dmesg` errors,
  decoder and compositor interactions; do not infer runtime fitness
  from successful compilation.

Offline preflight is a necessary gate, not a hardware acceptance result.
