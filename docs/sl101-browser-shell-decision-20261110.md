# SL101: Cog today, own small WPEPlatform shell next

Date: 2026-11-10.

**Decision:** Do not maintain a deep Cog fork. Keep Cog 0.18.x as a
known diagnostic/reference launcher (including separate KMS-Cog and
Sway-Cog test lanes), and create a small shell against upstream
WPEPlatform for future browser UX after GPU compatibility is proven.

## Upstream facts

Cog provides libcogcore, a launcher and optional platform modules for
Wayland and DRM. It is not a general full browser:
https://github.com/Igalia/cog/blob/master/docs/overview.md

WPE WebKit 2.54, released in September 2026, stabilized WPEPlatform and
deprecated the old libwpe backend API. Cog has no further stable releases
beyond 0.18.x. New projects should use WPEPlatform directly:
https://wpewebkit.org/blog/2026-09-16-wpewebkit-2.54.html
https://wpewebkit.org/blog/2026-10-06-wpe-platform.html

WPEPlatform provides a WPEDisplay / WPEToplevel / WPEView abstraction
and built-in Wayland, DRM and headless implementations:
https://wpewebkit.org/about/architecture.html

## Tegra2-specific blocker

The WPE 2.54 compositor uses **Skia** instead of TextureMapper; Cairo
rendering is removed. Our Tegra2/Grate GLES2 target has not passed
new-Skia compatibility/performance qualification. WebKit 2.54 still
allows a TextureMapper comparison by starting the same binary with
WEBKIT_USE_SKIA_FOR_COMPOSITION=0 (this is not a permanent compatibility
contract). Compare this explicitly against Skia on EGL/Grate GLES2.
Do not upgrade the GPU browser simply because a modern shell can initialize. The
WPEPlatform change also does not yet replace the old fdo video-plane
extension; VDE/KMS overlays need separate integration and proof.

A browser shell alone cannot fix BO DMA coherency, EGL-config
advertisement, dmabuf feedback or a WebProcess crash.

## Proposed architecture

    ,browse / NuraLoumi launcher
             |
      small native shell (C/GObject)
      address input / back / forward / history
      keyboard + touch + pointer routing
      multi-view/tab lifecycle
      permission policy + WebProcess crash recovery
      truthful renderer / backend diagnostics
             |
       selectable backend
         /          \
    pinned Cog     modern WPEPlatform
    legacy probe   headless -> Wayland -> DRM
         \          /
       Grate Mesa + kernel/VDE QA

Implement functionality as shell/UI logic, not WebKit internals. Keep
NuraLoumi responsible for native chrome, keyboard and launcher UX.

1. Preserve pinned Cog as hardware regression reference; only small,
   targeted fixes to its input/Wayland/DRM adapter.
2. Build a minimal WPEPlatform headless prototype, then Sway Wayland,
   then isolated DRM/KMS. Check GPU pixels, allocations, crashes,
   memory, and keyboard/touch against pinned Cog.
3. Decide renderer compatibility before adding larger browser features.
4. Only promote a new browser if it is at least functionally stable
   and measurably usable on Tegra20. Otherwise continue Cog/legacy
   WebKit while developing the new shell independently.
