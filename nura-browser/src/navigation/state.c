/* SPDX-License-Identifier: MIT */
#define _POSIX_C_SOURCE 200809L
#include "state.h"
#include "url.h"

#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>

#define STATE_FILE "navigation-state.v1"
#define STATE_HEADER "NURABROWSER_STATE_V1\n"
#define STATE_MAX_BYTES 8256

int
nurabrowser_nav_state_open(const char *path)
{
    int dir;
    char **components;
    struct stat st;

    if (!path || !g_path_is_absolute(path))
        return -1;
    /* openat() with O_NOFOLLOW on *every* path component prevents an attacker
     * replacing an ancestor with a symlink before the final directory opens. */
    dir = open("/", O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW);
    if (dir == -1)
        return -1;
    components = g_strsplit(path, "/", -1);
    for (gsize i = 0; components[i]; i++) {
        int next;
        if (!*components[i])
            continue;
        if (strcmp(components[i], ".") == 0 ||
            strcmp(components[i], "..") == 0) {
            close(dir);
            g_strfreev(components);
            return -1;
        }
        next = openat(dir, components[i],
                      O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW);
        close(dir);
        if (next < 0) {
            g_strfreev(components);
            return -1;
        }
        dir = next;
    }
    g_strfreev(components);
    if (fstat(dir, &st) || !S_ISDIR(st.st_mode) ||
        st.st_uid != geteuid() || (st.st_mode & 0777) != 0700) {
        close(dir);
        return -1;
    }
    return dir;
}

char *
nurabrowser_nav_state_read(int dir)
{
    char data[STATE_MAX_BYTES + 1];
    size_t used = 0;
    struct stat st;
    int fd;
    char *value = NULL, *normalized = NULL;
    gsize header_size = strlen(STATE_HEADER);

    if (dir < 0)
        return NULL;
    fd = openat(dir, STATE_FILE,
                O_RDONLY | O_CLOEXEC | O_NOFOLLOW | O_NONBLOCK);
    if (fd < 0)
        return NULL;
    if (fstat(fd, &st) || !S_ISREG(st.st_mode) ||
        st.st_uid != geteuid() || st.st_nlink != 1 ||
        (st.st_mode & 0077) || st.st_size < (off_t)(header_size + 2) ||
        st.st_size > STATE_MAX_BYTES)
        goto done;
    while (used < sizeof(data) - 1) {
        ssize_t n = read(fd, data + used, sizeof(data) - 1 - used);
        if (n < 0 && errno == EINTR)
            continue;
        if (n <= 0)
            break;
        used += (size_t)n;
    }
    if (used != (size_t)st.st_size ||
        memcmp(data, STATE_HEADER, header_size) != 0 ||
        data[used - 1] != '\n' ||
        memchr(data, '\0', used) != NULL)
        goto done;
    data[used - 1] = '\0';
    value = data + header_size;
    /* Restored state uses the *same* strict parser as remote IPC. */
    if (!nurabrowser_nav_normalize_url(value, &normalized, NULL))
        normalized = NULL;
done:
    close(fd);
    return normalized;
}

static gboolean
write_all(int fd, const char *text, gsize size)
{
    while (size) {
        ssize_t count = write(fd, text, size);
        if (count < 0 && errno == EINTR)
            continue;
        if (count <= 0)
            return FALSE;
        text += count;
        size -= (gsize)count;
    }
    return TRUE;
}

gboolean
nurabrowser_nav_state_write(int dir, const char *url)
{
    char *normalized = NULL, *payload = NULL;
    char tmp[72];
    int fd = -1;
    gboolean ok = FALSE;
    struct stat st;

    if (dir < 0 || !url ||
        !nurabrowser_nav_normalize_url(url, &normalized, NULL))
        return FALSE;
    if (fstat(dir, &st) || !S_ISDIR(st.st_mode) ||
        st.st_uid != geteuid() || (st.st_mode & 0777) != 0700)
        goto done;
    payload = g_strconcat(STATE_HEADER, normalized, "\n", NULL);
    if (strlen(payload) > STATE_MAX_BYTES)
        goto done;
    /* Directory is private 0700. O_EXCL/O_NOFOLLOW guards the temporary
     * inode; renameat replaces a hostile destination symlink, never follows it. */
    for (unsigned int attempt = 0; attempt < 16; attempt++) {
        g_snprintf(tmp, sizeof(tmp), ".navigation-state.%08x.tmp",
                   g_random_int());
        fd = openat(dir, tmp, O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC |
                    O_NOFOLLOW, 0600);
        if (fd >= 0)
            break;
        if (errno != EEXIST)
            goto done;
    }
    if (fd < 0)
        goto done;
    if (!write_all(fd, payload, strlen(payload)) ||
        fchmod(fd, 0600) || fsync(fd))
        goto cleanup_temp;
    if (close(fd))
        goto cleanup_closed;
    fd = -1;
    if (renameat(dir, tmp, dir, STATE_FILE))
        goto cleanup_closed;
    /* The rename has already committed if directory fsync fails. The caller
     * can retry; no half-written state is visible. */
    ok = fsync(dir) == 0;
    goto done;
cleanup_temp:
    close(fd);
    fd = -1;
cleanup_closed:
    unlinkat(dir, tmp, 0);
done:
    g_free(payload);
    g_free(normalized);
    return ok;
}
