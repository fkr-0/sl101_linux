# SL101: tatsächlicher GStreamer/VDE-Verarbeitungspfad (Debian .100 vs Nura .106)

2026-11-11. Live-Read-only-Audit mit gleichen H.264-Eingabedaten, identischem CMA-Kernel und GStreamer-Diagnoseaufrufen. **Kein Device-Flash, kein Reboot, keine Paketinstallation, kein KMS-Master-Wechsel.** Originalmessungen unter work/sl101-gst-processing-path-20261111/ (gitignored).

## Identität und identischer Inhalt

- Debian .100: sltwrpbootdebian, Kernel 7.0.1-postmarketos-grate-dmavde1, GStreamer **1.26.2**, Plugin /usr/lib/arm-linux-gnueabihf/gstreamer-1.0/libgstv4l2codecs.so, glibc 2.41.
- Nura .106: sl101-nura, derselbe Kernel 7.0.1-postmarketos-grate-dmavde1, GStreamer **1.28.7**, Plugin /usr/lib/gstreamer-1.0/libgstv4l2codecs.so, Alpine/musl.
- Beide auf AC; VDE cached_capture=N, /dev/media0 enthält tegra-vde-proc. Die Geräteneuerkennung aus dem Gst-Debuglog ist bei beiden vorhanden.
- Testclip: identischer SHA-256 e554039c0214ca939cea0ecf30081664ee0a89cc2820ca63944102214dbd407c, 96 H.264-Frames, 854×480 @ 24 fps, constrained-baseline, Level 3.1.

## REALER Graph aus GstPad-Caps (nicht bloß Pad-Templates)

    MP4-Datei
      filesrc
        ↓
      qtdemux                  video/x-h264 (AVC, AU alignment)
        ↓
      h264parse                parsed AVC, constrained-baseline L3.1, 854×480, 24/1
        ↓
      v4l2slh264dec            GstH264Decoder → Linux V4L2 Stateless Request API
        ├─ /dev/media0         tegra-vde-proc
        ├─ VDE-Hardware        H.264-Bilddekodierung
        ├─ Hardwareformat      I420 (V4L2-Breite intern auf 864 aufgerundet)
        └─ Decoder src caps    video/x-raw, format=I420, width=854, height=480, framerate=24/1
        ↓
      fakesink sync=false      Frames werden verworfen; keine KMS/Wayland-Ausgabe

**Wichtig:** In beiden echten Pipelines sind die finalen Caps **video/x-raw, I420**, nicht video/x-raw(memory:DMABuf). V4L2 bietet DMABuf-Export als Capability an (DMA_DRM/YU12), aber dieses Feature ist NICHT als ausgehandelter Link zur Senke belegt. Kein videoconvert, videoscale, software-decoder oder GPU compositor zwischen VDE und fakesink. Das schließt implizite CPU-Mappings innerhalb der V4L2/GStreamer-Implementierung nicht aus; die Logs allein beweisen keine generelle Zero-Copy-Eigenschaft.

Übereinstimmende Gst-Debug-Ereignisse je 96-Frame-Decode:

- **96×** gst_v4l2_codec_h264_dec_output_picture;
- **96×** gst_v4l2_request_set_done;
- **96×** gst_v4l2_codec_allocator_alloc;
- **192×** gst_v4l2_codec_allocator_release (INPUT + CAPTURE pool);
- 10 V4L2 codec buffer objects angelegt, 10 wieder freigegeben.

Der Buffer-Lifecycle und die Caps stimmen strukturell überein. Der entscheidende Unterschied liegt in der Zeit pro ausgegebenem Frame.

## Stufenmessung (sechs unabhängige Durchläufe pro Pipelinevariante)

Dieselben Gst-Launch-Prozesse; Kinder-CPU-Zeit aus getrusage(RUSAGE_CHILDREN) und Wall-Time per perf_counter_ns. Alternierende Reihenfolge. Zahlen = Median in Millisekunden.

