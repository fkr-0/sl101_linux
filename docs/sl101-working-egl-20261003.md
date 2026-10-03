# SL101 EGL working review candidate — 2026-10-03

User confirmed that the latest review screen is clean. Preserve this as a
visually accepted review candidate, not full EGL conformance or boot qualification.

Driver SHA256: 68a78e18af642275d3fec6fc93a4f20cd618d9f951981c7e240d5731e7f29ade.
Private prefix: /opt/grate-mesa25-texfuse-68a78e18af642275d3fec6fc93a4f20cd618d9f951981c7e240d5731e7f29ade.
Kernel: 7.0.1-postmarketos-grate.
SD CID: 035344534c31323880ac79a543010300.

Live review labwc26494 mapped this exact library, WLR_RENDERER=gles2,
GL vendor Grate / renderer Tegra. WayVNC shared the real display via SSH.
Evidence: /var/lib/sl101-egl-review-20261003-123045.
Archived exact target driver: work/sl101-egl-review-20261003/accepted-68a78e18/.
The prefix's inherited manifest names an older artifact: it is not current
provenance. Fresh review provenance records the verified current hash.

Subsequent inspection found labwc27352 on pixman. The transition cause is not
established. Persistent boot renderer remains pixman. The preserved trial launcher
is work/sl101-egl-review-20261003/start-review.sh; it is not a boot service.

Next gates, in order:
1. Exact-hash isolated pixel oracle: ARGB, XRGB, padded pitch, alpha source-over,
   scissor, overlap and partial damage; pixman control must pass.
2. Real-display application interaction: terminal scroll/resize, multiple windows,
   panel popups, fullscreen, keyboard and touch; inspect VNC and physical display.
3. 30-minute repeated interaction soak: process RSS, kernel fault delta, trace
   GR3D submissions correlated with the tested labwc process; investigate exits.
4. Browser CPU compatibility, text/image/scroll/input, memory and TLS smoke.
5. Reversible supervised default-renderer promotion with hash checks and recovery;
   ordinary reboot then physically supervised cold boot, including VNC startup.

Suspend is outside these gates and requires separate physical supervision.
