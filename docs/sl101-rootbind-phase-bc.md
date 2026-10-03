# SL101 RootBind Phase B/C status

Date: 2026-09-23

This lane is intentionally Android-preserving. It does not authorize permanent U-Boot installation, TF101-derived partition assumptions, historical `abootimg` geometry, legacy `root=/dev/mmcblk*` guesses, or unverified SBK/BCT/key material.

## Current live-evidence boundary

No repository-local `state/sl101-preflight/*.json` report exists yet for the current physical tablet. The current host ADB executable also fails before transport enumeration with:

```text
adb: symbol lookup error: adb: undefined symbol: libusb_get_ssplus_usb_device_capability_descriptor
```

`fastboot devices -l` and the filtered USB scan exposed no tablet transport during this pass. Therefore no RootBind wrapper field is being resolved from native-SD/U-Boot observations or repository archaeology. Native Debian MicroSD evidence remains recorded separately and is explicitly forbidden from populating RootBind `/data` or boot-wrapper defaults.

The narrow first probe, once an already-authorized Android/recovery ADB transport is available, is:

```sh
PYTHONPATH=src python scripts/sl101-preflight.py --serial <EXACT-ADB-SERIAL>
python scripts/sl101-rootbind-build.py wrapper-spec \
  --preflight state/sl101-preflight/<serial>/<timestamp>.json \
  --out tmp/sl101-rootbind/wrapper-spec.json
```

The preflight is observational only. It captures identity, `/proc/partitions`, `/proc/mounts`, `/dev/block/by-name`, `/data` free space (`df -k /data`), CPU/kernel facts, and root/recovery indicators without root escalation or device writes.

## Deterministic wrapper specification

`scripts/sl101-rootbind-build.py wrapper-spec` now resolves only fields directly supported by a read-only live preflight report. Every still-unknown field remains blocked with a narrow probe:

| Field | Current state | Narrow evidence required |
|---|---|---|
| ASUS boot image/header format | blocked | From an already-authorized rooted Android/recovery environment, capture the original boot partition image/header read-only, record exact byte count + SHA-256, then parse that observed header. |
| Kernel/ramdisk load addresses + page size | blocked | Derive only from the captured boot image/header from this physical unit. |
| Boot partition label/path/size | blocked until live report | `/dev/block/by-name` plus `/proc/partitions`; no historical partition number fallback. |
| Android `/data` device/filesystem/free space | blocked until live report | `/proc/mounts` plus `df -k /data`. |
| Hand-off to `/data/linuxroot` | blocked/partial | First resolve `/data`; then prove the actual mount/pivot sequence on this unit. |
| Initramfs vs mainline hand-off patch | blocked | Only test after boot geometry and `/data` topology are observed. |
| Restore path | blocked | Capture the original boot image, exact size + SHA-256, and prove recovery can restore the same bytes to the same observed boot partition before any boot-partition modification. |
| Firmware/NVRAM filenames | blocked-runtime-evidence-required | Record exact `firmware_class`/`brcmfmac` filename requests after a candidate Linux kernel actually boots. |

The wrapper spec embeds SHA-256 and byte size of the live preflight JSON used as evidence.

## Phase C staging contract

`scripts/sl101-rootbind-build.py stage-plan` does not write the tablet. It becomes `ready-to-stage` only when all of these gates are true:

- live `/data` device, filesystem and free space are resolved from the tablet;
- a tested original-boot restore path is marked resolved;
- the provenance-qualified Debian rootfs archive and modules archive still match their recorded hashes;
- kernel release/module layout is exactly `6.18.45` / `usr/lib/modules/6.18.45`;
- observed `/data` free space is at least the rootfs archive's unpacked file-byte total plus a fixed 256 MiB first-boot/staging margin.

The generated staging sequence is deliberately reversible: verify `/data` immediately before staging, refuse an existing `/data/linuxroot` unless explicitly selected by the operator, create only the new RootBind subtree plus a sentinel, extract with numeric ownership/xattrs/ACLs, verify merged-/usr and `usr/lib/modules/6.18.45`, keep machine-id empty and SSH host keys absent until first real boot, and inject only operator-approved public SSH keys. Rollback removes only the sentinel-verified `/data/linuxroot` subtree from Android/recovery and never reformats `/data`.

The current archived rootfs passes the identity-hygiene gate: `/etc/machine-id` exists and is empty, no `etc/ssh/ssh_host_*` files are archived, and `/usr/bin/qemu-arm-static` is absent. Its summed regular-file payload is `324021433` bytes, so the current deterministic free-space gate is `592456889` bytes including the fixed 256 MiB margin.

## Host artifact provenance audit

The immutable archives and DTB needed for RootBind still match the recorded provenance exactly:

