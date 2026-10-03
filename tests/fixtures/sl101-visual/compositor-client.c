#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>
#include <wayland-client.h>
#include "xdg-shell-client-protocol.h"

/*
 * SL101 compositor-semantics fixture.
 *
 * This deliberately uses ordinary wl_shm buffers and subsurfaces rather than
 * GL clients, so the compositor must import/sample exactly the kinds of buffers
 * used by panels, menus and toolkit clients.
 *
 * Final scene:
 *   - opaque ARGB8888 fullscreen parent,
 *   - padded-stride XRGB8888 child with asymmetric RGB ramps,
 *   - premultiplied ARGB8888 child above it with varying alpha,
 *   - a second synchronized commit changing bounded parent/XRGB rectangles.
 *
 * The independent Python oracle uses the same public geometry/constants but
 * recomputes the pixels and source-over math separately.
 */

enum {
    XRGB_X = 83,
    XRGB_Y = 71,
    XRGB_W = 173,
    XRGB_H = 97,
    XRGB_PAD = 52,
    ARGB_X = 170,
    ARGB_Y = 110,
    ARGB_W = 191,
    ARGB_H = 121,
    XRGB_PATCH_X = 15,
    XRGB_PATCH_Y = 12,
    XRGB_PATCH_W = 47,
    XRGB_PATCH_H = 31,
    PARENT_PATCH_W = 91,
    PARENT_PATCH_H = 53,
};

struct shm_buffer {
    struct wl_buffer *buffer;
    int width;
    int height;
    int stride;
};

static struct wl_display *display;
static struct wl_compositor *compositor;
static uint32_t compositor_version;
static struct wl_shm *shm;
static struct wl_subcompositor *subcompositor;
static struct xdg_wm_base *wm;
static struct wl_surface *parent_surface;
static struct wl_surface *xrgb_surface;
static struct wl_surface *argb_surface;
static struct wl_subsurface *xrgb_subsurface;
static struct wl_subsurface *argb_subsurface;
static int width = 1280;
static int height = 720;
static int configured_once;

static void fail(const char *message)
{
    fprintf(stderr, "FIXTURE_ERROR %s errno=%d (%s)\n",
            message, errno, strerror(errno));
    exit(2);
}

static uint8_t premul(uint8_t c, uint8_t a)
{
    return (uint8_t)(((unsigned)c * a + 127u) / 255u);
}

static uint32_t argb_word(uint8_t a, uint8_t r, uint8_t g, uint8_t b)
{
    return ((uint32_t)a << 24) | ((uint32_t)r << 16) |
           ((uint32_t)g << 8) | b;
}

static uint32_t parent_pixel(int x, int y, int phase)
{
    int patch_x = width - 140;
    int patch_y = height - 95;

    if (phase >= 2 && x >= patch_x && x < patch_x + PARENT_PATCH_W &&
        y >= patch_y && y < patch_y + PARENT_PATCH_H)
        return argb_word(255, 7, 211, 79);

    return argb_word(255, 17, 53, 91);
}

static uint32_t xrgb_pixel(int x, int y, int phase)
{
    if (phase >= 2 && x >= XRGB_PATCH_X &&
        x < XRGB_PATCH_X + XRGB_PATCH_W &&
        y >= XRGB_PATCH_Y && y < XRGB_PATCH_Y + XRGB_PATCH_H)
        return argb_word(0x2a, 201, 33, 149);

    uint8_t r = (uint8_t)((x * 3 + 11) & 0xff);
    uint8_t g = (uint8_t)((y * 5 + 37) & 0xff);
    uint8_t b = (uint8_t)((x + y * 2 + 73) & 0xff);

    /* XRGB's top byte is intentionally non-0xff: consumers must ignore it. */
    return argb_word(0x2a, r, g, b);
}

static uint32_t argb_pixel(int x, int y)
{
    static const uint8_t alpha[3] = {64, 128, 192};
    uint8_t a = alpha[((x / 16) + (y / 12)) % 3];
    uint8_t r = (uint8_t)(220 - ((x / 23) % 4) * 17);
    uint8_t g = (uint8_t)(41 + ((y / 19) % 5) * 19);
    uint8_t b = (uint8_t)(137 + ((x + y) % 5) * 13);

    return argb_word(a, premul(r, a), premul(g, a), premul(b, a));
}

