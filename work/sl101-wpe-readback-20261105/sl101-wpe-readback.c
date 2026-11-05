#define _POSIX_C_SOURCE 200809L
#include "sl101-wpe-readback.h"
#include <dlfcn.h>
#include <errno.h>
#include <limits.h>
#include <poll.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>
#include <linux/dma-buf.h>
#include <linux/sync_file.h>

#ifndef DRM_FORMAT_XRGB8888
#define DRM_FORMAT_XRGB8888 0x34325258u
#define DRM_FORMAT_ARGB8888 0x34325241u
#endif

/* No optimistic assumption from header symbols: exact display extension token. */
static int has_extension(const char *list, const char *token)
{
    size_t len = strlen(token);
    const char *p = list;
    if (!p) return 0;
    while ((p = strstr(p, token))) {
        if ((p == list || p[-1] == ' ') &&
            (p[len] == 0 || p[len] == ' ')) return 1;
        p += len;
    }
    return 0;
}

/* Bounded explicit sync_file wait, not an implicit dma-buf completion guess. */
static int wait_producer_fence(int fd)
{
    struct pollfd p = {.fd=fd, .events=POLLIN};
    struct sync_file_info info = {0};
    int n;
    if (fd < 0) return 0;
    /* One bounded attempt: repeated EINTR must not extend the timeout. */
    n=poll(&p, 1, 150);
    if (n != 1 || !(p.revents & POLLIN) || (p.revents & (POLLERR|POLLNVAL)))
        return 0;
    if (ioctl(fd, SYNC_IOC_FILE_INFO, &info) != 0) return 0;
    /* Linux sync_file status: 1 = all fences signaled successfully. */
    return info.status == 1 && info.num_fences > 0;
}

static int sync_cpu(int fd, unsigned long phase)
{
    struct dma_buf_sync s = {.flags=DMA_BUF_SYNC_READ|phase};
    return ioctl(fd, DMA_BUF_IOCTL_SYNC, &s) == 0;
}

void sl101_rb_free(struct sl101_rb_snapshot *out)
{
    if (out) { free(out->bytes); memset(out, 0, sizeof(*out)); }
}

enum sl101_rb_result sl101_rb_probe(EGLDisplay display, EGLImageKHR image,
                                     uint32_t width, uint32_t height,
                                     struct sl101_rb_metadata *out)
{
    PFNEGLEXPORTDMABUFIMAGEQUERYMESAPROC query;
    PFNEGLEXPORTDMABUFIMAGEMESAPROC export_image;
    EGLuint64KHR modifier = UINT64_MAX;
    EGLint pitch = -1, offset = -1;
    int fourcc = 0, planes = 0, fd = -1;
    off_t allocation;
    uint64_t end;
    if (!out) return SL101_RB_INVALID_LAYOUT;
    memset(out, 0, sizeof(*out));
    if (display == EGL_NO_DISPLAY || image == EGL_NO_IMAGE_KHR ||
        !width || !height || width > 4096 || height > 4096)
        return SL101_RB_INVALID_LAYOUT;
    if (!has_extension(eglQueryString(display, EGL_EXTENSIONS),
                       "EGL_MESA_image_dma_buf_export"))
        return SL101_RB_UNSUPPORTED;
    query = (PFNEGLEXPORTDMABUFIMAGEQUERYMESAPROC)
        eglGetProcAddress("eglExportDMABUFImageQueryMESA");
    export_image = (PFNEGLEXPORTDMABUFIMAGEMESAPROC)
        eglGetProcAddress("eglExportDMABUFImageMESA");
    if (!query || !export_image ||
        query(display, image, &fourcc, &planes, &modifier) != EGL_TRUE)
        return SL101_RB_UNSUPPORTED;
    if (planes != 1 || modifier != 0 ||
        ((uint32_t)fourcc != DRM_FORMAT_XRGB8888 &&
         (uint32_t)fourcc != DRM_FORMAT_ARGB8888))
        return SL101_RB_UNSUPPORTED;
    if (export_image(display, image, &fd, &pitch, &offset) != EGL_TRUE) {
        if (fd >= 0) close(fd);
        return SL101_RB_UNSUPPORTED;
    }
    if (fd < 0) return SL101_RB_IO_ERROR;
    allocation = lseek(fd, 0, SEEK_END);
    close(fd);
    if (pitch < (int64_t)width*4 || pitch % 4 || offset < 0 ||
        allocation <= 0 || allocation > 64*1024*1024)
        return SL101_RB_INVALID_LAYOUT;
    end = (uint64_t)offset+(uint64_t)(height-1)*(uint64_t)pitch+
          (uint64_t)width*4;
    if (end > (uint64_t)allocation)
        return SL101_RB_INVALID_LAYOUT;
    *out = (struct sl101_rb_metadata) {
        .width=width,.height=height,.fourcc=(uint32_t)fourcc,
        .modifier=(uint64_t)modifier,.plane_count=planes,.pitch=pitch,
        .offset=offset,.storage_bytes=(uint64_t)allocation
    };
    return SL101_RB_OK_CONDITIONAL;
}

