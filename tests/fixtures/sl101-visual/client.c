#define _GNU_SOURCE
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>
#include <wayland-client.h>
#include "xdg-shell-client-protocol.h"

/* A fixed, opaque, full-output wl_shm texture. No fonts, providers or clocks.
 * Single-pixel edges, row/column ramps and an asymmetric checker expose stride,
 * channel, interpolation and texture-coordinate errors at desktop dimensions. */
static struct wl_compositor *compositor;
static struct wl_shm *shm;
static struct xdg_wm_base *wm;
static struct wl_surface *surface;
static struct wl_buffer *buffer;
static int width = 1280, height = 720;

static void ping(void *data, struct xdg_wm_base *base, uint32_t serial) {
    (void)data;
    xdg_wm_base_pong(base, serial);
}
static const struct xdg_wm_base_listener wm_listener = { .ping = ping };

static void global(void *data, struct wl_registry *registry, uint32_t name,
                   const char *interface, uint32_t version) {
    (void)data;
    if (!strcmp(interface, "wl_compositor"))
        compositor = wl_registry_bind(registry, name, &wl_compositor_interface,
                                      version < 4 ? version : 4);
    else if (!strcmp(interface, "wl_shm"))
        shm = wl_registry_bind(registry, name, &wl_shm_interface, 1);
    else if (!strcmp(interface, "xdg_wm_base")) {
        wm = wl_registry_bind(registry, name, &xdg_wm_base_interface, 1);
        xdg_wm_base_add_listener(wm, &wm_listener, NULL);
    }
}
static void global_remove(void *data, struct wl_registry *registry, uint32_t name) {
    (void)data; (void)registry; (void)name;
}
static const struct wl_registry_listener registry_listener = {
    .global = global, .global_remove = global_remove
};

static void configured(void *data, struct xdg_surface *xdg, uint32_t serial) {
    (void)data;
    xdg_surface_ack_configure(xdg, serial);
    if (buffer) return;
    if (width < 1 || height < 1 || width > 2048 || height > 2048) exit(2);
    size_t size = (size_t)width * height * 4;
    int fd = memfd_create("sl101-visual-oracle", MFD_CLOEXEC);
    if (fd < 0 || ftruncate(fd, (off_t)size)) exit(2);
    uint32_t *pixels = mmap(NULL, size, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
    if (pixels == MAP_FAILED) exit(2);
    for (int y = 0; y < height; ++y) {
        for (int x = 0; x < width; ++x) {
            unsigned r = (unsigned)x % 251;
            unsigned g = (unsigned)y % 241;
            unsigned b = ((x / 17 + y / 13) & 1) ? 224 : 32;
            if (x % 127 == 0 || y % 61 == 0) r = g = b = 255;
            pixels[(size_t)y * width + x] = 0xff000000u | r << 16 | g << 8 | b;
        }
    }
    struct wl_shm_pool *pool = wl_shm_create_pool(shm, fd, (int)size);
    buffer = wl_shm_pool_create_buffer(pool, 0, width, height, width * 4,
                                      WL_SHM_FORMAT_ARGB8888);
    wl_shm_pool_destroy(pool);
    close(fd);
    munmap(pixels, size);
    wl_surface_attach(surface, buffer, 0, 0);
    wl_surface_damage(surface, 0, 0, width, height);
    wl_surface_commit(surface);
    fprintf(stderr, "FIXTURE_COMMITTED width=%d height=%d format=ARGB8888\n", width, height);
}
static const struct xdg_surface_listener surface_listener = { .configure = configured };
static void top_configure(void *data, struct xdg_toplevel *top, int32_t w,
                          int32_t h, struct wl_array *states) {
    (void)data; (void)top; (void)states;
    if (w > 0) width = w;
    if (h > 0) height = h;
}
static void top_close(void *data, struct xdg_toplevel *top) {
    (void)data; (void)top; exit(0);
}
static const struct xdg_toplevel_listener top_listener = {
    .configure = top_configure, .close = top_close
};

int main(void) {
    struct wl_display *display = wl_display_connect(NULL);
    if (!display) return 2;
    struct wl_registry *registry = wl_display_get_registry(display);
    wl_registry_add_listener(registry, &registry_listener, NULL);
    if (wl_display_roundtrip(display) < 0 || !compositor || !shm || !wm) return 2;
    surface = wl_compositor_create_surface(compositor);
    struct xdg_surface *xdg = xdg_wm_base_get_xdg_surface(wm, surface);
    xdg_surface_add_listener(xdg, &surface_listener, NULL);
    struct xdg_toplevel *top = xdg_surface_get_toplevel(xdg);
    xdg_toplevel_add_listener(top, &top_listener, NULL);
    xdg_toplevel_set_app_id(top, "sl101-visual-regression");
    xdg_toplevel_set_title(top, "SL101 visual regression oracle");
    xdg_toplevel_set_fullscreen(top, NULL);
    wl_surface_commit(surface);
    while (wl_display_dispatch(display) >= 0) {}
    return 2;
}
