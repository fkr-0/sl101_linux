# NuraBrowser CI-only ARMHF deployment to SL101 .106

Date: 2026-11-11. Repo: sl101_linux. Build provenance and deployment
are intentionally independent of the older locally built binaries.

## Contract

- Only CI-produced ARMv7 hard-float VFPv3-D16 NuraBrowser; never promote
  the host crossbuild under work/ directly onto the device.
- Pin source SHA, GitHub Actions run ID, workflow path, successful
  status, downloaded original tar SHA256, ELF build manifest and checksums.
- Retain the known-good Cog 0.18.5 / WPE WebKit 2.54.0-2 private Debian
  root with no-SIMD libwebp/libsharpyuv; never modify it as part of
  CI staging. The browser executable and launcher are separate files.
- Read-only device identity and runtime checks before a single file copy:
  SL101 hostname, eMMC CID, SD CID, root partition, Nura OS, current
  browser-specific kernel and boot ID, WPE and no-SIMD overlay digests.
- Never silently rewrite the existing NuraLoumi A/B kernel pin.
- Stage only /opt/nura-browser/releases/<git-sha> with a CI-STAGED
  receipt and RUNTIME_QUALIFIED=false, ACTIVATED=false.
- No live public alias, reboot, KMS, Sway, WayVNC, Mesa, NuraLoumi,
  Cog process, WebKit sandbox setting or compositor input mutation.

## CI workflow

The GitHub Actions workflow
.github/workflows/nura-browser-armhf.yml runs on ubuntu-24.04.
It builds its own Docker image from a fixed Debian base-image digest:

    debian@sha256:873bf43b48d52ba792b98de93232153e59d4946b93cbd89d91cffef0df4ce823

WPE WebKit runtime and SDK packages are obtained from the dated
2026-09-19 Debian snapshot with pinned digests:

    libwpewebkit-2.0-1_2.54.0-2_armhf.deb
    0b3713cae5520fb44a6fcb099b0b23b8f2802bf3e3a57415fc36b9616bc84ffb
    libwpewebkit-2.0-dev_2.54.0-2_armhf.deb
    8fe43cebac76de223b5e181eaa049bb21f788fb935dd620fdc640e3b440486f9

Other Debian unstable dependencies still depend on the time of the
build. The CI artifact records its full dpkg package list and Docker
image digest. This is provenance and validation, **not yet an
independently reconstructible immutable dependency snapshot**. Runtime
is deliberately sourced from the existing Cog installation, not the CI
container.

The CI build runs actual navigation/control socket tests, native engine
tests, 58+ offline browser tests, WPE 2.54 ARMHF crosslink, ELF ABI
audit and Cortex-A9 No-NEON QEMU library probes. It packages two files:

    release/bin/nurabrowser-core
    release/bin/,browse

The tar also carries the original CI-PROVENANCE.json and exact
manifest. The GitHub Actions upload has SHA/run-scoped artifact name.
It explicitly claims static-armhf-audited-not-runtime-qualified.

## Controller/Ansible

Use the importer
deploy/ansible/tools/nura_browser_ci_payload.py with the approved
source SHA, run ID and tar SHA256. It checks GitHub's actual run
and downloads the exact named Actions artifact. The independent
verify-ci-release.py checks every member, ELF architecture/ABI,
no-NEON evidence and SHA256; no tar extraction occurs before validation.

The inventory approves the exact run and separately pins the actual
boot state. There is no fallback to a locally built file.

    ansible-playbook -i deploy/ansible/inventory/hosts.yml \
      deploy/ansible/playbooks/nura-browser-stage.yml --limit sl101-nura --check

Then, only when successful, run with both SL101_APPLY=YES and
SL101_NURABROWSER_STAGE=YES plus the exact release SHA/run environment
variables. The playbook performs one more complete verification on the
controller, rechecks device physical identity and Cog hashes, copies
the intact original CI tar, checks SHA256 remotely before extraction,
verifies both staged executable hashes and writes CI-STAGED.

## Runtime qualification remains separate

The host/no-NEON executable builds, but the new WPEPlatform front end
has not passed an actual WebProcess launch on SL101 .106. The previously
prepared native headless test was blocked by the execution environment
and a concurrent kernel reboot. Thus an Ansible **staged** result must
not be described as an activated, working on-device browser.

The existing test runner
nura-browser/scripts/qualify-cog-runtime-headless.sh is independent
of Ansible and uses an isolated mount namespace, Cog's existing
runtime, mandatory sandbox, CPU renderer and bounded lifetime.
Only after this has an actual pass, and the native browser has
documented pixel/input behavior, may a separately reviewed activation
install the public ,browse integration and associated runtime mounts.

