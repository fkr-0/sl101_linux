# First four SL101 OCP outcomes — independent evidence review and on-device gates

Date: 2026-11-05. Project: `sl101_linux`; canonical working tree.
Scope: review OCP tasks 01 (producer buffer), 04 (KMS input namespace),
06 (input-triggered hang), 07 (Cog teardown) and run **bounded**
non-browser device verification. No deployment or replacement of Mesa/Cog.

## OCP checkpoint reviews

| OCP lane | Material reviewed | Decision |
|---|---|---|
| 01 WPE producer buffer | `b393563`, `work/sl101-wpe-producer-buffer-oracle-20261105/{producer_oracle.py,test_producer_oracle.py,README.md}` | Host metadata/snapshot validator PASS; **no actual producer BO readback**. The 71,067 wrong pixels / 22,232 magenta pixels remain post-labwc screen-space observations. No ARMHF Cog instrumentation or deployment. |
| 04 KMS input namespace | `scripts/sl101-cog-kms-input-candidate.sh`, `tests/test_sl101_cog_kms_input_candidate.py`, `docs/sl101-cog-kms-input-candidate-20261105.md` | Host mock contract PASS, concrete host device ownership confirmed. Launcher candidate **not** a production drop-in: no browser injection/session parity, rejects historical chroot mount stacks. Do not install yet. |
| 06 input-triggered hang | `scripts/sl101-cog-hang-supervisor.py`, its host tests and triage report | Host 3/3 PASS, but supervisor owns a *local process group only*, cannot guarantee termination of descendants after setsid, D-state kernel tasks or zombies. Does not restore labwc; not a replacement for the qualified KMS wrapper. No reproduced hang or root cause. |
| 07 Cog teardown review | `575970ad-c90b-4406-9839-13cc7b2e47c5`, `teardown-reentrant-asan.txt`, Cog source and patch | **HOLD**. Independent review confirms a source-grounded reentrant `destroy_buffer` use-after-free in extracted patched code, pending pageflip userdata lifetime and teardown gaps. Python test's model PASS cannot waive ASan UAF; exact native packet remains `revision_required`. No source promotion or device install. |

Focused host regression run in this review:
`python3 -m unittest tests.test_sl101_cog_kms_input_candidate tests.test_sl101_cog_hang_supervisor tests.test_sl101_cog_teardown -v`: **16/16 PASS**.
`python3 -m unittest discover -s work/sl101-wpe-producer-buffer-oracle-20261105 -p 'test_*.py' -v`: **9/9 PASS**.

## Independent security-review cross-check (OCP 09)

After the first-four device gates, the separate read-only security worker
completed OCP `SL101-LINUX-20261105-09-INDEPENDENT-SECURITY-AND-RECOVERY-RE-20261105-4722E6`:
**NOT APPROVED** for production execution. It found critical unowned/global
Cog process cleanup and missing independent watchdog in the older Wayland
probe, high-risk Pixman rollback behavior, and a high-risk broad input-device
allowlist plus unverified supervisor environment gate in the *existing* KMS
input candidate. Those are blockers, not merely style recommendations.

This follow-up's separate scratch-namespace smoke **does not modify or
approve** that candidate. It exposes only exact event0/event5 and udev in a
short-lived namespace, never starts Cog and verifies no host mount leak.
Production input integration must explicitly allowlist device identities,
retain injection and private credentials, fix actual supervisor identity and
teardown cleanup, and undergo new independent review before any live launch.

## Exact target and initial state

Read-only SSH identity (BatchMode, strict host key):
- Host `sl101-nura`, kernel `7.0.1-postmarketos-grate`
- SD CID `035344534c31323880ac79a543010300`
- Boot ID `ccfb94d1-a56a-4419-96ef-42c632bb0b46`
- `labwc` PID 6777, `SL101_DESKTOP_RENDERER=grate`, no `cog`
- About 828 MiB free-to-applications memory; idle memory pressure
- No matching host1x/GR3D timeout/reset, OOM or watchdog in checked current boot ring

## On-device gate A: host/chroot input visibility

Observed actual device nodes:
- `/dev/input/event0` Atmel touchscreen: `0660 root:input` (GID 23), rdev 13:64
- `/dev/input/event5` Slider AT keyboard: `0660 root:input` (GID 23), rdev 13:69
- `/dev/input/event6` keyd keyboard: `0660 root:input` (GID 23), rdev 13:70
- `/dev/dri/renderD128`: `0666 root:video` (GID 27)

