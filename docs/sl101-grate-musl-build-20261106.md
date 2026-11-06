# SL101: Grate Mesa 25.0.7 mit Cog-EGL-Fixes als musl/ARMv7 Build (2026-11-06)

## Status und Artefakt

**HOST-BUILD ERFOLGREICH / NICHT AUF TABLET AUSGEROLLT.** Unabhängiger,
gemeinsam gebauter musl-Satz aus Mesa EGL, GLESv2, GBM, Gallium/Grate sowie
Grate-libdrm_tegra und Alpine-libdrm. Die Debian-glibc-Installation und der
laufende Nura-Desktop wurden nicht verändert.

- Build-Archiv: `work/sl101-grate-musl-20261106/grate-mesa25-musl-20261106.tar.gz`
- SHA-256: `09dc5991a18c3449c163c5ff8f8426f5d3e0f0a7a0210a764b055e19395234db`
- Privater Zielpräfix: `/opt/grate-mesa25-musl-20261106`, Libdir: `lib`
- Rebuild: `bash scripts/sl101-grate-musl-build.sh all`
- Einzelphasen: `fork`, `mesa`, `audit`.
- Build-Protokolle: `work/sl101-grate-musl-20261106/{build.log,mesa.log,final-build.log}`.
- Nebenprodukte/Quellkopien liegen ausschließlich unter dem ignorierten `work/`-Baum; der ABI-relevante Original-Mesa-Quellbaum bleibt unangetastet.

## Quelle/ABI

Der musl-Build verwendet die im bisherigen glibc-Cog/Mesa-Build vorbereitete,
zusammenhängende Mesa-25.0.7-Quelle:

`build/mesa-grate-clean/mesa-25.0.7/`

Die beiden Cog/Wayland-EGL-Fixes sind explizit im Build-Skript überprüft:
1. `src/egl/drivers/dri2/platform_wayland.c`: bei leerer Wayland-Format-Bitmap und vorhandenem Render-GPU-FD die eigenen Treiberformate für EGL-Konfigurationen zulassen (Cog-FDO-Nested-Compositor).
2. `src/egl/drivers/dri2/egl_dri2.c`: NULL-Guard für `dri_screen_render_gpu` / `pipe_screen` in `dri2_setup_screen`.

EGL-Datei-SHA-256 beim Build:
- `egl_dri2.c`: `75d96f33d00d4d90d0c361857384052365c7c943b8507f96f82880a2d741f1ec`
- `platform_wayland.c`: `f2cbe16c88c3e2d4933d9a3dab66dd602461c12d936db808230b773ffaf5f035`

Die Grate-Treiberquelle ist in diesem vorbereiteten Source-Tree enthalten. Das Grate-libdrm-2.4.97-Fork enthält die notwendige private Tegra-API, erfüllt aber *nicht* Mesas Core-libdrm-Mindestversion >=2.4.109. Deshalb wird nur dessen **musl-built libdrm_tegra** verwendet. Das **musl-built core libdrm 2.4.120** und seine Entwicklungsheader stammen aus Alpine 3.20 (armv7) und werden im privaten Prefix mitgeliefert. Der Grate-DMA-BUF-Fix `SEEK_CUR -> SEEK_SET` bleibt aktiviert. Kein Fälschen der pkg-config-Version.

- Host: Arch Linux x86_64; GCC cross `arm-linux-musleabihf-gcc 11.2.1`; Meson `1.12.0`.
- Ziel: ARMv7-A, Hard-Float VFPv3-D16, **kein NEON als Buildziel**; `-DNO_FORMAT_ASM`; `-Dgallium-drivers=grate,softpipe`.
- libc: musl, `libEGL.so.1` NEEDED `libc.so` statt `libc.so.6`; Core-libdrm NEEDED `libc.musl-armv7.so.1`.
- Verbleibende Target-Systembibliotheken: musl Loader, `libstdc++.so.6`, `libgcc_s.so.1`, Wayland-Client/Server, zlib, libffi. Loader-Konfiguration ist **pro Launcher**, nicht global, zu wählen.

## Verifikationsbelege

- Vollständiges Meson/Ninja Cross-Build und Staging: **PASS**.
- ELF32 ARMv7, `Tag_FP_arch: VFPv3-D16`, `Tag_ABI_VFP_args: VFP registers`: **PASS** bei EGL, GLESv2, GBM, Gallium und libdrm_tegra.
- Direkte `NEEDED`-Prüfung auf glibc-Einträge: **PASS**.
- Alpine-3.20-armv7-Docker/QEMU: `ld-musl-armhf.so.1 --list` löst die Abhängigkeiten von EGL, GLESv2, GBM und Gallium aus dem privaten Präfix und den Alpine-Systempaketen auf: **PASS**.
- ARMv7-musl-Testbinary ruft `eglQueryString(EGL_NO_DISPLAY, EGL_EXTENSIONS)` erfolgreich auf: `EGL loader OK, client extension string length: 338` (**PASS**). Das ist **kein** GPU-, EGLDisplay- oder Cog-Test.
- `make test`: **PASS**, 592 Tests (ein Skip).
- `make check`: **PASS**.

## Sichere Übernahme auf den Alpine-Host

Das Paket ist absichtlich nicht ins glibc-Debian-chroot und nicht in die
Alpine-Standardbibliotheken installiert worden. Vor der Verwendung:

1. Zielidentität (SL101-Serienkennung, Kernel, Alpine/musl ABI), Platzbedarf,
   native libstdc++/libffi/Wayland-SONAMEs und DRM-UAPI **read-only** erneut
   prüfen. Das getestete Alpine-3.20-SDK ist nicht automatisch identisch mit
   dem laufenden postmarketOS.
2. SHA-256 des übertragenen Archivs vor dem Entpacken erneut vergleichen.
   Archiv enthält `./opt/grate-mesa25-musl-20261106/`; nur in diesen neuen
   privaten Präfix entpacken. Vorhandenen Präfix nicht blind überschreiben.
3. Nur für einen einzeln gestarteten Probeclient die Variablen setzen:
   `LD_LIBRARY_PATH=/opt/grate-mesa25-musl-20261106/lib`,
   `GBM_BACKENDS_PATH=/opt/grate-mesa25-musl-20261106/lib/gbm`,
   `MESA_LOADER_DRIVER_OVERRIDE=grate` und bei Bedarf
   `EGL_PLATFORM=wayland`. Keine `ld-musl-armhf.path`- oder
   `/usr/lib`-Standardumstellung.
4. Hardware-Qualifikation separat: GR3D-Rendernode, korrekte Pixel/
   Shader, Cog-FDO/EGL Wayland-Formatfeedback, DMA-BUF-Import/Stride,
   Touch/Keyboard, Audio und stabile Wiedergabe. **EGL-Init/Linker-Erfolg
   ist kein Nachweis für korrekte GPU-Pixel.**
5. Rückfall: Probeclient stoppen, dessen Umgebungsvariablen/Launcher
   zurücksetzen, dann bisherigen Pixman/Software-Desktop unverändert
   benutzen. Keine standardmäßige Aktivierung, solange EGL-/Pixel-Orakel
   und rollbackfähige Livesession nicht bestätigt sind.

**Keine SSH-Session, kein grafischer Sessionwechsel, kein Reboot, kein Deploy
und keine Änderung an Debian-/Alpine-Systempfaden durch diesen Build.**
