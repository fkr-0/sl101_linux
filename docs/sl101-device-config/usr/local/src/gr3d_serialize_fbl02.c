/* Lane fbl02: experimental Alpine/musl GR3D ioctl interposer.
 * DO NOT DEPLOY before confirming labwc calls matching fence waits.
 * Build in Alpine armv7: cc -O2 -fPIC -shared -o gr3d_serialize.so
 *   gr3d_serialize_fbl02.c -ldl -pthread
 */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <errno.h>
#include <pthread.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdlib.h>
#include <sys/file.h>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <unistd.h>

/* Legacy DRM/Tegra 1.1 UAPI, mirrored from tegra_drm.h. */
struct tegra_syncpt { uint32_t id, incrs; };
struct tegra_wait { uint32_t id, thresh, timeout, value; };
struct tegra_submit {
    uint64_t context;
    uint32_t num_syncpts, num_cmdbufs, num_relocs, num_waitchks;
    uint32_t waitchk_mask, timeout;
    uint64_t syncpts, cmdbufs, relocs, waitchks;
    uint32_t fence, reserved[5];
};
struct pending {
    dev_t dev;
    ino_t ino;
    int lock_fd; /* owning open file description; wait may use another fd */
    uint32_t id, fence;
    struct pending *next;
};
static struct pending *pending_jobs;
static pthread_mutex_t mutex = PTHREAD_MUTEX_INITIALIZER;
static pthread_once_t once = PTHREAD_ONCE_INIT;
static int (*real_ioctl)(int, unsigned long, ...);
static void init_ioctl(void) {
    *(void **)(&real_ioctl) = dlsym(RTLD_NEXT, "ioctl");
}
static int match(struct pending *p, const struct stat *st) {
    return p->dev == st->st_dev && p->ino == st->st_ino;
}
static int tegra(unsigned long req, unsigned int nr) {
    return _IOC_TYPE(req) == 'd' && _IOC_NR(req) == nr;
}

int ioctl(int fd, unsigned long request, ...) {
    /* No-argument ioctl callers must not be read with va_arg(). */
    if (_IOC_DIR(request) == _IOC_NONE && _IOC_SIZE(request) == 0) {
        pthread_once(&once, init_ioctl);
        if (!real_ioctl) { errno = ENOSYS; return -1; }
        return real_ioctl(fd, request);
    }
    va_list ap;
    void *arg;
    va_start(ap, request);
    arg = va_arg(ap, void *);
    va_end(ap);
    pthread_once(&once, init_ioctl);
    if (!real_ioctl) { errno = ENOSYS; return -1; }
    if (!arg || (!tegra(request, 0x48) && !tegra(request, 0x44)))
        return real_ioctl(fd, request, arg);

    struct stat st;
    if (fstat(fd, &st) != 0)
        return real_ioctl(fd, request, arg);

    if (tegra(request, 0x48)) {
        struct tegra_submit *submit = arg;
        /* Fail closed on unsupported syncpoint shape; never release a
         * possibly asynchronous submit on unsupported metadata. */
        if (submit->num_syncpts != 1 || !submit->syncpts) {
            errno = ENOTSUP;
            return -1;
        }
        const struct tegra_syncpt *sp = (void *)(uintptr_t)submit->syncpts;
        pthread_mutex_lock(&mutex);
        int held = 0;
        for (struct pending *p = pending_jobs; p; p = p->next)
            if (match(p, &st)) { held = 1; break; }
        if (!held && flock(fd, LOCK_EX) != 0) {
            int err = errno;
            pthread_mutex_unlock(&mutex);
            errno = err;
            return -1;
        }
        /* Reserve the metadata *before* submission, so allocation failure
         * cannot strand an accepted job with untracked completion. */
        struct pending *new_job = malloc(sizeof(*new_job));
        if (!new_job) {
            if (!held) flock(fd, LOCK_UN);
            pthread_mutex_unlock(&mutex);
            errno = ENOMEM;
            return -1;
        }
        int rc = real_ioctl(fd, request, arg);
        int err = errno;
        if (rc == 0) {
            *new_job = (struct pending){ .dev = st.st_dev,
                .ino = st.st_ino, .lock_fd = fd, .id = sp->id,
                .fence = submit->fence, .next = pending_jobs };
            pending_jobs = new_job;
        } else {
            free(new_job);
            if (!held) flock(fd, LOCK_UN);
        }
        pthread_mutex_unlock(&mutex);
        errno = err;
        return rc;
    }

    /* SYNCPT_WAIT: keep the flock held across the kernel's blocking wait;
     * release only when *every* outstanding fence for this DRM inode has
     * been observed at a matching or later threshold. */
    int rc = real_ioctl(fd, request, arg);
    int err = errno;
    if (rc == 0) {
        const struct tegra_wait *wait = arg;
        pthread_mutex_lock(&mutex);
        int removed = 0;
        int unlock_fd = -1;
        struct pending **pp = &pending_jobs;
        while (*pp) {
            struct pending *p = *pp;
            if (match(p, &st) && p->id == wait->id &&
                (int32_t)(wait->thresh - p->fence) >= 0) {
                *pp = p->next;
                if (unlock_fd < 0) unlock_fd = p->lock_fd;
                free(p);
                removed = 1;
            } else {
                pp = &p->next;
            }
        }
        int remain = 0;
        for (struct pending *p = pending_jobs; p; p = p->next)
            if (match(p, &st)) { remain = 1; break; }
        if (removed && !remain)
            flock(unlock_fd, LOCK_UN);
        pthread_mutex_unlock(&mutex);
    }
    /* EINTR/ETIMEDOUT and unmatched waits retain the lock; no speculative
     * unlock is allowed. If the renderer never waits, this shim deadlocks
     * rather than pretending the GPU finished. */
    errno = err;
    return rc;
}
