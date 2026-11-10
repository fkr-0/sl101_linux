/* SPDX-License-Identifier: MIT
 * Internal seam for CPU verification; not part of public contract.h.
 */
#ifndef NURABROWSER_CONTROL_PRIVATE_H
#define NURABROWSER_CONTROL_PRIVATE_H
#include <gio/gio.h>
#include <sys/types.h>
gboolean nurabrowser_control_peer_uid_allowed(GCredentials *credentials,
                                               uid_t expected_uid);
#endif
