/* SPDX-License-Identifier: MIT */
#include "options.h"

#include <gio/gio.h>
#include <string.h>

/* Do not accept file:, data:, javascript:, credentials, or relative URLs.
 * about:blank is an intentionally inert initial page for offline testing. */
static gboolean
valid_initial_url(const char *value)
{
    if (g_strcmp0(value, "about:blank") == 0)
        return TRUE;

    if (!value || !*value || strpbrk(value, "\r\n\t"))
        return FALSE;

    g_autoptr(GError) error = NULL;
    g_autoptr(GUri) uri = g_uri_parse(value, G_URI_FLAGS_NONE, &error);
    if (!uri || !g_uri_get_scheme(uri) || !g_uri_get_host(uri))
        return FALSE;

    const char *scheme = g_uri_get_scheme(uri);
    if (g_ascii_strcasecmp(scheme, "https") &&
        g_ascii_strcasecmp(scheme, "http"))
        return FALSE;

    return *g_uri_get_host(uri) != '\0' &&
           g_uri_get_userinfo(uri) == NULL;
}

static gboolean
valid_platform(const char *name)
{
    return g_strcmp0(name, "headless") == 0 ||
           g_strcmp0(name, "wayland") == 0 ||
           g_strcmp0(name, "drm") == 0;
}

void
nurabrowser_options_clear(NuraBrowserOptions *options)
{
    if (!options)
        return;
    g_clear_pointer(&options->url, g_free);
    g_clear_pointer(&options->platform, g_free);
    options->no_control = FALSE;
    options->exit_after_ms = 0;
}

gboolean
nurabrowser_options_parse(int *argc, char ***argv,
                          NuraBrowserOptions *options, GError **error)
{
    g_return_val_if_fail(argc && argv && options, FALSE);

    gchar *url = NULL;
    gchar *platform = NULL;
    gboolean no_control = FALSE;
    gint exit_after_ms = 0;
    gboolean success = FALSE;
    GOptionEntry entries[] = {
        { "url", 0, 0, G_OPTION_ARG_STRING, &url,
          "Initial absolute HTTP(S) URL (or about:blank)", "URL" },
        { "platform", 0, 0, G_OPTION_ARG_STRING, &platform,
          "WPEPlatform backend: headless, wayland, drm", "BACKEND" },
        { "no-control", 0, 0, G_OPTION_ARG_NONE, &no_control,
          "Disable the private NuraLoumi control socket", NULL },
        { "exit-after-ms", 0, 0, G_OPTION_ARG_INT, &exit_after_ms,
          "Quit after N milliseconds (headless CI only)", "N" },
        { NULL, 0, 0, 0, NULL, NULL, NULL }
    };

    g_autoptr(GOptionContext) context = g_option_context_new(NULL);
    g_option_context_set_summary(context,
        "NuraBrowser — native WPE WebKit 2.54+ shell, no Cog backend");
    g_option_context_add_main_entries(context, entries, NULL);

    if (!g_option_context_parse(context, argc, argv, error))
        goto done;

    if (*argc != 1) {
        g_set_error_literal(error, G_OPTION_ERROR, G_OPTION_ERROR_BAD_VALUE,
                            "Positional arguments are not supported; use --url");
        goto done;
    }

    if (!url)
        url = g_strdup("about:blank");
    if (!valid_initial_url(url)) {
        g_set_error(error, G_OPTION_ERROR, G_OPTION_ERROR_BAD_VALUE,
                    "Invalid initial URL: expected absolute HTTP(S) or about:blank");
        goto done;
    }

    /* Explicit CLI wins over environment. If neither is present, the
     * safe headless default prevents unexpected DRM-master acquisition. */
    const char *selected = platform ? platform : g_getenv("WPE_PLATFORM");
    if (!selected || !*selected)
        selected = "headless";
    if (!valid_platform(selected)) {
        g_set_error(error, G_OPTION_ERROR, G_OPTION_ERROR_BAD_VALUE,
                    "Unsupported WPE platform '%s' (headless|wayland|drm)",
                    selected);
        goto done;
    }

    if (exit_after_ms < 0 || exit_after_ms > 3600000) {
        g_set_error_literal(error, G_OPTION_ERROR, G_OPTION_ERROR_BAD_VALUE,
                            "--exit-after-ms must be between 0 and 3600000");
        goto done;
    }
    if (exit_after_ms && g_strcmp0(selected, "headless") != 0) {
        g_set_error_literal(error, G_OPTION_ERROR, G_OPTION_ERROR_BAD_VALUE,
                            "--exit-after-ms is for the headless platform only");
        goto done;
    }

    nurabrowser_options_clear(options);
    options->url = g_steal_pointer(&url);
    options->platform = g_strdup(selected);
    options->no_control = no_control;
    options->exit_after_ms = (guint)exit_after_ms;
    success = TRUE;

done:
    g_free(url);
    g_free(platform);
    return success;
}