static struct shm_buffer make_buffer(const char *name, int w, int h,
                                     int stride, uint32_t format,
                                     int phase)
{
    if (w <= 0 || h <= 0 || stride < w * 4 || (stride & 3))
        fail("invalid buffer geometry");

    size_t size = (size_t)stride * (size_t)h;
    if (size > INT32_MAX)
        fail("buffer too large");

    int fd = memfd_create(name, MFD_CLOEXEC);
    if (fd < 0 || ftruncate(fd, (off_t)size) != 0)
        fail("memfd/ftruncate");

    uint8_t *mapping = mmap(NULL, size, PROT_READ | PROT_WRITE,
                            MAP_SHARED, fd, 0);
    if (mapping == MAP_FAILED)
        fail("mmap");

    /* Padding is a loud canary. A correct import never samples it as pixels. */
    memset(mapping, 0xa5, size);

    for (int y = 0; y < h; ++y) {
        uint32_t *row = (uint32_t *)(mapping + (size_t)y * (size_t)stride);
        for (int x = 0; x < w; ++x) {
            if (format == WL_SHM_FORMAT_XRGB8888)
                row[x] = xrgb_pixel(x, y, phase);
            else if (w == width && h == height)
                row[x] = parent_pixel(x, y, phase);
            else
                row[x] = argb_pixel(x, y);
        }
    }

    struct wl_shm_pool *pool = wl_shm_create_pool(shm, fd, (int)size);
    if (!pool)
        fail("wl_shm_create_pool");

    struct shm_buffer out = {
        .buffer = wl_shm_pool_create_buffer(pool, 0, w, h, stride, format),
        .width = w,
        .height = h,
        .stride = stride,
    };
    wl_shm_pool_destroy(pool);
    munmap(mapping, size);
    close(fd);

    if (!out.buffer)
        fail("wl_shm_pool_create_buffer");
    return out;
}

static void damage_buffer(struct wl_surface *surface, int x, int y, int w, int h)
{
    if (compositor_version >= 4)
        wl_surface_damage_buffer(surface, x, y, w, h);
    else
        wl_surface_damage(surface, x, y, w, h);
}

static void ping(void *data, struct xdg_wm_base *base, uint32_t serial)
{
    (void)data;
    xdg_wm_base_pong(base, serial);
}

static const struct xdg_wm_base_listener wm_listener = {
    .ping = ping,
};

static void registry_global(void *data, struct wl_registry *registry,
                            uint32_t name, const char *interface,
                            uint32_t version)
{
    (void)data;
    if (strcmp(interface, "wl_compositor") == 0) {
        compositor_version = version < 4 ? version : 4;
        compositor = wl_registry_bind(registry, name,
                                      &wl_compositor_interface,
                                      compositor_version);
    } else if (strcmp(interface, "wl_shm") == 0) {
        shm = wl_registry_bind(registry, name, &wl_shm_interface, 1);
    } else if (strcmp(interface, "wl_subcompositor") == 0) {
        subcompositor = wl_registry_bind(registry, name,
                                         &wl_subcompositor_interface, 1);
    } else if (strcmp(interface, "xdg_wm_base") == 0) {
        wm = wl_registry_bind(registry, name, &xdg_wm_base_interface, 1);
        xdg_wm_base_add_listener(wm, &wm_listener, NULL);
    }
}

static void registry_remove(void *data, struct wl_registry *registry,
                            uint32_t name)
{
    (void)data;
    (void)registry;
    (void)name;
}

static const struct wl_registry_listener registry_listener = {
    .global = registry_global,
    .global_remove = registry_remove,
};

static void commit_scene_phase1(void)
{
    const int xrgb_stride = XRGB_W * 4 + XRGB_PAD;
    struct shm_buffer parent = make_buffer("sl101-parent-p1", width, height,
                                           width * 4,
                                           WL_SHM_FORMAT_ARGB8888, 1);
    struct shm_buffer xrgb = make_buffer("sl101-xrgb-p1", XRGB_W, XRGB_H,
                                         xrgb_stride,
                                         WL_SHM_FORMAT_XRGB8888, 1);
    struct shm_buffer argb = make_buffer("sl101-argb-p1", ARGB_W, ARGB_H,
                                         ARGB_W * 4,
                                         WL_SHM_FORMAT_ARGB8888, 1);

    xrgb_surface = wl_compositor_create_surface(compositor);
    argb_surface = wl_compositor_create_surface(compositor);
    if (!xrgb_surface || !argb_surface)
        fail("create child surface");

    xrgb_subsurface = wl_subcompositor_get_subsurface(
        subcompositor, xrgb_surface, parent_surface);
    argb_subsurface = wl_subcompositor_get_subsurface(
        subcompositor, argb_surface, parent_surface);
    if (!xrgb_subsurface || !argb_subsurface)
        fail("create subsurface");

    wl_subsurface_set_position(xrgb_subsurface, XRGB_X, XRGB_Y);
    wl_subsurface_set_position(argb_subsurface, ARGB_X, ARGB_Y);
    wl_subsurface_place_above(argb_subsurface, xrgb_surface);

    wl_surface_attach(parent_surface, parent.buffer, 0, 0);
    damage_buffer(parent_surface, 0, 0, width, height);

    wl_surface_attach(xrgb_surface, xrgb.buffer, 0, 0);
    damage_buffer(xrgb_surface, 0, 0, XRGB_W, XRGB_H);
    wl_surface_commit(xrgb_surface);

    wl_surface_attach(argb_surface, argb.buffer, 0, 0);
    damage_buffer(argb_surface, 0, 0, ARGB_W, ARGB_H);
    wl_surface_commit(argb_surface);

    wl_surface_commit(parent_surface);
    if (wl_display_roundtrip(display) < 0)
        fail("phase1 roundtrip");

    fprintf(stderr,
            "PHASE1_COMMITTED parent=%dx%d xrgb=%dx%d stride=%d "
            "argb=%dx%d compositor_v=%u\n",
            width, height, XRGB_W, XRGB_H, xrgb_stride,
            ARGB_W, ARGB_H, compositor_version);
}

