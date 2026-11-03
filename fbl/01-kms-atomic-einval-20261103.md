# SL101 FBL lane 01 — Cog atomic EINVAL, 2026-11-03

OCP: SL101-LINUX-01-PROMPT-KMS-ATOMIC-EINVAL-20261103-324D9D

Previous evidence (fbl/00-SUMMARY): WebProcess GR3D submits and PRIME export, Cog PRIME import and ADDFB2 success, then MODE_ATOMIC EINVAL and a separate release-buffer crash. This does not prove displayed GPU pixels. **Live capture now confirms the immediate EINVAL cause:** the kernel reported `[drm:tegra_fb_get_tiling] unknown format modifier: ffffffffffffff`, followed by `[PLANE:33:plane-0] atomic driver check failed` and `-22`. The traced Cog ADDFB2 payload for FB 103 showed 1280x800, AR24, pitch 5120, `flags=2` (modifier flag), and modifier `0x00ffffffffffffff` (DRM_FORMAT_MOD_INVALID). The matching atomic request set FB 103 on plane 33; the Tegra driver's tiling decoder rejected the modifier. This narrows failure to **invalid/implicit modifier passed as explicit framebuffer modifier**. Fix must verify true memory layout before choosing an implicit/no-modifier AddFB2 path or correctly advertised supported modifier. BOTTOM_UP is known to affect Tegra scanout orientation, but its presence on WPE buffers has not been measured.

Read-only SSH identified sl101-nura, 7.0.1-postmarketos-grate, ASUS Eee Pad Slider SL101. Unprivileged reading of drm.debug was denied.

Execute scripts/sl101-fbl01-kms-atomic-capture.sh --dry-run first; --execute is disruptive and requires exclusive live-graphics ownership. It captures ADDFB2/ATOMIC ioctl trace and before/after dmesg to /tmp on device, and restores the exact original drm.debug value using a trap. It does not deploy libraries or change renderer defaults.

Next isolate the rejected atomic property array (object IDs, plane IN_FORMATS, rotation, FB IDs) and the exported buffer's fourcc/modifier/pitch/tiling/GEM flags/BOTTOM_UP. Compare SCANOUT allocation with WPE BACKBUFFER/SHARE; choose linear scanout or Cog GLES compositor only on measured evidence. Keep CPU Skia raster by default. Audit failed-flip release and asynchronous fence lifetime separately.

Live run used GNU-style timeout initially (unsupported on target BusyBox); corrected run reproduced the kernel rejection, but outer timeout killed the straced wrapper and left Cog running. The exact pre-run drm.debug value 0 was restored. Lane 01 sent SIGTERM specifically to the remaining Cog PID 28316; wrapper resumed and `rc-service sl101-desktop status` reported `started`. The script now uses an inner 35-second sl101-kms-run timeout before the 75-second outer guard to give the wrapper time to restore desktop state. This revised safety gate has not yet been live exercised.

Still required: DRM GET_FB2/PRIME pixel readback (handle format/mapping errors), independent frame count and software pixel baseline, verified visible output, and independent review. Submissions or rAF alone are insufficient.
