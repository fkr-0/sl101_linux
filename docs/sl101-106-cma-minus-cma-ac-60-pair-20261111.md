# SL101 .106: Minus-CMA B60 → CMA A60, AC-powered physical comparison

Date: 2026-11-11. **Both kernels booted, same physical .106, same 96-frame
H.264 MP4, 60 full VDE decode pipelines each, both on AC, zero failures.**

## Experiment and provenance

- Tablet: sl101-nura, 192.168.23.106, Alpine/musl, SD root /dev/mmcblk1p1.
- SD CID: 035344534c31323880ac79a543010300.
- eMMC CID: 7001004d4d43333247448d402a656e00.
- B/minus-CMA: 7.0.1-postmarketos-grate-dmavde1-minus-cma;
  boot ID 2459039c-a4d8-4cdb-9128-dd3b3061f771.
- A/CMA: 7.0.1-postmarketos-grate-dmavde1;
  NEW boot ID 48d4a72f-146f-43c7-a308-496466246821.
- Full kernel source differs only by CMA lowmem remap patch and
  CONFIG_LOCALVERSION. Same other three DMA/VDE fixes, same DTB.
- Exact same benchmark code SHA256:
  51a363ad6df985c20f90298e4fa7fe70d7de6f69f00805fb09e592c48eda9c4d.
- Exact same H.264 sample SHA256:
  e554039c0214ca939cea0ecf30081664ee0a89cc2820ca63944102214dbd407c.
- Same GStreamer pipeline: filesrc → qtdemux → h264parse →
  v4l2slh264dec → fakesink sync=false. Three prewarm runs, then 60
  independent timed launches and a private CMA tracefs instance.
- Both experiments: AC online=1 and battery status Charging throughout.
  B battery 93%, A battery 95%. Temperature both start/end 33→34 C.
  CPU start/end B 760→1000 MHz, A 912→1000 MHz; ondemand governor,
  CPU clock NOT pinned throughout.

## Measured B→A comparison

| Metric | B minus-CMA | A CMA | B minus A |
| --- | ---: | ---: | ---: |
| Pipeline wall p50 (ms) | 925.378 | **918.958** | +6.420 (0.694% of B) |
| Pipeline wall p95 (ms) | 958.663 | **947.718** | +10.945 |
| Pipeline wall p99 (ms) | 966.204 | **952.670** | +13.534 |
| Pipeline wall mean (ms) | 925.988 | **918.958** | +7.030 |
| Child user CPU p50 (ms) | 640.889 | 660.905 | -20.016 |
| Child system CPU p50 (ms) | 209.390 | 184.868 | +24.522 |
| Underlying core CMA allocation p50 (µs) | 1119.0 | 314.0 | +805.0 |
| Underlying core CMA allocation p95 (µs) | 3736.25 | 822.2 | +2914.05 |
| Underlying core CMA allocation p99 (µs) | 7406.92 | 1493.71 | +5913.21 |
| Completed decodes | **60/60** | **60/60** | — |
| Matched CMA allocations AND releases | **2040 each** | **2040 each** | — |
| Kernel CMA allocation failures | **0** | **0** | — |

The CMA core tracepoints bracket CMA page allocation only; they do
not measure the additional direct-map remap after CMA alloc_finish.
The much higher core-allocation times on B can therefore NOT be
causally attributed to the CMA patch. Page fragmentation, caching,
kernel boot history and scheduling also change between boots.

A naive independent-run bootstrap (5000 resamples, seed 20261111)
for the B-minus-A pipeline time difference gives:

- Median: +6.420 ms, approximate 95% interval **-0.003 to +13.986 ms**.
- Mean: +7.030 ms, approximate 95% interval **+0.918 to +13.245 ms**.

These rough intervals assume independent repetitions and do not control
time correlation, CPU frequency, boot order or fragmentation.
**Operational finding:** no material CMA pipeline regression detected.
CMA is ~0.7% faster by sample median, but the difference is small and
cannot be claimed as a reliably causal speedup or proven parity.