## Evidence

Record actual GitHub source SHA, run ID, artifact SHA256, read-only
Ansible --check recap, inactive stage recap, remote executable hashes,
kernel boot ID and untouched Cog/Sway state here after verification.

### 2026-11-11 verified GitHub Actions artifact

| Evidence | Verified value |
| --- | --- |
| GitHub Actions run | 43032042301, completed SUCCESS |
| Source SHA | e0c2b0424c1244596bd0b2e9f40dd1ae54e968ac |
| Workflow | .github/workflows/nura-browser-armhf.yml |
| Branch | nurabrowser-ci-20261111 |
| Original CI tar SHA256 | a15c922ac9e8e49a499e4b128c42cadbfb4ce96f5e44d2ecf2acc1dc8259920a |
| CI-built ARMHF core SHA256 | 67b5a5d6961ccb4ee100e40a6cb8300571e6a986978fd20e2fd20381a2e3a06b |
| CI-built launcher SHA256 | c5ef1b3422dbc68949fe58b4d23dce49a5f0f400c405c3e78ddb85b66300b5e4 |
| Static status | CI-STATIC-READY-RUNTIME-UNQUALIFIED |

This artifact was downloaded from its exact GitHub run, and the CI-only
importer verified its complete contents, source, hashes and ARMHF ABI
before publishing to the ignored controller data directory. This is
**not** the previously built host-local ARMHF binary.

Read-only physical device check before staging:
kernel 7.0.1-postmarketos-grate-dmavde1,
boot ID 48d4a72f-146f-43c7-a308-496466246821,
hostname sl101-nura, both storage CIDs and SD root matched inventory.

### Actual CI-only Ansible staging result on .106

The complete controller/device read-only preflight PASSED:

    ok=11 changed=0 unreachable=0 failed=0 skipped=9

The explicitly gated Ansible stage PASSED:

    ok=20 changed=6 unreachable=0 failed=0 skipped=0

An immediate second full staged Ansible run was IDEMPOTENT:

    ok=20 changed=0 unreachable=0 failed=0 skipped=0

Installed, inactive release:

    /opt/nura-browser/releases/e0c2b0424c1244596bd0b2e9f40dd1ae54e968ac/
      nurabrowser-ci.tar
      BIN-SHA256SUMS.txt
      CI-GITHUB-RUN.json
      CI-STAGED
      release/bin/nurabrowser-core
      release/bin/,browse
      release/CI-PROVENANCE.json
      release/nurabrowser-artifacts.json

Independent postflight over SSH verified:

- Original CI tar SHA256 remains
  a15c922ac9e8e49a499e4b128c42cadbfb4ce96f5e44d2ecf2acc1dc8259920a.
- Both executable files passed a fresh remote sha256sum -c check.
- ARM ELF32 EABI5 hard-float binary and ld-linux-armhf.so.3 interpreter.
  Executables and release directories are root-owned.
- CI-STAGED explicitly contains RUNTIME_QUALIFIED=false and
  ACTIVATED=false. No global ,browse alias and no current symlink.
- Physical kernel/boot ID, Sway, WayVNC, NuraLoumi panel were
  preserved; no Cog/NuraBrowser test process was left running.

This is an **installed, CI-provenanced inactive release**, NOT a
fully activated NuraLoumi browser. The native WPEPlatform WebProcess,
sandbox, Wayland pixels and keyboard/touch need a separately gated
on-device qualification before enabling the public command.

### Separate repository-wide GitHub CI caveat

The dedicated NuraBrowser WPE 2.54 ARMHF release workflow run 43032042301
COMPLETED SUCCESSFULLY and generated the verified production-candidate
artifact used above.

The separate, generic repository-wide CI workflow run 43032041614 on
the same source commit FAILED in Unit tests: 354 tests were run,
4 failures, 16 errors, 40 skipped. Failure examples include test
fixtures referring to Git-ignored work/sl101-dmafix1-vde-rc2-20261110
kernel artifacts and build/mesa-grate-clean source files not present in
a clean GitHub checkout. Those are other project test dependencies,
not an ARMHF NuraBrowser compiler/linker or artifact failure.

The local full repository test suite did pass (2147 tests, 3 skipped)
because the local machine retains these ignored hardware/source
fixtures. Do not represent the generic GitHub CI as green, silently
remove those tests, or infer clean-checkout reproducibility from the
local result. Repair the baseline/general CI artifact fixture strategy
as a distinct, scoped change.
