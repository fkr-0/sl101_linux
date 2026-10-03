# SL101 Firefox deployment — 2026-10-03

## Delivered

Firefox ESR 140.16.0esr-1~deb13u1 (Debian armhf) under
`/opt/sl101-firefox-debian`. Launch with `/usr/local/bin/sl101-firefox` or
**Firefox (SL101)** in the application menu. A normal browser window is left
open on https://en.wikipedia.org/wiki/Linux and shared by existing WayVNC.
The original Nura/musl Firefox package remains installed separately.

Target: SL101 SD CID 035344534c31323880ac79a543010300,
kernel 7.0.1-postmarketos-grate, root@192.168.23.106.
Compositor remained labwc27352/pixman throughout browser qualification.
No GPU candidate, kernel, boot renderer or desktop service was changed.

## Package provenance and CPU diagnosis

Debian official trixie-slim ARMv7 image digest:
sha256:a99cfc517144bc59b1978475ec53b46ecabec7e43635402ee5b77cc54cd1b20a.
Export SHA256:
9312e8243384574a9ab866dedfdd93bccf5359b4163b9bf22db6a770bc0afdc9.
APT verified signed trixie, trixie-security and trixie-proposed-updates indexes.
Current package came from signed trixie-proposed-updates, not trixie-security.
Its published deb SHA256:
afefe95a54102a149e9b56ea026f328be585814986479c877b0f8b05bf09d843.

Installed Nura Firefox154 SIGILLs on vmov.i32 q8,#0 before --version.
Debian Firefox153.4 --version works, but real GUI startup SIGILLs on
vmov d16,r0,r1 at libxul virtual offset 0xa391d80. Disabling JS JIT tiers
and Wasm did not restore startup; the unsupported instruction is in the
file-backed library. Tegra20 has VFPv3-D16, without NEON or d16-d31.
ESR140.15 passed the browser gates, then ESR140.16 was installed and retested.
ESR140 uses the normal JS configuration; no JIT-disabling preferences remain
in its active profile.

The isolated APT preferences prefer firefox-esr version140.* to prevent
reinstalling the demonstrated broken153 package. Proposed updates have low
priority for other packages; no host APK sources/packages were changed.
This is a compatibility policy, not a supported long-term browser baseline.
Mozilla ended ESR 140 support with the Firefox 157 / ESR 153.4 release on
2026-09-29; 140.17.0 is the final ESR 140 build. The deployed 140.16 instance
therefore remains a compatibility/recovery browser only, not a durable security
baseline for routine untrusted browsing. A 140.17 point update may still be
qualified as the final branch build, but it does not restore ongoing security
support. Qualify a newer CPU-compatible branch before treating Firefox as the
primary browser again.

## Runtime isolation

`sl101-firefox` prepares only selected device bindings, a128MiB /dev/shm,
/proc and the existing Wayland socket. It enters a private mount namespace,
recursively binds the Debian root, pivot_roots into it, detaches the host root,
and drops to browser UID/GID1000 before starting Firefox. The namespace entry
helper is `/usr/local/libexec/sl101-firefox-enter`.

Plain chroot rejected unprivileged user namespaces; a live A/B probe showed
host user namespaces available and chroot namespaces denied. Private-root
entry restored user namespaces. Final Firefox logs lack that denial, and
content processes report Seccomp2, zero effective capabilities, and distinct
user namespaces. No Firefox sandbox-disabling variables were used.

Wayland socket ownership is root:1000, mode0660, to allow the dedicated account
access. Other root desktop clients remain able to connect. On compositor
restart the launcher refreshes the socket binding and permissions. UID1000 is
created only in the Debian root, not in the host password database.

Profile: /home/browser/esr140-profile inside Debian. Earlier153 diagnostic
profiles are retained separately. Software WebRender is forced; GL acceleration
and WebGL are disabled for this first CPU-compatible qualification. Browser
runtime and Mesa libraries remain separate from the private Grate candidate.
No browser autostart or default-browser MIME association was changed.

## Verification

- Version:140.16.0esr; native target startup without SIGILL.
- Headed Wayland browser, not headless.
- HTTPS example.org: correct title, complete document, normal TLS validation.
- Actual Linux Wikipedia article:85800+ text characters, visible image and CSS;
  measured load6.45seconds in the final test (not a general benchmark).
- JavaScript arithmetic loop updates DOM to JS PASS49995000.
- WebDriver sends SL101 keyboard into a real input; DOM value matches.
- Scroll moves the document600pixels; screenshot captured.
- Actual VNC framebuffer1280x800 inspected: correct browser chrome, panel,
  article text and Tux image. Initial capture during startup was uniform gray;
  post-load capture is the final visual evidence.
- Final normal browser restarted without Marionette; localhost2828 listener absent.
- Resource sample:305817KiB summed PSS, approximately299MiB. RSS sums include
  shared pages repeatedly and are not used as unique memory.
- Content sandbox seccomp filters and user namespaces observed.
- Kernel delta checked after the run; no new GPU faults expected on pixman.

Host evidence: work/sl101-firefox-debian-20261003/.
Target evidence: /var/lib/sl101-firefox-smoke/.
Source launcher/helper, image/package inventories, library SHA256, rejected153
GDB traces, successful140 test receipts, resource snapshot and VNC PNG retained.
Browser profiles, private user data and credentials are not archived.

## Operation and remaining gates

Launch `/usr/local/bin/sl101-firefox [URL]`; the same profile can receive later
launches. The entry script recreates temporary mounts after a reboot, but this
has not been reboot-qualified. Debian updates must occur inside the isolated
root. To change major browser branches, keep the current profile and qualify a
new profile plus exact package first.

Pending: physical touch/keyboard review, video/audio/codecs, downloads,
JS-heavy user applications, longer memory/CPU soak, reboot launch, and GPU
browser acceleration. Native WLR compositor rendering is still pixman here.

Rollback: close the browser; disable the added application entry if no longer
wanted. Keep the isolated root and evidence until reviewed. After all browser
processes exit, selected mounts can be unmounted. Restore the live Wayland
socket to root:root0755 if retiring this integration. No system Mesa restore
or host OS replacement is necessary.
