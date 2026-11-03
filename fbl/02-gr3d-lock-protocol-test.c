/* Host-only regression driver. Build:
 * cc -std=c11 -Wall -Wextra -Werror -pthread -o /tmp/gr3d-fbl02-test
 *   fbl/02-gr3d-lock-protocol-test.c -ldl
 */
#define _GNU_SOURCE
#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <stdarg.h>
#include <stdio.h>
#include <sys/file.h>
#include <sys/ioctl.h>
#include <unistd.h>
static int locks, unlocks, submit_failure, wait_failure;
static int fake_ioctl(int fd, unsigned long req, ...) {
    (void)fd;
    va_list ap;
    va_start(ap, req);
    void *p = va_arg(ap, void *);
    va_end(ap);
    if (_IOC_NR(req) == 0x48) {
        if (submit_failure) { errno = EINVAL; return -1; }
        /* write fence in fixture without touching kernel */
        (void)p; /* fixture already supplies a kernel-like output fence */
        return 0;
    }
    if (_IOC_NR(req) == 0x44 && wait_failure) {
        errno = ETIMEDOUT;
        return -1;
    }
    return 0;
}
static void *fake_dlsym(void *handle, const char *sym) {
    (void)handle;
    (void)sym;
    return (void *)fake_ioctl;
}
#define dlsym fake_dlsym
#include "../docs/sl101-device-config/usr/local/src/gr3d_serialize_fbl02.c"
#undef dlsym
int flock(int fd, int operation) {
    (void)fd;
    if (operation == LOCK_EX) ++locks;
    if (operation == LOCK_UN) ++unlocks;
    return 0;
}
static unsigned long request(unsigned int nr) {
    return _IOC(_IOC_READ | _IOC_WRITE, 'd', nr, 64);
}
int main(void) {
    char path[] = "/tmp/sl101-gr3d-fbl02-XXXXXX";
    int fd = mkstemp(path);
    assert(fd >= 0);
    unlink(path);
    struct tegra_syncpt sp = { .id = 5, .incrs = 1 };
    struct tegra_submit s = { .num_syncpts = 1,
        .syncpts = (uintptr_t)&sp, .fence = 12 };
    struct tegra_wait w = { .id = 5, .thresh = 12, .timeout = 100 };
    /* Failure before accepted submit must unlock. */
    submit_failure = 1;
    assert(ioctl(fd, request(0x48), &s) == -1);
    assert(locks == 1 && unlocks == 1);
    submit_failure = 0;
    assert(ioctl(fd, request(0x48), &s) == 0);
    assert(locks == 2 && unlocks == 1);
    wait_failure = 1;
    assert(ioctl(fd, request(0x44), &w) == -1);
    assert(unlocks == 1);
    wait_failure = 0;
    w.thresh = 11; /* lower threshold cannot prove completion */
    assert(ioctl(fd, request(0x44), &w) == 0);
    assert(unlocks == 1);
    w.thresh = 12;
    assert(ioctl(fd, request(0x44), &w) == 0);
    assert(unlocks == 2);
    assert(ioctl(fd, request(0x44), &w) == 0);
    assert(unlocks == 2); /* unrelated wait never unlocks */
    /* Two accepted submits retain a single lock until both fences complete. */
    s.fence = 20;
    assert(ioctl(fd, request(0x48), &s) == 0);
    s.fence = 21;
    assert(ioctl(fd, request(0x48), &s) == 0);
    assert(locks == 3 && unlocks == 2);
    w.thresh = 20;
    assert(ioctl(fd, request(0x44), &w) == 0);
    assert(unlocks == 2);
    w.thresh = 21;
    assert(ioctl(fd, request(0x44), &w) == 0);
    assert(unlocks == 3);
    close(fd);
    puts("fbl02 mock submit/wait/error protocol OK");
    return 0;
}
