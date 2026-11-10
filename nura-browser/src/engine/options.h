/* SPDX-License-Identifier: MIT */
#ifndef NURABROWSER_ENGINE_OPTIONS_H
#define NURABROWSER_ENGINE_OPTIONS_H

#include <glib.h>

typedef struct {
    char *url;                  /* Owned, validated initial URI. */
    char *platform;             /* One of headless, wayland, drm. */
    gboolean no_control;
    guint exit_after_ms;        /* Zero disables the CI exit hook. */
} NuraBrowserOptions;

gboolean nurabrowser_options_parse(int *argc, char ***argv,
                                  NuraBrowserOptions *options, GError **error);
void nurabrowser_options_clear(NuraBrowserOptions *options);

#endif
