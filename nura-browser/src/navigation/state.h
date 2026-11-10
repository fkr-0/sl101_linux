/* SPDX-License-Identifier: MIT */
#ifndef NURABROWSER_NAV_STATE_H
#define NURABROWSER_NAV_STATE_H

#include <glib.h>

/* Owned directory descriptor, or -1 when persistence is unavailable.
 * No path is reopened after attach. Never follow symlink components. */
int nurabrowser_nav_state_open(const char *state_dir);
char *nurabrowser_nav_state_read(int directory_fd);
gboolean nurabrowser_nav_state_write(int directory_fd, const char *url);

#endif