The formal A1→B→A2 gate in scripts/sl101-dmavde-cma-ab-compare.py
remains OPEN: this is a matched-power same-device **B60→A60** pair,
not a 3-boot A1→B→A2 series. The earlier A five-run smoke is not
an adequate full A1 baseline. An extra alternating reboot phase
would be necessary for formal drift-qualified certification; it was
not requested and was not performed.

## eMMC write, recovery and postflight

Before the restore the B60 output and full trace were transferred to
the host, hashes checked and no failures confirmed. Independent
rollback snapshots of BOTH kernel variants exist.

- Original/restored A full 8MiB LNX SHA256:
  6aa6ea687edf6a78103b2df12505263c9d6436cd193815c31092541d30faedf0.
- Prior B full 8MiB LNX SHA256:
  6d667e4b144a7c068cb3ffa8fd7f4a670bec75a4fd7ef1ec4214498c5c514457.
- B rollback on host:
  work/sl101-106-dmavde1-minus-cma-deploy-20261111/lnx-eight-mib-before-return-to-A-B.img.
- A rollback on host:
  work/sl101-106-dmavde1-minus-cma-deploy-20261111/lnx-eight-mib-pre-minus-cma-four-patch-A.img.
- B rollback on device:
  /var/lib/sl101-kernel-candidates/dmavde1-minus-cma/pre-return-A-B-full-slot.bin.
- Original A backup manifest/image on device:
  /var/lib/sl101-kernel-candidates/dmavde1-minus-cma/pre-minus-cma-fourpatch-LNX-backup/.

The guarded sl101-rawboot.py v2 restore wrote ONLY the active
8,388,608-byte eMMC LNX at offset 8,912,896 on /dev/mmcblk0,
then read back the entire slot and A zImage/DTB. SOS/BAK/GP1 SHA256
hashes verified unchanged. Normal guarded reboot was successful.

Postboot: verified boot ID 48d4a72f-146f-43c7-a308-496466246821,
587 matching A modules, VDE and DRM nodes, Sway PID 1446,
sl101-desktop, NuraLoumi/WayVNC services, VDE cached_capture=N,
kernel tracer nop with no remaining private trace instances, and
no new DMA/CMA/VDE faults in dmesg.

**Final running state:** both .106 and .100 run the four-patch CMA
kernel. .106 remains on AC=1 with a charging battery.

## Raw, byte-verified measurement evidence (private, not Git tracked)

Physical .106 output directories:

    /root/hwrun/qa-dmavde1/cma-ab-B60-ac-20261111/
    /root/hwrun/qa-dmavde1/cma-ab-A60-ac-20261111/

Host results, 60 per-pipeline timing tuples, and complete traces:

    work/sl101-106-dmavde1-minus-cma-deploy-20261111/cma-B60-ac-20261111-{result.json,pipelines.json,trace.txt}
    work/sl101-106-dmavde1-minus-cma-deploy-20261111/cma-A60-ac-20261111-{result.json,pipelines.json,trace.txt}

| File | SHA256 |
| --- | --- |
| B60 result | 09f144c87b7658488cf1a992840dfcb87c905897fbbd18767d862f2caf42d622 |
| B60 pipelines | 6e30bcc14512dd883977db9019de19bbcc93eda8c16f5de8a4b1b285a29840bb |
| B60 trace | ff903e2692020a02a31589ea3259b8c7fe83aee968c748b35834082b69f2fcb4 |
| A60 result | 303459605f2f0f5ece70f01f236f8c0e783116469a099ae6f023d0663c708692 |
| A60 pipelines | 22efbc1339a068f40dd6d7624f5bab44c83c42ecf41f21d05322b6e1dc8378af |
| A60 trace | 8cb3f1ee8cffbe226356eb2d8b3bf9d268b2a10253fd56dc1cde71f4451167d1 |
