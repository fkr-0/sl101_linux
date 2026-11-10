# NuraLoumi SL101 artifacts, CI and rollout gate — 2026-11-10

**Host-stage only. No SL101 installation, Sway restart or boot change was
performed by this lane.**

## Provenance

Both artifacts were downloaded from the separate GitHub Actions release jobs
for the same **committed** NuraLoumi source SHA
`ccf7e3ac677b84485c32ef63a66ef88686bd866b` (2026-11-09):

| Target | GitHub Actions run | SHA256 of `nuraloumi-ci.tar` |
|---|---:|---|
| Alpine 3.22 / ARMv7 **musl** | 42680262513 (success) | `ff78b02462194fa39656775adad93fc467c2b5916f08dfaf8c958f4063f75d49` |
| Debian 13 / ARMHF **glibc** | 42680262464 (success) | `aa635c28d3890163b15b39169ef8fde2def88660cedc2bb49da20a3756125bf5` |

Downloaded to the sibling `nuraloumi` checkout, under ignored local paths:

- `target/sl101-staged-release-20261110/musl/nuraloumi-alpine322-armv7-musleabihf-5/`
- `target/sl101-staged-release-20261110/glibc/nuraloumi-debian13-armv7-gnueabihf-7/`

Each artifact's published `SHA256SUMS.txt` verified successfully against
`nuraloumi-ci.tar`. The bundles contain both `nuraloumi-panel` and
`nuraloumi-sway-workspace-switcher`. The published `ELF-AUDIT.txt`
reports ARM32 hard-float VFPv3-D16, no detected NEON attributes, and
the **correct distinct loader**: `/lib/ld-musl-armhf.so.1` for Alpine and
`/lib/ld-linux-armhf.so.3` for Debian.

**Important CI caveat:** the separate general `CI` workflow at
run `42680262456` failed in its Rust `Test` step. Its format/check steps
passed. Therefore neither platform-specific artifact success nor these
download checks establishes the entire NuraLoumi release train as green.

## Rollout and renderer truth

The supported musl build is for `sl101-nura` (`.106`), not the Debian
rootbind `.100`; the glibc build is for `.100`. No mixed ELF, loaders or
system Mesa directories.

The provider's live renderer detector already returns `Pixman`,
`GLES2`, `Grate` or `Unknown` based on the actual Sway process environment,
Gallium maps and PID-reuse checks. The `sl101-desktop` host launcher
additionally writes `/run/sl101-render-status` containing requested versus
actual rendering and Pixman fallback reason. A future panel integration may
use that signal as additional provenance, but a stale file must never
override the live compositor's actual renderer.

For on-device promotion:
1. Re-establish authenticated SSH and independent APX/boot recovery.
2. Confirm each device's hostname, SD CID, current running kernel, Sway
   process, active renderer and installed NuraLoumi binary hashes.
3. Preserve the old panel and workspace-switcher binaries, stage only
   architecture-matching copies, verify ELF dynamic linker/no-NEON and
   match the above full release artifact hash.
4. Start the panel through the existing `sl101-sway-panel` hook under
   the current Sway instance, without replacing system Mesa or changing
   the compositor. Verify live top-right renderer label and failed-Grate
   fallback (Pixman). Confirm Super+digits workspace behavior and
   keyboard-release overlay semantics with physical input.
5. Roll back to the original binaries and panel process on any
   mismatch; collect frames and fault deltas separately from simple
   ELF/process success.

This lane did not mutate either tablet because the available SSH identities
were rejected by both targets (`Permission denied`). In-flight NuraLoumi
file-manager/xdg/viewer changes belong to separate active workers and are
**not** part of this pinned release artifact.
