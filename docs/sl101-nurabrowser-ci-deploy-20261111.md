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
