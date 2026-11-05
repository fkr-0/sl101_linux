#ifndef SL101_WPE_READBACK_H
#define SL101_WPE_READBACK_H
#include <EGL/egl.h>
#include <EGL/eglext.h>
#include <stddef.h>
#include <stdint.h>

/* Acquisition statuses are NOT hardware-verification claims. */
enum sl101_rb_result {
    SL101_RB_OK_CONDITIONAL = 0,
    SL101_RB_UNSUPPORTED = 1,
    SL101_RB_NO_PRODUCER_FENCE = 2,
    SL101_RB_INVALID_LAYOUT = 3,
    SL101_RB_SYNC_FAILED = 4,
    SL101_RB_IO_ERROR = 5
};

struct sl101_rb_metadata {
    uint32_t width, height, fourcc;
    uint64_t modifier;
    int plane_count;
    int pitch, offset;
    uint64_t storage_bytes;
};

struct sl101_rb_snapshot {
    unsigned char *bytes;
    size_t len;
    struct sl101_rb_metadata metadata;
};

/*
 * Does not own image or EGL display; caller MUST retain both throughout.
 * producer_sync_file_fd must refer to actual producer writes of this frame,
 * supplied by trusted WPE producer code. -1 fails closed.
 * sync_file completion is checked with SYNC_IOC_FILE_INFO (not just poll).
 * DMA_BUF_IOCTL_SYNC brackets CPU read. Only exact verified linear single-plane.
 * Result is conditional until fence->frame provenance independently validated.
 */
/* Metadata-only: never maps and never claims coherent producer bytes. */
enum sl101_rb_result sl101_rb_probe(EGLDisplay display, EGLImageKHR image,
                                     uint32_t width, uint32_t height,
                                     struct sl101_rb_metadata *out);

enum sl101_rb_result sl101_rb_readback(EGLDisplay display,
                                      EGLImageKHR image,
                                      uint32_t width, uint32_t height,
                                      int producer_sync_file_fd,
                                      struct sl101_rb_snapshot *out);
void sl101_rb_free(struct sl101_rb_snapshot *out);
#endif
