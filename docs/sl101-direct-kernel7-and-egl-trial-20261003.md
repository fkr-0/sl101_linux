# SL101 direct kernel 7 boot and renderer trial

An ordinary reboot returned the identified `.106` tablet directly to
`7.0.1-postmarketos-grate`, with a new boot ID, the installed internal boot-image
hashes, `kexec_loaded=0`, no enabled kexec service and no pending handoff markers.
A separate full power-off/on cycle has not been observed.

The approved internal Android boot-image update preserved its root command line.
Header offset: 8912896; page size: 2048. Kernel SHA256:
`794a3766aed121654aed5b88f3a8d826f38b47fa4fcfb5bb01d3267518a0d9e1`.
DTB SHA256: `01fbb5a935e429c42dc5e2793049bbfc91ff3a6f73c15f2063e1fb0af1a289b0`.
Kernel 7's installed module manifest was verified before reboot.

The guarded rawboot transaction was rehearsed on a host shadow image. Fresh
32 MiB readback after the write matched that shadow exactly. The conservative
backup window is the previous image's 8167092-byte occupied extent, not a claimed
partition boundary. Host recovery files are in
`tmp/sl101-nura/default-grate-20261003/boot-recovery/`; device recovery files are
in `/var/lib/sl101-kernel7/direct-boot-backup-20261003/`.
Backup SHA256: `be4da660d957db7b74b3b895c857ff929bde74c221f0bde6372899ec77099b15`.
Write receipt: `/var/log/sl101-kernel7-direct-write-20261003.json`.
The old internal 6.18 image is backed up; it is no longer the default cold-boot
image or an automatic fallback. Recovery requires the guarded restore workflow.

The persistent renderer wrapper booted the hash-qualified Grate prefix. The
user then confirmed distorted drawing on both VNC and the real screen, so
`/etc/sl101-desktop-renderer.conf` was returned to
`SL101_DESKTOP_RENDERER=pixman` and the desktop restarted. Direct kernel 7 boot
was retained. The visual regression reproduction and repeat instructions are
in [the pixel-gate report](sl101-egl-visual-regression-20261003.md).

For the reported bottom-right to top-right touch inversion, labwc's Atmel
maXTouch calibration matrix was changed from `1 0 0 0 -1 1` to identity
`1 0 0 0 1 0`. No kernel inversion property was present. Physical corner checks
are still required before calling touch corrected.