| Artifact | Bytes | Observed SHA-256 | Manifest status |
|---|---:|---|---|
| `tmp/sl101-rootbind/artifacts/debian-trixie-armhf-rootfs.tar.xz` | 107141788 | `5bfc126bdb0c9d4df6048fa123f5af4cc14bda430ade81a865db9b6e3c20a460` | matches |
| `tmp/sl101-rootbind/artifacts/sl101-modules.tar.xz` | 6881116 | `7be10435bc15fc22ed511eb946b0d44302e578aac7be5585b79a7bdb2e52be64` | matches |
| `tmp/sl101-rootbind/kernel-build/arch/arm/boot/dts/nvidia/tegra20-asus-sl101.dtb` | 56438 | `7c938df062396a142f800c3807ba0d8f4255cd9ff8bfc8d09e83ee93b1dcb52a` | matches |
| `tmp/sl101-rootbind/artifacts/build-environment.json` | 839 | `17701252c4367dcb52e049c438c046a878ced0bb6ecddd74318d0c2a07937953` | matches |
| `tmp/sl101-rootbind/artifacts/build-environment-packages.tsv` | 5692 | `0bd76b6ce200745d501486574e86aeec9a5492404c498101858f37ff289d693d` | matches |
| `tmp/sl101-rootbind/artifacts/rootfs-recovery.json` | 1033 | `d22cf70f9cc6e241e43a9c686054fac52fa377278754214af082dc4095a56ca8` | matches |
| `tmp/sl101-rootbind/artifacts/provenance.json` | 3964 | `983ab1d29205d150ad805e2e55f4553467396511d7c87e6353d1ddd8ca58ab96` | self-audit reference |

### Concrete provenance defect discovered

The manifest points `kernel_config` and `zImage` at mutable `tmp/sl101-rootbind/kernel-build/...` paths. Those paths have since been overwritten by later kernel work, so their current bytes no longer match the manifest:

| Mutable path | Bytes now | Current SHA-256 | Manifest SHA-256 |
|---|---:|---|---|
| `tmp/sl101-rootbind/kernel-build/.config` | 287335 | `5554fbf206264319ac8b2bb9614f1eff493746e7c995b25b36de07150f565ff2` | `2431173cadb597191042a28f77c0c4437bc9dc4e9bf0a4133ba0579e13c20ea7` |
| `tmp/sl101-rootbind/kernel-build/arch/arm/boot/zImage` | 11837952 | `238b5501dd5df31731004d5fa866b793ad5fe9addb294c61ecfc90e6011dc915` | `b76cf9e35b730c86488913564b964578ed1d90d99a23d7e005146aa7a0551ba3` |

No surviving copy of the exact manifest-hashed `b76cf9e...` zImage or `2431173...` config was found in the searched repository-local kernel artifact trees. They must not be silently replaced by the separately proven native-SD `aaf847d5...` kernel. The RootBind rootfs/modules archives remain usable because their bytes still match provenance; any wrapper that needs the original Phase-4 zImage must first reproduce or recover that exact kernel artifact under a non-mutable artifact path and record its provenance.

## Preserved opaque boot/recovery evidence

The existing boot/recovery captures are preserved byte-for-byte and now also have a generated hash/size manifest at:

`tmp/sl101-rootbind/artifacts/preserved-live-evidence.json`

These filenames are **not** being treated as proof of partition identity, boot labels, geometry, or a tested restore source. They are preserved provenance only until a fresh live tablet mapping proves what each capture represents.

| Preserved artifact | Bytes | SHA-256 |
|---|---:|---|
| `tmp/sl101-backup/android-boot-p4.blob` | 16777216 | `fa81303d47e8619467936c6db747daa7c859d403ee436c2beb75a9a93076e112` |
| `tmp/sl101-backup/boot-p5-backup.img` | 5242880 | `e99cef492d9d7f87b8ee6d5e1e07ec297c94082f36bd08f3ddb9905fb31cc6e2` |
| `tmp/sl101-backup/gpt-header.bin` | 17408 | `a1b7a666d52586225a588484decb10ef039b76b6f42c38c4a0ac01f1060a70a0` |
| `tmp/sl101-backup/lnx-backup-sl101-2.bin` | 14680064 | `665c9c1b0bb712c2788adb0f83d01e8bb1418057ff2bf17d095631d0f6bb40eb` |
| `tmp/sl101-backup/lnx-sector17408-backup.bin` | 14680064 | `c473a7ce20e617ef8c18816b2a2cad55559cd6266045242880f5d21919eef286` |
| `tmp/sl101-backup/pregpt.bin` | 23592960 | `571eb03a59ccb00d1a4887925035b25420da8628632c917e680b7d086e34a283` |
| `tmp/sl101-backup/recovery-p4-backup.img` | 555220992 | `4be95be64f1f46b9d2123da4a6cd8d3ea0ef3f97c9bc563d969c2ede83a0f2d0` |

The host-side recorder is deterministic and semantic-free:

```sh
python scripts/sl101-rootbind-build.py evidence-manifest \
  --artifact tmp/sl101-backup/android-boot-p4.blob \
  --artifact tmp/sl101-backup/boot-p5-backup.img \
  --artifact tmp/sl101-backup/gpt-header.bin \
  --artifact tmp/sl101-backup/lnx-backup-sl101-2.bin \
  --artifact tmp/sl101-backup/lnx-sector17408-backup.bin \
  --artifact tmp/sl101-backup/pregpt.bin \
  --artifact tmp/sl101-backup/recovery-p4-backup.img \
  --out tmp/sl101-rootbind/artifacts/preserved-live-evidence.json
```

## Verification

Host checks currently pass with:

```sh
PYTHONPATH=src python -m unittest \
  tests.test_sl101_rootbind_build tests.test_sl101_preflight -v
python -m py_compile scripts/sl101-rootbind-build.py scripts/sl101-preflight.py
git diff --check -- \
  scripts/sl101-rootbind-build.py scripts/sl101-preflight.py \
  tests/test_sl101_rootbind_build.py tests/test_sl101_preflight.py
```

The unit suite covers live-evidence-only field resolution, rejection of non-live/unidentified evidence, separation of native-SD facts from RootBind defaults, hash-gated rootfs/modules staging, free-space gating, tested-restore gating, and read-only preflight probe allowlisting.