A real `setpriv --reuid=1000 --regid=1000 --groups 27,23`
readability check for event0, event5 and DRI node returned 0 on the **host**.
A real read-only chroot check found:
`chroot_touch_visible=1`, `chroot_keyboard_visible=1`,
`chroot_udev_visible=1` (these are shell *test exit values*, 1 means absent).

The installed Debian root retains 12 pre-existing mount entries
(`dev/dri`, `proc`, `sys`, `dev/shm`, six standard `dev/*` files,
Wayland and Pulse sockets).
The unmodified candidate's default **read-only** preflight was executed
on the target via SSH stdin and failed closed with exit **69**:
`stale mounts under private root`.
No unmount, overlay or launcher execution was attempted.

## On-device gate B: private namespace proof

Created `scripts/sl101-cog-input-private-ns-smoke.sh`.
Its on-device run checks hostname, kernel, CID, renderer, labwc presence,
no Cog, event node types/group, then uses `unshare --mount --fork`.
Only **inside the newly verified mount namespace** it binds
`/dev/input/event0`, `event5`, and read-only `/run/udev` onto separate
scratch paths under a temporary `/tmp/sl101-input-smoke.*` directory.
The child verifies rdev equivalence and readability for UID 1000/GID 23;
parent verifies no child mounts leaked into host mountinfo and cleans scratch.
No evdev payloads/keystrokes are read.

Device result (exit code **0**):
```text
PASS_PRIVATE_NAMESPACE input_nodes=event0,event5 input_gid=23 udev=visible
PASS_NO_HOST_MOUNT_LEAK
```
Host syntax and static safety regression `tests/test_sl101_cog_input_private_ns_smoke.py`:
**3/3 PASS**.

This proves namespace binding and effective permissions, **not** actual
libinput enumeration inside the pivot-root Debian chroot, Cog callbacks,
WebKit DOM delivery, hotplug handling, or an integration-ready launcher.

## On-device gate C: passive health sampler

Created `scripts/sl101-cog-passive-health-probe.py` and
`tests/test_sl101_cog_passive_health_probe.py`.
The host program sends a fixed read-only Python probe via SSH stdin to the
tablet and reads an unmodified kernel `dmesg` ring before/after.
It records UTC/boot ID, uptime, labwc/Cog/WebProcess names, PID/start ticks,
memory, PSI and chroot mount count. **No device file is written**; the JSONL
receipt is saved only under the host's ignored `work/` directory.
It fails closed on wrong host/kernel/CID, boot switch, renderer change,
missing desktop process, SSH failure, or a newly counted kernel fault.

Actual five-sample device result:
```json
{
  "result": "PASS_READ_ONLY",
  "samples": 5,
  "kernel_faults_before": 0,
  "kernel_faults_after": 0,
  "renderer": "SL101_DESKTOP_RENDERER=grate",
  "chroot_mount_count": 12,
  "processes": ["labwc"]
}
```
Boot ID remained constant, labwc PID was 6777 throughout, all five
mount counts were 12, memory pressure PSI `some avg10=0.00`.
Host tests: **7/7 PASS**.
Local ignored evidence files:
`work/sl101-first-four-review-20261105/passive-health.jsonl` and
`passive-health-kernel.jsonl`.

## Postflight and conclusions

After all live checks:
- Same boot ID, `labwc` PID 6777, Grate renderer, no browser running.
- Same 12 pre-existing chroot mounts; no `sl101-input-smoke` host mounts.
- No newly matching GPU/host1x/kernel fault entries.
- No Cog, WPE, rootfs, Mesa, KMS or desktop service was restarted, replaced,
  installed, or launched. No evdev event contents logged.

**Confirmed blocker:** current Cog/KMS chroot omits input nodes and udev data,
even though host permissions work. A namespace-first approach was proved
technically viable in isolation but still requires independent security review
and careful integration with the existing injection launcher and stale mount
ownership before live Cog input qualification.

**Required next stage:** finish and independently review input event-to-WebKit
instrumentation (OCP 05), resolve stale mounts under exclusive graphics
ownership, preserve injection functionality and cross-build/ABI-gate Cog;
then run a separately supervised 15-second KMS input test with recovery.
Keep Cog teardown packet `575970ad` on HOLD until reentrant UAF and
pageflip callback lifetime are fixed with real sanitizers.
The WPE producer-buffer oracle likewise cannot produce a verdict until a
synchronized modifier-aware EGL/GBM readback is implemented and compared with
the matching compositor frame.

### Re-run host sampler

```sh
python3 scripts/sl101-cog-passive-health-probe.py \
  --samples 5 --interval 1 \
  --output work/sl101-first-four-review-20261105/passive-health-kernel.jsonl
```

**This report contains no claim of a fixed live KMS input path or an
input-triggered freeze reproduced.**