| Pipelinevariante | Debian Wall | Nura Wall | Debian User-CPU | Nura User-CPU |
| --- | ---: | ---: | ---: | ---: |
| fakesrc num-buffers=0 → fakesink (Initialisierung) | 133.824 | 202.589 | 108.457 | 148.322 |
| filesrc → qtdemux → h264parse → fakesink | 172.968 | 246.719 | 124.578 | 179.327 |
| filesrc → qtdemux → h264parse → **v4l2slh264dec** → fakesink | **1494.237** | **939.546** | **1236.486** | **646.952** |
| **Differenz: Decoder zusätzlich zu Parser** | **1321.269** | **692.827** | **1111.908** | **467.625** |

Fazit: Debian ist beim Start und Parser **schneller**, aber nach Einschaltung der stateless V4L2-Decoding-Kette **~555 ms langsamer** für 96 Frames; die zusätzliche User-CPU liegt ~590 ms höher. Die um Parser-Only bereinigte decoderbezogene Mehrarbeit beträgt Wall ~628 ms und User-CPU ~644 ms. Ein allgemeiner glibc- oder MP4-Demux-Nachteil erklärt das nicht.

## Einzelbild-Timing direkt aus GStreamer-Debugereignissen

Zeitstempel aus v4l2codecs-h264dec::output_picture (96 Events, gleicher Clip):

| Metrik | Debian .100 | Nura .106 |
| --- | ---: | ---: |
| Median zwischen zwei ausgegebenen Bildern | **12.954 ms** | **6.573 ms** |
| p95 zwischen zwei ausgegebenen Bildern | **14.259 ms** | **8.805 ms** |
| Gesamte Spanne der 96 output_picture-Ereignisse | 1263.447 ms | 654.681 ms |
| Allocator-Event-Abstand p50 | 12.970 ms | 6.570 ms |

Gleich viele Bilder, aber nahezu doppelte per-frame-Dauer auf Debian.

## Frame-Sweep / Test auf fixe Startkosten vs Kosten pro Bild

Der identische Pipelinegraph wird mittels fakesink num-buffers=N nach N ausgegebenen Bildern beendet. Vier Läufe pro N und Gerät; Median:

| fakesink N | Debian Wall | Nura Wall | Debian User-CPU | Nura User-CPU |
| --- | ---: | ---: | ---: | ---: |
| 12 | 476.127 ms | 485.976 ms | 302.457 ms | 232.301 ms |
| 24 | 625.964 ms | 527.266 ms | 437.315 ms | 311.869 ms |
| 48 | 920.139 ms | 669.187 ms | 733.349 ms | 415.368 ms |
| 96 | 1439.801 ms | 916.722 ms | 1237.038 ms | 665.107 ms |

Die Debian-Mehrkosten wachsen mit der dekodierten Framezahl. Bei nur zwölf Bildern liegt Debian leicht vorn; bei 96 Bildern ist es +523 ms langsamer. Das spricht **gegen eine reine Plugin-Initialisierungsabweichung** und für einen per-picture-Pfad im GstH264Decoder/V4L2-Request-/Buffer-Handling oder dessen Kernelkommunikation.

## Tatsächliche CPU-, VDE- und Speichertakte unter Last

Zwei reale 96-Frame-Decodes pro Gerät, 40-ms-Polling von clk/debugfs und cpufreq. Das Sampling selbst kann Laufzeiten geringfügig beeinflussen; es wurde auf beiden Geräte identisch angewendet.

| Takt | Debian .100 | Nura .106 |
| --- | --- | --- |
| CPU (meiste Samples) | 1.000 MHz (67/72) | 1.000 MHz (38/44) |
| VDE-Hardware | **300 MHz (72/72)** | **300 MHz (44/44)** |
| EMC, aktiver Wert | 600 MHz (59/72) | 600 MHz (29/44) |
| Host1x | 150 MHz durchgehend | 150 MHz durchgehend |

Beide hatten VDE-Clock enabled, wenn der Decoder aktiv war. Somit ist eine simple 2:1-VDE-Taktabweichung **nicht belegt**, und CPU/EMC sehen ebenfalls ähnlich aus. EMC 300 MHz ist an Anfang/Ende einiger Intervalle normal; kein durchgehender Wert garantiert.

## Diagnosegrenze: zusätzlicher Gst-Latency-Tracer

