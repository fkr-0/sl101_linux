# CI NuraBrowser headless smoke: staging-to-runtime handoff

The device already has the exact GitHub Actions run 43032042301
(source e0c2b0424c1244596bd0b2e9f40dd1ae54e968ac) staged under
/opt/nura-browser/releases/<sha>. It is inactive. This handoff
never consumes the host-built work/... ELF or upgrades existing Cog.

The helper scripts are:

    nura-browser/scripts/run-staged-ci-smoke.sh
    nura-browser/scripts/qualify-cog-runtime-headless.sh

The first script verifies exact physical hostname, CPU, boot ID, kernel,
both MMC CIDs, SD root, the original CI tar SHA256, both CI ELF/script
hashes and CI-STAGED receipt. It refuses startup without these gates.
It also SHA-pins the second script from the reviewed tree. Read-only
mode never writes any files:

    sh run-staged-ci-smoke.sh --check

Separately approved and authenticated device-root execution, after
successful preflight:

    NURABROWSER_NATIVE_HEADLESS_TEST=YES sudo -n sh run-staged-ci-smoke.sh --run

The script copies only the CI-origin ARMHF binary to a disposable
root-owned /tmp/nurabrowser-smoke-XXXXXXXX directory, with a separate
UID 1000 state directory. It invokes the existing preflight and enters
its private mount namespace. It never replaces Cog, touches the public
,browse symlink, or attaches Wayland/DRM. The browser must produce an
actual WebKit load-finished signal, remain alive through its deadline
and exit successfully, with sandbox enabled. Otherwise it fails.

## Current execution status

2026-11-11 23:25 CET: Device .106 responded to ICMP, but normal
public-key SSH authentication from the current controller shell failed.
Its SSH server recognized the configured RSA public key, but no unlocked
agent was available to complete authentication. An unrelated existing
SSH ControlMaster was identified as a Git transport connection and
was deliberately not reused. No legitimate tablet command could be
executed in this session. **Device headless and Wayland qualification
are not claimed.** The last observed CI release and runtime hashes
remain historical receipts, not fresh hardware evidence.

The helper has host-only negative tests in
tests/test_staged_ci_smoke.py. Its actual privileged operations require
both fresh device identity checks and an authenticated, approved
test session. Do not work around the SSH-agent or namespace security
boundary. Once headless succeeds, a separately gated software Sway
Wayland + WayVNC pixel/input test can be run without altering Cog.
