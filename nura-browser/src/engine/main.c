/* SPDX-License-Identifier: MIT */
#include "engine.h"
#include "../control/remote.h"

#include <glib.h>
#include <stdlib.h>
#include <string.h>

int
main(int argc, char **argv)
{
    /* The same shipping ELF also provides remote navigation. In this mode
     * there is no second browser process, WebView, or graphics context. */
    if (argc > 1 && strcmp(argv[1], "--remote") == 0)
        return nurabrowser_remote_main(argc - 2, argv + 2);

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
