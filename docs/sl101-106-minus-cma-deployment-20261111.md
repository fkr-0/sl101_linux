# SL101 .106 — minus-CMA benchmark: flashed, rebooted, verified

Date: 2026-11-11. Target: sl101-nura, 192.168.23.106.
**SUCCESS:** normal boot into 7.0.1-postmarketos-grate-dmavde1-minus-cma.

## Artifact identity

- Human label: 7.0.1-pmos-grate-dmavde1-minus-cma.
- Actual uname -r: 7.0.1-postmarketos-grate-dmavde1-minus-cma.
- Archive SHA-256: 774931dae8224afb78bd2f38272bcfbe6496f3b8db86b600fb26d81f208e4c3d.
- zImage SHA-256: 16772701116246c569ebf3ca956a3d13fa2e2e2c3d11f9d20ac48a870c9aa25e.
- DTB SHA-256: 01fbb5a935e429c42dc5e2793049bbfc91ff3a6f73c15f2063e1fb0af1a289b0.
- VDE module SHA-256: be44097b3fe220fa8083abb7cf7dbbcea396ce28d41e8c15199617b15aecc24b.

The host A/B verifier confirmed the three other patches, kernel Kconfig
(except LOCALVERSION), DTB and all 587 module paths match the four-patch
CMA candidate. Only arch/arm/mm/dma-mapping.c differs by the CMA change.

## Guarded flash and rollback

Before writing, authenticated preflight verified:
- hostname sl101-nura; previous kernel 7.0.1-postmarketos-grate-dmavde1;
- prior boot ID d31d3cd8-87b9-4dfb-a697-71e4b577f91a;
- eMMC CID 7001004d4d43333247448d402a656e00;
- microSD CID 035344534c31323880ac79a543010300;
- AC online, battery 99%, and exact four-patch LNX SHA before write.

Prior four-patch A full 8-MiB LNX SHA-256:
6aa6ea687edf6a78103b2df12505263c9d6436cd193815c31092541d30faedf0.

Private independent host backup:

    work/sl101-106-dmavde1-minus-cma-deploy-20261111/lnx-eight-mib-pre-minus-cma-four-patch-A.img

Separate guarded on-device rollback backup:

    /var/lib/sl101-kernel-candidates/dmavde1-minus-cma/pre-minus-cma-fourpatch-LNX-backup/slot-backup.bin
    /var/lib/sl101-kernel-candidates/dmavde1-minus-cma/pre-minus-cma-fourpatch-LNX-backup/slot-backup.json

The older unmodified stock LNX backup also remains retained from the
earlier four-patch deployment (docs/sl101-106-dmavde1-flash-20261111.md).

The on-device minus-CMA archive passed all 609 SHA256SUMS file checks,
and all 587 matching modules were installed in:

    /lib/modules/7.0.1-postmarketos-grate-dmavde1-minus-cma

Pinned module SHA and vermagic were verified before flash.
The sl101-rawboot.py v2 plan derived from the actual running four-patch
image changed ONLY the 8,388,608-byte LNX region at byte offset
8,912,896 on /dev/mmcblk0. The replacement zImage+DTB occupied
6,552,646 bytes including its Android header. Both were read back
successfully. The adjacent SOS, BAK and GP1 partition hashes were
identical before and after writing.

New full 8-MiB LNX SHA-256, verified again after reboot:
6d667e4b144a7c068cb3ffa8fd7f4a670bec75a4fd7ef1ec4214498c5c514457.

No writes to .100, BCT, EBT, Android user data or other eMMC regions.

## Successful reboot and service inspection

After the guarded reboot, authenticated SSH returned NEW boot ID
2459039c-a4d8-4cdb-9128-dd3b3061f771 and the expected
uname -r: 7.0.1-postmarketos-grate-dmavde1-minus-cma.

Verified: physical CIDs, microSD root /dev/mmcblk1p1, 587 matching
modules, /dev/dri/card0, /dev/dri/renderD128, /dev/video0,
Sway PID 1438, NuraLoumi panel, sl101-desktop and WayVNC services.
VDE cached_capture default=N. Initial dmesg and decoder smoke show
no new CMA allocation, DMA or VDE async-worker errors. The wm8903
audio warning is a known stock-baseline warning, not new to this RC.

