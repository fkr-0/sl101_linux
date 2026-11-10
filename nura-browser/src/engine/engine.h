/* SPDX-License-Identifier: MIT */
#ifndef NURABROWSER_ENGINE_H
#define NURABROWSER_ENGINE_H

#include "options.h"

/* Blocking main-context entry. All navigation/control callbacks must run
 * on the same GLib default main context as WebKitWebView. */
int nurabrowser_engine_run(const NuraBrowserOptions *options);

#endif
