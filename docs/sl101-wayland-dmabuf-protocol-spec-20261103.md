# Wayland linux-dmabuf v1–v6: requirements for the SL101 WPE/Cog failure

**Research date:** 2026-11-03

**OCP task:** `SL101-LINUX-02-WAYLAND-DMABUF-PROTOCOL-SPEC-20261103-794388`

**Scope:** protocol XML and its accompanying upstream implementation guide; no device writes, Mesa changes, or browser launches.

## Bottom line

- An advertised `zwp_linux_dmabuf_v1` global does **not** establish that any particular DRM format/modifier pair is supported.
- There is **no explicit minimum count of advertised format/modifier pairs** in the inspected XML. This is not permission for a client to invent supported pairs.
- For negotiated versions 1–3, all formats/pairs actually supported by the compositor are sent using bind-time `format` (v1+) and/or `modifier` (v3+) events. A roundtrip completes their enumeration. If the compositor really supports formats and sends none, it has failed to advertise the formats it supports.
- Starting at negotiated version 4, `format` and `modifier` **must not be sent**. Format/modifier feedback instead follows the client's explicit `get_default_feedback` / `get_surface_feedback` request. An immediate post-bind absence of legacy events at v4 is therefore **required**, not a symptom of failure.
- A requested v4–v5 feedback object requires `main_device`, at least one preference tranche targeting `main_device`, the tranche events, and `done`. Zero tranches is not compliant. Within a tranche the XML requires one or more `tranche_formats` **events**, but its `indices` array has no stated nonzero minimum: sending an event with an empty array is not explicitly forbidden, while sending no `tranche_formats` event fails the stated structure.
- Starting at version 6, `main_device` disappears and at least one tranche with the `sampling` flag is explicitly required. Each v6 tranche must have at least one flag.
- Since version 4, `zwp_linux_buffer_params_v1.add` specifies `invalid_format` when a format/modifier pair was not advertised as supported. A Mesa fallback to arbitrary driver formats can trip a fatal error and is **not** a protocol-safe default.

## Primary upstream sources, pinned

The XML was inspected by fetching the official Wayland Protocols Git repository and running `git show <tag>:<path>`, rather than inferring requirements from Mesa behavior.

| wayland-protocols tag | Commit (dereferenced) | XML path | iface version | XML SHA-256 |
|---|---|---|---|---|
| 1.20 | `b0a25f26d3e8b5ad24773881a9a895dd9cc75466` | `unstable/linux-dmabuf/linux-dmabuf-unstable-v1.xml` | 3 | `be1cc5194d050d346fdbbaf9966fdce5779a28beaafca8f7b93861eec20d1aa7` |
| 1.24 | `bb7b3985eded147104331830a370195dffd1cdab` | `unstable/linux-dmabuf/linux-dmabuf-unstable-v1.xml` | 4 | `6f94b70ff66660ec620fdc6a441c46a3b2ea56b7aad39f8635a29779938e160e` |
| 1.33 | `54346071a5f211f2c482889f2c8ee3b5ecda63ab` | `stable/linux-dmabuf/linux-dmabuf-v1.xml` | 5 | `eccc7a040cf67bba17ef29fc906fecc2d55120701821613a821e272b87d74d96` |
| 1.49 | `ee78491a237eaff9389a0ccf8680521d074407d3` | `stable/linux-dmabuf/linux-dmabuf-v1.xml` | 6 | `2735bb4589cbb364dfcb6a821dd3abbf0c0257956b716b9691718ddfd453df4c` |