static void commit_scene_phase2(void)
{
    const int xrgb_stride = XRGB_W * 4 + XRGB_PAD;
    const int parent_patch_x = width - 140;
    const int parent_patch_y = height - 95;

    struct shm_buffer parent = make_buffer("sl101-parent-p2", width, height,
                                           width * 4,
                                           WL_SHM_FORMAT_ARGB8888, 2);
    struct shm_buffer xrgb = make_buffer("sl101-xrgb-p2", XRGB_W, XRGB_H,
                                         xrgb_stride,
                                         WL_SHM_FORMAT_XRGB8888, 2);

    wl_surface_attach(parent_surface, parent.buffer, 0, 0);
    damage_buffer(parent_surface, parent_patch_x, parent_patch_y,
                  PARENT_PATCH_W, PARENT_PATCH_H);

    wl_surface_attach(xrgb_surface, xrgb.buffer, 0, 0);
    damage_buffer(xrgb_surface, XRGB_PATCH_X, XRGB_PATCH_Y,
                  XRGB_PATCH_W, XRGB_PATCH_H);
    wl_surface_commit(xrgb_surface);

    /* Child state is synchronized by default and becomes visible here. */
    wl_surface_commit(parent_surface);
    if (wl_display_roundtrip(display) < 0)
        fail("phase2 roundtrip");

    fprintf(stderr,
            "PHASE2_COMMITTED parent_damage=%d,%d+%dx%d "
            "xrgb_damage=%d,%d+%dx%d\n",
            parent_patch_x, parent_patch_y,
            PARENT_PATCH_W, PARENT_PATCH_H,
            XRGB_PATCH_X, XRGB_PATCH_Y,
            XRGB_PATCH_W, XRGB_PATCH_H);
    fprintf(stderr,
            "FIXTURE_COMMITTED width=%d height=%d "
            "formats=ARGB8888,XRGB8888 premultiplied=1 padded_stride=%d "
            "subsurfaces=2 commits=2\n",
            width, height, xrgb_stride);
}

static void xdg_configure(void *data, struct xdg_surface *xdg,
                          uint32_t serial)
{
    (void)data;
    xdg_surface_ack_configure(xdg, serial);
    if (configured_once)
        return;
    configured_once = 1;

    if (width < 400 || height < 300 || width > 2048 || height > 2048)
        fail("unexpected fullscreen dimensions");

    commit_scene_phase1();
    commit_scene_phase2();
}

static const struct xdg_surface_listener xdg_surface_listener = {
    .configure = xdg_configure,
};

static void toplevel_configure(void *data, struct xdg_toplevel *top,
                               int32_t w, int32_t h,
                               struct wl_array *states)
{
    (void)data;
    (void)top;
    (void)states;
    if (w > 0)
        width = w;
    if (h > 0)
        height = h;
}

static void toplevel_close(void *data, struct xdg_toplevel *top)
{
    (void)data;
    (void)top;
    exit(0);
}

static const struct xdg_toplevel_listener toplevel_listener = {
    .configure = toplevel_configure,
    .close = toplevel_close,
};

int main(void)
{
    display = wl_display_connect(NULL);
    if (!display)
        fail("wl_display_connect");

    struct wl_registry *registry = wl_display_get_registry(display);
    wl_registry_add_listener(registry, &registry_listener, NULL);
    if (wl_display_roundtrip(display) < 0 ||
        !compositor || !shm || !subcompositor || !wm)
        fail("required Wayland globals unavailable");

    parent_surface = wl_compositor_create_surface(compositor);
    if (!parent_surface)
        fail("create parent surface");

    struct xdg_surface *xdg =
        xdg_wm_base_get_xdg_surface(wm, parent_surface);
    xdg_surface_add_listener(xdg, &xdg_surface_listener, NULL);

    struct xdg_toplevel *top = xdg_surface_get_toplevel(xdg);
    xdg_toplevel_add_listener(top, &toplevel_listener, NULL);
    xdg_toplevel_set_app_id(top, "sl101-compositor-semantics");
    xdg_toplevel_set_title(top, "SL101 compositor semantics fixture");
    xdg_toplevel_set_fullscreen(top, NULL);

    wl_surface_commit(parent_surface);
    while (wl_display_dispatch(display) >= 0) {
        /* Keep all shm buffers/surfaces alive for stable repeated capture. */
    }
    return 2;
}