## Full B-side 60-run battery diagnostic (2026-11-11)

**COMPLETE: 60/60 real hardware VDE H.264 decode pipelines** using the
pinned 96-frame clip and the real CMA allocation tracepoints. Device .106
stayed on the same minus-CMA kernel, boot ID
2459039c-a4d8-4cdb-9128-dd3b3061f771; VDE cached_capture=N, no
reboot, no KMS acquisition. The benchmark was run in explicitly
labelled battery mode because the charger was **absent** (AC=0,
battery ~88%, Discharging). That battery mode is deliberately
**not eligible for the AC-only A1–B–A2 performance comparator**.

| Metric | p50 | p95 | p99 |
| --- | ---: | ---: | ---: |
| H.264 pipeline wall time, ms | 1021.452 | 1106.163 | 1120.865 |
| CMA core allocation, microseconds | 1063.5 | 2947.3 | 9675.76 |
| Pipeline child CPU user, ms | 714.090 | 773.511 | 796.376 |
| Pipeline child CPU system, ms | 205.364 | 267.667 | 285.349 |

2040 matched CMA core allocations, zero tracing parse errors,
zero kernel CMA allocation failures. `cma_alloc_success` increased
by 2142 system-wide during the run. Original trace (871361 bytes),
all individual 60 timing tuples and verified JSON report are retained
outside Git:

    work/sl101-106-dmavde1-minus-cma-deploy-20261111/cma-B60-battery-result.json
    work/sl101-106-dmavde1-minus-cma-deploy-20261111/cma-B60-battery-pipelines.json
    work/sl101-106-dmavde1-minus-cma-deploy-20261111/cma-B60-battery-trace.txt

Result SHA-256: c958665afea2b3e3b7aa7b2f1bdd5e3f481b52c45940696fc939ec8789d6e11f.

The battery was 88% before and immediately after the 60 runs
(87% at later audit), **AC=0 both before and after this 60-run test**, CPU frequency **760 MHz at start, 1000 MHz at
finish** with ondemand governor, and temperature 27→29 °C. The first
15 decodes averaged 955.323 ms; the last 15 averaged 1031.829 ms.
**Time/frequency drift and unplugged power make this a diagnostic,
not a direct CMA overhead estimate.** Earlier 5-run CMA measurements
were on AC and cannot serve as A1/A2 with matched conditions.

After the run, Sway PID **1438** persisted; kernel tracer was **nop**,
no private tracing instances remained, cached_capture=N, VDE/DRM
nodes remained present, and no new DMA/CMA/VDE faults were detected.

The full three-boot A1–B–A2 performance gate remains **OPEN**, not
PASS or REGRESSION.

## Earlier five-run B smoke and deployment



The **first** B-side 96-frame H.264 decoder test was repeated five
 times **ON AC POWER (AC=1 at start and finish; battery 99%)**, not
 on battery. This has been independently confirmed from the original
 measurement JSON. **170 matched CMA allocation events**, zero failures.

- VDE pipeline p50 902.762 ms; p95 912.595 ms; p99 913.789 ms.
- Underlying CMA page allocation p50 289.5 microseconds; p95 734.85.
- Same clip as the earlier A-side **also AC-powered** five-run smoke
  (A p50 879.381 ms). Minus-CMA B p50 was 2.7% higher than CMA A
  for just five runs; not a robust result.
- Private JSON: work/sl101-106-dmavde1-minus-cma-deploy-20261111/cma-B-five-run-smoke.json.
- Source: scripts/sl101-dmavde-cma-ab-bench.py.

Five repetitions do NOT establish a CMA performance advantage or penalty.
The independent 60+ A1–B–A2 thermal-controlled performance comparison
remains OPEN. Similarly, the full 216-case GPU and 120-case bilinear
matrices and 96-frame FFmpeg-reference comparison were performed on A;
they have NOT been independently repeated on B.

Recovery: physically supervised APX/RCM/RAM U-Boot plus original stock
SD extlinux rescue, followed by restoring only the backed-up
8,388,608-byte A LNX at offset 8,912,896 with sl101-rawboot.py restore.
Check physical CIDs, original backup SHA and current B slot SHA before
any write. Do not use .100 backups or a 14-MiB composite.
