# SL101 Sway + neuer musl Mesa: Live-Videotest (2026-11-06)

## Ergebnis: Videodarstellung NICHT qualifiziert

Der Benutzer beobachtet bei Video unter dem laufenden Sway-GLES2-Grate-Desktop wieder **massive bekannte Grafikfehler**, obwohl einfache Sway-Fenster/Terminaltext zuvor sauber erschienen. Das ist ein unmittelbarer visueller Negativbefund und darf nicht als Pixel-PASS ausgegeben werden.

Während sämtlicher Versuche blieb der Sway-Prozess PID `10909` am Leben; `/proc/10909/maps` wies `/opt/grate-mesa25-musl-20261106/lib/libgallium-25.0.7.so` nach. Kein Wechsel zu Pixman, kein KMS, kein Compositor-Neustart.

### Testmatrix

| Versuch | Pipeline | Ergebnis |
| --- | --- | --- |
| VDE→Wayland DMA_DRM, Audio via PulseAudio | `filesrc → qtdemux → h264parse → v4l2slh264dec → video/x-raw(memory:DMABuf),format=DMA_DRM → waylandsink` | **FAIL**, `Unsupported pixel format`, `not-negotiated`, exit 1. Der treiberspezifische Kachelausgabemodus wird auf diesem Weg nicht als kompatibles Wayland-DMABuf ausgehandelt. |
| VDE→I420→Wayland RGBx, Audio via PulseAudio | `v4l2slh264dec → video/x-raw,format=I420 → videoconvert → waylandsink fullscreen=true` | **EOS/exit 0** für 17,25-s-H.264-Clip `/home/user/tds3e1-main.mp4`, 854×480/24fps; Decoder-Caps I420 und Sink-Caps RGBx verifiziert. **Aber bekannte massive Pixelkorruption laut Benutzer**, kein Visual-PASS. Hardware-VDE-Decode ist aktiv, aber das Kachel→I420-/Farbraumkonvertierungs-/Wayland-Compositing-Stück ist nicht korrekt qualifiziert. |
| mpv wlshm CPU-Kontrollpfad | `mpv --hwdec=no --vo=wlshm --fullscreen --ao=pulse` für denselben Clip | Screenshots nach 4 und 9 s aufgenommen, Lauf durch 26-s-Bound begrenzt (exit 143); Audio-Underruns und `Audio/Video desynchronisation detected`. **Kein A/V-PASS**. Pixelqualität nicht unabhängig qualifiziert; etwaige dort beobachtete Fehler sind vom VDE-Konverter zu trennen. |

Wichtig: **Der VDE-Test ist kein reiner Software-Decode.** VDE dekodiert Hardware-H.264; der Pfad I420→RGBx/Wayland-Buffer verwendet jedoch Software-Konvertierung/-Kopien. Die mpv-Probe war bewusst ein separater rein softwaredekodierter Kontrolllauf.

Der bereits länger dokumentierte YM12→I420-VDE-Fehler (`docs/sl101-video-playback.md`) kann die berichteten Pixelartefakte erklären. Der Renderer-Fehler beim Videofenster/Stride/Buffer-Import ist als zweite Ursache weiterhin offen. Die Fotobeobachtung alleine trennt diese Ursachen nicht.

### Reproduzierbare Evidenz

Roh-Logs und `grim`-Captures nach 4/9 s liegen unter:

```
work/sl101-video-sway-musl-20261106/
  vde-dmabuf.log
  vde-dmabuf-run.log
  vde-i420.log
  vde-i420-4s.png
  vde-i420-9s.png
  mpv-wlshm.log
  mpv-4s.png
  mpv-9s.png
```

Auf dem SL101 selbst: `/tmp/sl101-video-sway-musl-20261106/`. Die PNGs haben verschiedene Hashes je Zeitpunkt, aber das ist **kein** Nachweis korrekter Bildinhalte, weder vollen Bildlaufs noch korrekter Video-PTS. Der User meldet explizit die bekannten starken Bildfehler.

### Sichere Fortsetzung

1. Zuerst Videoinhalte der VDE-I420- und mpv-wlshm-Captures gegen tatsächliche Referenzframes vergleichen. Der Unterschied trennt decoderseitige Pixelkorruption von renderer-/importseitiger Korrumpierung.
2. Die DMA_DRM-Fehlverhandlung beheben; Tegra-VDE tiled Formate/modifier, dmabuf import, Wayland-Feedback und stride/plane alignment müssen korrekt durch die V4L2→Wayland→Grate-Kette geführt werden. **Kein bloßes Durchzwingen falscher Caps**.
3. Alternativ den bereits getesteten VDE→KMS-Direct-Scanout getrennt wiederholen, **nur** mit exklusivem Graphics-Slot und expliziter Einwilligung, weil der aktuelle Sway dafür gestoppt werden muss.
4. Für mehr als kleine Proben Audio-Drops, Frames, FPS und Kernel-Fehler mit unabhängiger Evidenz prüfen.

Kein permanenter Video-Launcher installiert; keine Änderung an Mesa, Sway, Hintergrund, Paketstand oder Audio-Konfiguration. Kurze Testprozesse sind alle beendet.