- Auf .106 gelang GST_TRACERS='latency(flags=pipeline+element)' mit 96 registrierten Element-Latenzen je Decoder- und Parser-Element (v4l2slh264dec0 median ca. 20.413 ms pro Tracer-Event; diese per-element-Latenzen entsprechen **nicht** der Nettoausgabeperiode oder exklusiver User-CPU).
- Auf .100 wurde derselbe **instrumentierte** Durchlauf nach Timeout beendet; das 5-KB-Debuglog enthielt nur die Tracer-Initialisierung und keine verwertbaren Elementereignisse. Keine verbleibenden gst-launch-Prozesse, /dev/video0 weiterhin vorhanden und keine neuen CMA/DMA/VDE-Kernel-Fehler festgestellt.
- **Keine** Profildaten oder A/B-Schlüsse aus dem fehlgeschlagenen Debian-Tracer ziehen. Die nichtinstrumentierten Debian-Decode- und Frame-Sweep-Läufe waren alle erfolgreich.
- Ausführliches System-Call-Profiling wurde nicht durchgeführt; keine Behauptung über ioctl-Zeitanteile, Kopierzahlen oder eine konkrete Hotspot-Funktion.

## Ursachenhypothese und nächste Trennexperimente

**Beobachtet:** gleiches Kernelrelease, derselbe Video-/Media-Graph, dasselbe Ausgabeformat, dieselbe Framelast und nahe identische Betriebsfrequenzen. Der Mehrverbrauch entsteht pro Frame in der Hardwaredecoder-Integration und im dazugehörigen Userspace.

**Nicht nachgewiesen:** spezifischer Code-Hotspot oder Kausalität der GStreamer-Version. Wichtigste Unterschiede bleiben:

- Debian: Gst-Plugins-Bad/Codecs/V4L2 1.26.2, glibc 2.41, Debian ARMHF-Compilerflags.
- Nura: Gst-Plugins-Bad/Codecs/V4L2 1.28.7, musl, Alpine ARMv7-Buildflags.
- Mögliche Unterschiede in Request API Control-Setup, H.264 DPB-Verwaltung, Buffer-Allocations oder implizitem Mapping; VDE-Treiber ist derselbe Quellstand, aber physische Geräte können trotzdem unterschiedlich reagieren.

**Nächstes entscheidendes Experiment:** GStreamer 1.28.x **isoliert unter Debian** bauen/ausführen (ohne den produktiven 1.26-Stack systemweit zu überschreiben), dieselben 96 Frames und identische Stage-/Frame-Sweep-Metriken. Dies trennt einen Versions-/Buildwechsel von physischen Unterschieden und glibc. Bei Bedarf zusätzlich gleiche GStreamer-Version auf beiden Geräten unter kontrolliert gleichem Userspace, und gezieltes Call-Stack-Profiling des v4l2codecs-H.264-Prozesses. Kein voreiliges Paketupgrade des produktiven Systems.

Offizielle Referenz zur Funktion: https://gstreamer.freedesktop.org/documentation/v4l2codecs/v4l2slh264dec.html ; Versionshinweise: https://gstreamer.freedesktop.org/releases/1.28/ .

## Gesicherte Rohdaten

Alle privaten Originaldaten sind getrennt nach Gerät SHA-256-gesichert in:

    work/sl101-gst-processing-path-20261111/

- 100-verbose.log, 106-verbose.log — tatsächlicher Gst-Caps/Decoder-/Allocator-Ablauf.
- 100-stage-bench.json, 106-stage-bench.json — sechs pro Stufe.
- 100-frame-sweep.json, 106-frame-sweep.json — vier pro Framelimit.
- 100-clock-sweep.json, 106-clock-sweep.json — CPU/VDE/EMC-Sampling.
- 100-gst-latency-tracer.log (nur Initialisierung/Timeout),
  106-gst-latency-tracer.log (96 Frame-Latenz-Events je Element).

Die gleichen Testdateien existieren auf den Geräten in
/root/hwrun/qa-dmavde1/gst-path-audit-20261111/.

**Beide SL101 bleiben unverändert auf dem Vier-Patch-CMA-Kernel;
keine Kernel-, Paket- oder Desktop-Konfiguration verändert.**
