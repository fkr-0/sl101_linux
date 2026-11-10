/* SPDX-License-Identifier: MIT */
#include "engine.h"

#include <glib.h>
#include <stdlib.h>

int
main(int argc, char **argv)
{
    NuraBrowserOptions options = { 0 };
    g_autoptr(GError) error = NULL;

    if (!nurabrowser_options_parse(&argc, &argv, &options, &error)) {
        g_printerr("nura-browser: %s\n", error ? error->message : "invalid options");
        nurabrowser_options_clear(&options);
        return EXIT_FAILURE;
    }

    int result = nurabrowser_engine_run(&options);
    nurabrowser_options_clear(&options);
    return result;
}
