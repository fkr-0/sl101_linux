# SL101 Wayland producer-frame gate (2026-11-05)

## Scope
Host-only and fail-closed. `scripts/sl101-wayland-producer-frame-gate.py` compares immutable, **externally supplied** XRGB8888/ARGB8888 linear producer bytes to a packed RGB24 screenshot. The manifest's origin, sync, modifier, frame ID and timestamps are **untrusted assertions**. Even a passing comparison returns `CONDITIONAL_UNVERIFIED_ORIGIN`, `actual_producer_pixels_verified=false`, and `hardware_attribution=INCONCLUSIVE`. It is not a GPU mapper, no ELF has been compiled, and no Cog callback has been instrumented.

It checks single plane, explicit linear modifier 0, verified-layout assertion, byte bounds using offset+(height-1)*pitch+width*4, valid sequence ordering, snapshot-before-attach assertion, and visually verified unique marker. No unproven 64-byte pitch rule: non-64-aligned pitches are allowed if the full allocation covers them. Little-endian DRM XRGB/ARGB stores B,G,R,[X/A]. Screen is 1280x800 RGB24, with the 1024x720 producer at (128,68), scale=1, transform=0 and viewport 1024x720. It compares exact producer-to-screen pixels, magenta occurrences and five error contours. Quadrant expected-color comparisons skip the border and marker zone.

### Command
    python3 -m unittest tests.test_sl101_wayland_producer_frame_gate -v
    python3 scripts/sl101-wayland-producer-frame-gate.py --metadata frame.json --producer-raw producer.bin --screen-rgb screen.rgb

## Missing live prerequisites / safety gates
- Exact on-device EGL client/display extension inventory, WPE FDO ABI and library versions, proven EGL image export API plus modifier/plane/fd query support.
- Source-grounded synchronization (EGL fence, GL finish or DRM syncpt) and modifier-aware private CPU staging while buffer is owned **before attach/release**; do not mmap tiled BOs or confuse labwc glReadPixels with producer readback.
- Isolated Cog instrumentation assigning stable per-wl_buffer identity and logging export, snapshot, attach, commit, release and WPE release dispatch. No copied buffer after reentrant release.
- Frame marker visible in both producer and compositor capture, coherent timestamps, full provenance hashes, matching 1024x720 ROI and transform.
- Independent different-author safety/lifetime review; private-prefix Docker ARMHF crossbuild and DT_NEEDED pinning; independent watchdog 15s first / <=30s second; single graphics ownership and rollback. The independently reproduced Cog teardown UAF remains HOLD.
- No old global pgrep/pkill script, Pixman config mutation, device reboot, GR3D reset, or live browser launch prior to review.

## Current device inventory / explicit block
Read-only SSH to `user@192.168.23.106` succeeded; `hostname=sl101-nura`, `uname -r=7.0.1-postmarketos-grate`. The *first* query read `/sys/block/mmcblk0/device/cid=7001004d4d43333247448d402a656e00`; this is NOT the previously qualified SD CID `035344534c31323880ac79a543010300`. Device role/SD identity remains unresolved; this first query accidentally selected a different MMC block name. Its EGL globbing also failed under remote zsh, returning **no reliable EGL inventory**. A second, read-only full MMC/EGL inventory command was blocked by the safety gate. Do not retry it via another route or assume export support. No ARMHF build, private-prefix deploy, Cog browser, or new screenshot was performed.

Host validation: `python3 -m unittest tests.test_sl101_wayland_producer_frame_gate -v` **18/18 PASS**; `make test` **333 tests OK, 1 skipped**; `make check` **PASS**. Test suite emits an expected negative patch-apply diagnostic and a mocked Grate/Pixman recovery message; exit status 0 is the only supported test-result claim. These are host tests, not tablet graphics tests.

Existing 71,067/737,280 screen errors, including 22,232 magenta pixels, establish **post-labwc** corruption only. Producer bytes, verified modifier, completed fence, same-frame screenshot, and producer correctness: **NOT YET PROVEN**.