Browse pinned sources:
- [1.20 unstable XML](https://gitlab.freedesktop.org/wayland/wayland-protocols/-/blob/b0a25f26d3e8b5ad24773881a9a895dd9cc75466/unstable/linux-dmabuf/linux-dmabuf-unstable-v1.xml)
- [1.24 unstable XML](https://gitlab.freedesktop.org/wayland/wayland-protocols/-/blob/bb7b3985eded147104331830a370195dffd1cdab/unstable/linux-dmabuf/linux-dmabuf-unstable-v1.xml)
- [1.33 stable XML](https://gitlab.freedesktop.org/wayland/wayland-protocols/-/blob/54346071a5f211f2c482889f2c8ee3b5ecda63ab/stable/linux-dmabuf/linux-dmabuf-v1.xml)
- [1.49 stable XML](https://gitlab.freedesktop.org/wayland/wayland-protocols/-/blob/ee78491a237eaff9389a0ccf8680521d074407d3/stable/linux-dmabuf/linux-dmabuf-v1.xml)
- [1.49 guidance: feedback.rst](https://gitlab.freedesktop.org/wayland/wayland-protocols/-/blob/ee78491a237eaff9389a0ccf8680521d074407d3/stable/linux-dmabuf/feedback.rst)
- [1.33 announcement](https://mail-archive.com/wayland-devel@lists.freedesktop.org/msg42702.html)
- [Rendered stable XML](https://wayland.app/protocols/linux-dmabuf-v1)
- [2026 clarification of format_table event retransmission](https://cgit.freedesktop.org/wayland/wayland-protocols/commit/?id=afb614d5fcbd02d261a6ae91920aa91cf3915a8a)

**Naming trap:** The protocol only became stable with wayland-protocols **1.33** (2024-01-19) at **interface v5**; the v4 feedback scheme initially existed in the unstable XML. The stable file is `linux-dmabuf-v1.xml` and the wire interface is still `zwp_linux_dmabuf_v1`, not `wp_linux_dmabuf_v4`. `zwp_linux_dmabuf_feedback_v1` remains the stable wire interface name as well.

## Version and event contract

| Negotiated version | Format transport | When data is delivered | Mandatory framing |
|---|---|---|---|
| 1–2 | `zwp_linux_dmabuf_v1.format(DRM_FORMAT)` | Once on bind, complete after a roundtrip | Advertise **all supported** formats |
| 3 | `modifier(format, hi, lo)` (and historical `format`) | Once on bind, complete after a roundtrip | Advertise supported pairs; implicit modifier represented with `DRM_FORMAT_MOD_INVALID` |
| 4–5 | `format_table(fd,size)` + `tranche_formats(indices[])` on a feedback object | In response to `get_default_feedback` or `get_surface_feedback`, followed by `done` | `main_device`, >=1 tranche targeting it, event(s) within each tranche, `tranche_done`, `done` |
| 6 | Same indexed feedback; `sampling` tranche flag / optional `set_sampling_device` | After feedback request | >=1 sampling tranche; `main_device` is no longer sent |

Small exact excerpts from the pinned XML (each is a deliberately short quotation):

- v1–v3, `format`: “All the supported formats are advertised once when the client binds”.
- v4, legacy events: “must not be sent by compositors”.
- v4–v5, `main_device`: “must send at least one preference tranche”.
- v4, `params.add`: “format + modifier pair was not advertised as supported”.
- v6, feedback: “must always advertise at least one tranche with the sampling flag set”.

These are binding **MUST** requirements where the XML uses “must”; observations of what Mesa/wlroots usually do are not independent protocol requirements.

### How feedback is encoded

One complete v4–v5 feedback **update** normally has this structure (semantic schematic, not literal wire syntax):

    format_table(fd, size=16*N)       # table entries = uint32 fourcc + 4-byte pad + uint64 modifier
    main_device(dev_t)                # exactly one, v4-v5
    tranche_target_device(dev_t)      # exactly one per tranche
    tranche_flags(flags)              # exactly one per tranche
    tranche_formats(indices[])        # one or more events per tranche, each index uint16
    tranche_done()                    # ends one tranche
    ...                               # optional further tranches, descending preference
    done()                            # ends atomic feedback update

The `indices` reference format/modifier pairs from the **most recently received** `format_table`. Merely having pairs in the file does not make them supported for a surface: the advertised pairs are the ones referenced in the applicable tranche events. The table can have duplicate pairs, but duplicate pairs must not be advertised in a single tranche or across tranches sharing the same device and flags.

The feedback object describes **supported** combinations and **preferred** devices/paths. The client must select a format both the client can produce and a relevant compositor tranche offers. Tranches are ordered from highest to lowest preference. `tranche_done` ends one preference grouping; `done` closes the entire feedback update so clients can apply a consistent snapshot. Changes can trigger a full new update.

In tag 1.24, some prose incorrectly calls the events `tranche_modifier`; the actual event declaration is **`tranche_formats`**, and subsequent stable XML uses that name. This is a documentation typo, not an alternate wire event.

### Empty cases: strict distinctions

| Case | Assessment | Basis |
|---|---|---|
| v1–v3: no legacy format/modifier events but actual supported set is empty | No explicit minimum count | All **supported** formats must be emitted; empty set may be vacuous |
| v1–v3: no events despite actual supported formats | Violates the complete advertisement requirement | `format` and `modifier` event descriptions |
| v4+: no legacy format/modifier events on `zwp_linux_dmabuf_v1` bind | **Required** | Explicit v4 deprecation prohibition |
| v4+: client never requests feedback | No feedback object exists; no unsolicited feedback required | Feedback obtained by `get_*_feedback` requests |
| v4–v5: feedback object has zero tranches | **Noncompliant** | At least one tranche must target `main_device` |
| v4+: tranche has no `tranche_formats` events | **Noncompliant** with described event sequence | One or more `tranche_formats` events per tranche |
| v4+: `tranche_formats` event has an empty `indices` array | **Under-specified**, not expressly forbidden | XML gives no minimum array length, though it makes no useful format claims |
| v4+: table contains pairs but no tranche references them | No usable advertised combinations | `tranche_formats` determines actual advertised subset |
| v6: feedback object has no sampling tranche | **Noncompliant** | New explicit sampling-tranche requirement |

The “empty tranche” conclusion is deliberately narrow: no stated array minimum is not a blanket endorsement of unusable feedback. The accompanying `feedback.rst` describes each tranche as carrying a set of format/modifier pairs and recommends actual combinations usable for texturing/composition.

### Default vs per-surface feedback

`get_default_feedback` creates feedback **unbound to a surface**, intended for basic clients or clients without per-surface allocation logic. `get_surface_feedback(wl_surface)` creates an independent, surface-specific feedback object. Both can change over time and both use their own `done` boundaries; per-surface feedback can prioritize scanout or a different rendering device.

**No rule in the reviewed XML says that the set of pairs in surface feedback must equal or be a subset of the default feedback's set.** Hence a default feedback object with no *indexed* usable formats and a surface feedback object with usable formats is not expressly excluded on set-inclusion grounds. The default feedback still has its own v4/v5 mandatory **tranche framing**, and an empty default is poor interoperability for clients that only implement default feedback. The upstream guidance recommends giving basic clients a fallback rendering/device path; that guidance is “should”, not a new minimum-count “must”.

### Client and compositor responsibilities

**Client (normative):**
- For v1–v3, collect the advertised formats/modifier pairs after bind and a roundtrip; for v4+ request feedback and wait until its `done` before treating it as complete.
- Do not assume any format/modifier pair not advertised is legal to submit. Since v4, `params.add` documents an `invalid_format` protocol error for unadvertised pairs. The fact that the client's driver can allocate a format says nothing about compositor import support.
- When using implicit modifiers across different allocation/main devices in v4/v5, force linear layout (specific rule from `main_device` documentation).
- Treat failure to allocate a matching buffer as an inability to use that DMA-BUF path, rather than silently inventing server support.

**Compositor (normative):**
- For v1–v3, send all actual supported formats (and v3 modifier pairs) when bound.
- For v4+, do not send legacy `format`/`modifier`; answer requested feedback with the documented events/tranche structure and `done`. In v4–v5, include at least one tranche targeted at `main_device`. In v6, include a sampling tranche and don't send `main_device`.
- Do not advertise unsupported pairs as usable, mutate an already-sent format table, or duplicate pair advertisements in prohibited scopes.

**Not normative:** “every DMA-BUF compositor must expose BGRA8888”, “an EGL driver must have a config regardless of feedback”, or “a render node implies an implicit supported format”. No such guarantee appears in these protocol files.

### Fallback when no usable pairs exist

A client **may** switch to a distinct, mutually supported transport such as `wl_shm` if the compositor advertises it, using its own shared-memory buffers and software rendering path. This is not a linux-dmabuf obligation, and cannot be assumed to be automatic in Wayland EGL. Legacy `wl_drm` is also a separate protocol and its presence/support must be established independently. Failure of one transport does not make unadvertised DMA-BUF pairs valid.

When no common pair exists, a well-behaved EGL implementation can return no usable EGL configurations / fail the initialization or surface setup cleanly, rather than segfault; the exact EGL error and alternative software-renderer policy are EGL/Mesa concerns, **not** prescribed by the linux-dmabuf XML.

## Application to the current SL101 investigation

Existing project notes:
- `docs/sl101-grate-wayland-format-bypass-20261103.md`
- `docs/sl101-wpe-fdo-egl-investigation-20261103.md`
- `patches/mesa-25.0.7/0031-egl-wayland-accept-driver-formats-when-server-bitmap-empty.patch`

The preceding investigation reports that WPEBackend-fdo's **internal** Wayland connection has a reported render device but may omit indexed format support. Mesa's `formats_bitmap` then stays empty and no driver-backed EGL configs are selected. The standalone EGL probe against labwc is a **different compositor endpoint** and cannot validate the nested FDO endpoint.

**Important qualification of patch 0031:** The prior documentation describes bypassing the server bitmap because a render node was available as “safe”. This is too strong under the actual protocol: `main_device` identifies a preferred DRM device, not guaranteed support for any pair. The patch may diagnose a broken/under-advertising compositor but may violate the advertised-pair rule when the client submits DMA-BUFs. It should remain experimental until the nested server's requests, full feedback payload, and successful buffer imports are captured.

The absence of **legacy** v4 format/modifier events is specifically *not* evidence of a Cog defect. Distinguish:
1. Did the client bind `zwp_linux_dmabuf_v1` at version **4**, and request default/surface feedback?
2. Did that object receive `format_table`, `main_device`, a `tranche_target_device`, `tranche_flags`, `tranche_formats` (with nonempty `indices`), `tranche_done`, and `done`?
3. Is `format_table` present but `tranche_formats` empty? Were indices parsed correctly (uint16, native endian) and were the referenced fourcc/modifiers supported by Grate?
4. Does FDO actually accept `zwp_linux_buffer_params_v1.create` / `create_immed` for those pairs, or does the client use `wpe_dmabuf_pool` to transport buffers instead?
5. Can the same nested surface display a `wl_shm` buffer if `wl_shm` is advertised? Does the first frame receive a frame callback?

**Classification pending packet-level trace:**
- **Cog/FDO protocol defect** if it advertises v4 but omits required feedback framing after a client request (e.g. zero tranches, missing `done`), or claims pairs it cannot import.
- **Possible legal but unusable/under-specified negotiation** if it sends properly framed tranches with empty indices; not proof that a client should fabricate formats.
- **Mesa issue** if a compliant, nonempty format feedback is actually received but Mesa fails to parse it, wrongly discards matching formats, or crashes instead of reporting failure.
- **Expected no DMA-BUF support** if there are genuinely no common advertised pairs and no alternate path; EGL need not invent an interoperable transport.

## Suggested bounded follow-up

Capture a complete **nested FDO** `WAYLAND_DEBUG=client` handshake from registry bind through feedback `done`, including event array lengths and table fd contents (do not confuse with outer labwc). Pair it with EGL config enumeration and one actual buffer creation/import/attach. Qualify `0031` as diagnostic only; replace it with a protocol-respecting fix if the trace shows missing or misinterpreted advertisements. Preserve the existing no-unsafe-live-deployment gates.

No source modification or hardware action is needed to establish these protocol conclusions.
