/* SPDX-License-Identifier: MIT */
#include "../options.h"

#include <glib.h>
#include <string.h>

static gboolean
parse_case(const char *const *arguments, NuraBrowserOptions *options,
           GError **error)
{
    int argc = 1;
    while (arguments[argc - 1])
        ++argc;
    gchar **argv = g_new0(gchar *, (gsize)argc + 1);
    argv[0] = g_strdup("nura-browser");
    for (int i = 1; i < argc; i++)
        argv[i] = g_strdup(arguments[i - 1]);

    gboolean result = nurabrowser_options_parse(&argc, &argv, options, error);
    g_strfreev(argv);
    return result;
}

static void
test_defaults(void)
{
    g_unsetenv("WPE_PLATFORM");
    NuraBrowserOptions options = { 0 };
    const char *args[] = { NULL };
    g_assert_true(parse_case(args, &options, NULL));
    g_assert_cmpstr(options.url, ==, "about:blank");
    g_assert_cmpstr(options.platform, ==, "headless");
    g_assert_false(options.no_control);
    g_assert_cmpuint(options.exit_after_ms, ==, 0);
    nurabrowser_options_clear(&options);
}

static void
test_override_and_headless_ci(void)
{
    g_setenv("WPE_PLATFORM", "drm", TRUE);
    NuraBrowserOptions options = { 0 };
    const char *args[] = {
        "--url=https://example.org/a?q=b",
        "--platform=headless",
        "--no-control",
        "--exit-after-ms=25",
        NULL
    };
    g_assert_true(parse_case(args, &options, NULL));
    g_assert_cmpstr(options.platform, ==, "headless");
    g_assert_cmpstr(options.url, ==, "https://example.org/a?q=b");
    g_assert_true(options.no_control);
    g_assert_cmpuint(options.exit_after_ms, ==, 25);
    /* The parser does not mutate WPE_PLATFORM: the engine applies it
     * before any GObject touches the WebKit platform. */
    g_assert_cmpstr(g_getenv("WPE_PLATFORM"), ==, "drm");
    nurabrowser_options_clear(&options);
    g_unsetenv("WPE_PLATFORM");
}

static void
test_environment_passthrough(void)
{
    g_setenv("WPE_PLATFORM", "wayland", TRUE);
    NuraBrowserOptions options = { 0 };
    const char *args[] = { "--url=about:blank", NULL };
    g_assert_true(parse_case(args, &options, NULL));
    g_assert_cmpstr(options.platform, ==, "wayland");
    nurabrowser_options_clear(&options);
    g_unsetenv("WPE_PLATFORM");
}

static void
assert_rejected(const char *const *args)
{
    NuraBrowserOptions options = { 0 };
    g_autoptr(GError) error = NULL;
    g_assert_false(parse_case(args, &options, &error));
    /* GLib reports unknown switches as UNKNOWN_OPTION, while errors from
     * our own validators use BAD_VALUE. Both must fail closed. */
    g_assert_nonnull(error);
    g_assert_cmpuint(error->domain, ==, G_OPTION_ERROR);
    g_assert_true(error->code == G_OPTION_ERROR_BAD_VALUE ||
                  error->code == G_OPTION_ERROR_UNKNOWN_OPTION);
    nurabrowser_options_clear(&options);
}

static void
test_rejected_url_schemes(void)
{
    const char *file[] = { "--url=file:///etc/passwd", NULL };
    const char *javascript[] = { "--url=javascript:alert(1)", NULL };
    const char *relative[] = { "--url=relative", NULL };
    const char *no_host[] = { "--url=https:///path", NULL };
    const char *userinfo[] = { "--url=https://user:password@example.org/", NULL };
    const char *newline[] = { "--url=https://example.org/\nheader", NULL };
    assert_rejected(file);
    assert_rejected(javascript);
    assert_rejected(relative);
    assert_rejected(no_host);
    assert_rejected(userinfo);
    assert_rejected(newline);
}

static void
test_rejected_options(void)
{
    const char *invalid_platform[] = { "--platform=evil", NULL };
    const char *bad_timeout[] = { "--exit-after-ms=-1", NULL };
    const char *large_timeout[] = { "--exit-after-ms=3600001", NULL };
    const char *drm_timeout[] = {
        "--platform=drm", "--exit-after-ms=20", NULL
    };
    const char *positional[] = { "https://example.org", NULL };
    const char *unknown[] = { "--enable-untrusted-js", NULL };
    const char *bogus_integer[] = { "--exit-after-ms=invalid", NULL };
    g_unsetenv("WPE_PLATFORM");
    assert_rejected(invalid_platform);
    assert_rejected(bad_timeout);
    assert_rejected(large_timeout);
    assert_rejected(drm_timeout);
    assert_rejected(positional);
    assert_rejected(unknown);
    assert_rejected(bogus_integer);
}

static void
test_rejected_environment(void)
{
    g_setenv("WPE_PLATFORM", "not-a-platform", TRUE);
    NuraBrowserOptions options = { 0 };
    const char *args[] = { NULL };
    g_autoptr(GError) error = NULL;
    g_assert_false(parse_case(args, &options, &error));
    g_assert_error(error, G_OPTION_ERROR, G_OPTION_ERROR_BAD_VALUE);
    nurabrowser_options_clear(&options);
    g_unsetenv("WPE_PLATFORM");
}

int
main(int argc, char **argv)
{
    g_test_init(&argc, &argv, NULL);
    g_test_add_func("/nura/engine/defaults", test_defaults);
    g_test_add_func("/nura/engine/explicit-platform", test_override_and_headless_ci);
    g_test_add_func("/nura/engine/env", test_environment_passthrough);
    g_test_add_func("/nura/engine/url-rejected", test_rejected_url_schemes);
    g_test_add_func("/nura/engine/options-rejected", test_rejected_options);
    g_test_add_func("/nura/engine/env-rejected", test_rejected_environment);
    return g_test_run();
}
