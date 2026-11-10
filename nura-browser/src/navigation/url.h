/* SPDX-License-Identifier: MIT */
#ifndef NURABROWSER_NAV_URL_H
#define NURABROWSER_NAV_URL_H

#include <gio/gio.h>

/* Strict IPC input parser. The caller owns *normalized on success.
 * about:blank is intentionally not accepted from the remote control API. */
gboolean nurabrowser_nav_normalize_url(const char *input, char **normalized,
                                       GError **error);

#endif