enum sl101_rb_result sl101_rb_readback(EGLDisplay display,
                                      EGLImageKHR image,
                                      uint32_t width, uint32_t height,
                                      int producer_sync_file_fd,
                                      struct sl101_rb_snapshot *out)
{
    PFNEGLEXPORTDMABUFIMAGEQUERYMESAPROC query;
    PFNEGLEXPORTDMABUFIMAGEMESAPROC export_image;
    EGLuint64KHR modifier = UINT64_MAX;
    EGLint pitch = 0, offset = -1;
    int fourcc = 0, planes = 0, fd = -1;
    uint64_t end;
    off_t allocation;
    void *mapped = MAP_FAILED;
    unsigned char *copy = NULL;
    enum sl101_rb_result result = SL101_RB_IO_ERROR;
    int started = 0;

    if (!out) return SL101_RB_INVALID_LAYOUT;
    memset(out, 0, sizeof(*out));
    if (producer_sync_file_fd < 0) return SL101_RB_NO_PRODUCER_FENCE;
    if (display == EGL_NO_DISPLAY || image == EGL_NO_IMAGE_KHR)
        return SL101_RB_UNSUPPORTED;
    if (!width || !height || width > 4096 || height > 4096)
        return SL101_RB_INVALID_LAYOUT;
    if (!has_extension(eglQueryString(display, EGL_EXTENSIONS),
                       "EGL_MESA_image_dma_buf_export"))
        return SL101_RB_UNSUPPORTED;
    query = (PFNEGLEXPORTDMABUFIMAGEQUERYMESAPROC)
        eglGetProcAddress("eglExportDMABUFImageQueryMESA");
    export_image = (PFNEGLEXPORTDMABUFIMAGEMESAPROC)
        eglGetProcAddress("eglExportDMABUFImageMESA");
    if (!query || !export_image) return SL101_RB_UNSUPPORTED;
    if (query(display, image, &fourcc, &planes, &modifier) != EGL_TRUE)
        return SL101_RB_UNSUPPORTED;
    if (planes != 1 || modifier != 0 ||
        ((uint32_t)fourcc != DRM_FORMAT_XRGB8888 &&
         (uint32_t)fourcc != DRM_FORMAT_ARGB8888))
        return SL101_RB_UNSUPPORTED;
    /* Export owns fd on success. Failure may leave a filled fd: close safely. */
    if (export_image(display,image,&fd,&pitch,&offset) != EGL_TRUE) {
        if (fd >= 0) close(fd);
        return SL101_RB_UNSUPPORTED;
    }
    if (fd < 0) return SL101_RB_IO_ERROR;
    if (pitch < 0 || (uint64_t)pitch < (uint64_t)width * 4 ||
        (pitch & 3) || offset < 0) {
        result = SL101_RB_INVALID_LAYOUT; goto cleanup;
    }
    end = (uint64_t)offset + (uint64_t)(height - 1) * (uint64_t)pitch +
          (uint64_t)width * 4;
    if (end > 64ull*1024*1024 || end > SIZE_MAX) {
        result = SL101_RB_INVALID_LAYOUT; goto cleanup;
    }
    allocation = lseek(fd, 0, SEEK_END);
    if (allocation <= 0 || (uint64_t)allocation < end ||
        (uint64_t)allocation > 64ull*1024*1024) {
        result = SL101_RB_INVALID_LAYOUT; goto cleanup;
    }
    /* Fence must be owned by trusted producer; the consumer cannot invent it. */
    if (!wait_producer_fence(producer_sync_file_fd)) {
        result = SL101_RB_SYNC_FAILED; goto cleanup;
    }
    if (!sync_cpu(fd, DMA_BUF_SYNC_START)) {
        result = SL101_RB_SYNC_FAILED; goto cleanup;
    }
    started=1;
    mapped=mmap(NULL, (size_t)allocation, PROT_READ, MAP_SHARED, fd, 0);
    if (mapped == MAP_FAILED) goto cleanup;
    if ((uint64_t)width*height*4 > SIZE_MAX) {
        result = SL101_RB_INVALID_LAYOUT; goto cleanup;
    }
    copy = malloc((size_t)width*height*4);
    if (!copy) goto cleanup;
    for (uint32_t y=0; y<height; ++y)
        memcpy(copy + (size_t)y*width*4,
               (unsigned char *)mapped + offset + (size_t)y*pitch,
               (size_t)width*4);
    result=SL101_RB_OK_CONDITIONAL;
cleanup:
    if (mapped != MAP_FAILED) munmap(mapped, (size_t)allocation);
    if (started && !sync_cpu(fd, DMA_BUF_SYNC_END)) result=SL101_RB_SYNC_FAILED;
    close(fd);
    if (result == SL101_RB_OK_CONDITIONAL) {
        out->bytes=copy;
        out->len=(size_t)width*height*4;
        out->metadata=(struct sl101_rb_metadata) {
            .width=width,.height=height,.fourcc=(uint32_t)fourcc,
            .modifier=(uint64_t)modifier,.plane_count=planes,
            .pitch=pitch,.offset=offset,.storage_bytes=(uint64_t)allocation
        };
    } else free(copy);
    return result;
}
