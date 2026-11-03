/* fbl02: native adversarial lock-lifetime probes, NOT GPU proof.
 * cc -std=c11 -Wall -Wextra -Werror -pthread -o /tmp/fbl02-test \
 *   fbl/02-gr3d-lock-protocol-test.c
 */
#define _GNU_SOURCE
#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/file.h>
#include <sys/wait.h>
#include <unistd.h>
#include "../docs/sl101-device-config/usr/local/src/gr3d_serialize_fbl02.c"

struct probe { const char *path; int result; };
static void *try_other_description(void *arg)
{
    struct probe *p = arg;
    int fd = open(p->path, O_RDWR);
    assert(fd >= 0);
    errno = 0;
    p->result = flock(fd, LOCK_EX | LOCK_NB);
    if (p->result < 0) assert(errno == EWOULDBLOCK || errno == EAGAIN);
    if (p->result == 0) assert(flock(fd, LOCK_UN) == 0);
    assert(close(fd) == 0);
    return NULL;
}
static void probe_thread(const char *path, int expected)
{
    pthread_t thread;
    struct probe p = { path, -9 };
    assert(pthread_create(&thread, NULL, try_other_description, &p) == 0);
    assert(pthread_join(thread, NULL) == 0);
    assert(p.result == expected);
}
static void probe_process(const char *path, int expected)
{
    pid_t pid = fork();
    assert(pid >= 0);
    if (pid == 0) {
        int fd = open(path, O_RDWR);
        if (fd < 0) _exit(100);
        int result = flock(fd, LOCK_EX | LOCK_NB);
        if (result == 0) (void)flock(fd, LOCK_UN);
        (void)close(fd);
        _exit((result == expected) ? 0 : 101);
    }
    int status = 0;
    assert(waitpid(pid, &status, 0) == pid);
    assert(WIFEXITED(status) && WEXITSTATUS(status) == 0);
}
/* Kernel wait fixture: an interrupted/failed call is NOT completion. */
static int wait_mock(int interrupted, int failed)
{
    if (interrupted) { errno = EINTR; return -1; }
    if (failed) { errno = ETIMEDOUT; return -1; }
    return 0;
}
int main(void)
{
    assert(sl101_gr3d_fbl02_disabled() == -ENOTSUP);
    char path[] = "/tmp/sl101-fbl02-lock-XXXXXX";
    int fd = mkstemp(path);
    assert(fd >= 0);

    /* Thread and process use distinct open descriptions and cannot enter. */
    assert(flock(fd, LOCK_EX) == 0);
    probe_thread(path, -1);
    probe_process(path, -1);

    /* Dup retains the open description; closing the ORIGINAL number should
     * not release the lock while the duplicate exists. */
    int held = dup(fd);
    assert(held >= 0);
    assert(close(fd) == 0);
    int reused = open(path, O_RDWR);
    assert(reused >= 0);
    probe_thread(path, -1);
    probe_process(path, -1);

    /* Failed and interrupted waits MUST NOT be interpreted as completion.
     * The test deliberately keeps the OS lock while these outcomes occur. */
    assert(wait_mock(1, 0) == -1 && errno == EINTR);
    probe_process(path, -1);
    assert(wait_mock(0, 1) == -1 && errno == ETIMEDOUT);
    probe_thread(path, -1);

    /* Even while a second descriptor reuses a number from a closed fd,
     * releasing THAT descriptor does not release the held description. */
    assert(close(reused) == 0);
    probe_process(path, -1);
    assert(flock(held, LOCK_UN) == 0);
    probe_thread(path, 0);
    probe_process(path, 0);
    assert(close(held) == 0);

    /* No unsafe interposer is compiled: arbitrary DRM-looking requests and
     * invalid userspace syncpt pointers are never examined by this unit. */
    assert(unlink(path) == 0);
    puts("fbl02 disabled; native pthread/fork/dup/close/reuse/EINTR/timeout probes OK");
    return 0;
}
