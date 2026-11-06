# SL101 Live-Deploiement: musl Grate Mesa, Sway, grüner swaybg (2026-11-06)

## Ergebnis

**Erfolgreicher kontrollierter Sway-Neustart mit dem neuen Mesa-Grate-musl-Build.**

Hostarchiv `work/sl101-grate-musl-20261106/grate-mesa25-musl-20261106.tar.gz` mit SHA-256
`09dc5991a18c3449c163c5ff8f8426f5d3e0f0a7a0210a764b055e19395234db`.

- Ziel: SL101 / native Nura/Alpine musl, Kernel `7.0.1-postmarketos-grate`, Hardware-CID auf mmcblk1 gegen den schon protokollierten SL101 geprüft.
- Neuer, isolierter Zielprefix: `/opt/grate-mesa25-musl-20261106`; keine Änderungen an `/usr/lib` oder am Debian-glibc-Chroot.
- Auf `/usr/local/bin/sl101-desktop` wurde ausschließlich die `GRATE_PREFIX`-Zeile auf den neuen privaten Prefix gesetzt. `/etc/sl101-desktop-renderer.conf` verbleibt bei `SL101_DESKTOP_RENDERER=grate`, `SL101_COMPOSITOR=sway`.
- `rc-service sl101-desktop restart` wurde mit bewaffnetem 90-Sekunden-Rollback ausgeführt und war erfolgreich. Aktueller neuer Sway-Prozess bei Erstprüfung: PID `10909`.
- **Beweis aus `/proc/10909/maps`:** `libgallium-25.0.7.so`, `libEGL.so.1.0.0`, `libgbm.so.1.0.0` und `libdrm.so.2.4.0` stammen aus `/opt/grate-mesa25-musl-20261106/lib/`.
- Prozessumgebung: `WLR_RENDERER=gles2`, `MESA_LOADER_DRIVER_OVERRIDE=grate`, `WLR_RENDERER_ALLOW_SOFTWARE=0` und unverändertes `LD_PRELOAD=/usr/local/lib/gr3d_serialize.so`. Der bestehende, ältere import-lists-Prefix bleibt **vor** dem neuen Mesa-Libdir im Library-Suchpfad: dessen `libdrm_tegra.so.0` hat Priorität. Diese Kompatibilitätsabsicherung wurde nicht heimlich entfernt.
- `swaymsg -t get_outputs` war erreichbar. Im Sway-Configfile ist permanent `output LVDS-1 bg #00b050 solid_color` ergänzt; laufender Prozess `swaybg -o LVDS-1 -c #00b050` wurde beobachtet.
- `nuraloumi-panel --live --enable-renderer-switch` läuft nach dem Neustart erneut.

**Aussagegrenze:** Erfolgreicher EGL-Loader/Process-Maps-/Sway-IPC-Test ist kein Hardware-Pixel-Orakel. Insbesondere ist nicht bestätigt, dass Fenster unter Grate ohne Grafikfehler gerendert werden, dass Cog/WPE korrekt läuft oder dass alle Texel/Stride/Damage-Pfade fehlerfrei sind.

## Registerwechsel: Implementierungsgrenze

Die zuvor diskutierte *cross-EXEC FP20-GPR-zu-Row-Register-Umlegung* (physische `r0-r3`-Allokation, auch Row-Lifetime/Remapping) existiert als **separater Compiler-Kandidat**, dokumentiert in `docs/sl101-fp-bank-lifetime-dossier-20261106.md` und `work/sl101-fp-row-lifetime-fix-20261106/`.

Sie ist **nicht als Produktionsfix im hier eingesetzten Mesa-Quellbaum** `build/mesa-grate-clean/mesa-25.0.7/src/gallium/drivers/grate/fp/tgsi.c` enthalten. Der neue musl Build ist die Portierung des vorhandenen EGL-/Cog-Grate-Standes, keine automatische Integration aller späteren FP-Register-Lanes. Der Row-Lifetime-Kandidat war für bestimmte Offscreen-Probes erfolgreich, ist aber noch kein allgemein qualifizierter Browser-GPR-Fix.

## Dauerhafte Rückfallmöglichkeit

Die vor der Änderung gesicherten echten Dateien sind auf dem SL101 erhalten:

```sh
/usr/local/bin/sl101-desktop.pre-musl-20261106
/home/user/.config/sway/config.pre-musl-20261106
```

Zur manuellen Wiederherstellung des zuvor laufenden Grate/Sway-Stands, direkt auf SL101 als root:

```sh
cp -p /usr/local/bin/sl101-desktop.pre-musl-20261106 /usr/local/bin/sl101-desktop
cp -p /home/user/.config/sway/config.pre-musl-20261106 /home/user/.config/sway/config
rc-service sl101-desktop restart
```

Sitzungsbezogener Auto-Rollback liegt zusätzlich unter `/run/sl101-musl-sway-green-20261106/rollback.sh`, durch erfolgreiche `success`-Markierung deaktiviert; `/run` ist flüchtig.

## Ausführung

Hostseitiges Deploy-Skript: `scripts/sl101-musl-sway-green-20261106.sh`. Dry-Run als Default, `--apply` ausdrücklich erforderlich. Skript ist **einmalig und fail-closed**: erneuter Aufruf mit `--apply` verweigert sich bei bereits vorhandenem Session-State/anderer aktiver `GRATE_PREFIX`-Zeile. Keine laufende automatische Änderungsroutine.

Verifizierte Live-Ausgabe (SSH read-only nach Neustart):

```text
sl101-desktop: requested=grate renderer=gles2 kernel=7.0.1-postmarketos-grate
SWAY_PID=10909
/opt/grate-mesa25-musl-20261106/lib/libgallium-25.0.7.so
/opt/grate-mesa25-musl-20261106/lib/libEGL.so.1.0.0
swaybg -o LVDS-1 -c #00b050
```
