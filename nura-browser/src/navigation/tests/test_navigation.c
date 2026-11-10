/* SPDX-License-Identifier: MIT */
#include <nurabrowser/contract.h>
#include "../url.h"
#include "../state.h"

#include <fcntl.h>
#include <glib/gstdio.h>
#include <sys/stat.h>
#include <unistd.h>

static void
test_urls(void)
{
    const char *good[] = {
        "http://example.com/", "https://example.org/path?a=1&b=2#top",
        "HTTPS://EXAMPLE.COM/ok", "http://127.0.0.1:8080/",
        "https://[::1]:443/a%20b"
    };
    const char *bad[] = {
        "", "x", "example.com", "/relative", "//example.com",
        "javascript:alert(1)", "file:///etc/passwd", "data:text/plain,hi",
        "about:blank", "ftp://foo/", "https:evil.com", "https:///no-host",
        "http://user:pass@example.com", "http://user@example.com",
        "https://example.com@evil.test", "http://example.com\\@evil.test",
        "http://exa%6dple.com/", "https://example.com:0/",
        "https://example.com:99999/", "https://example.com:foo/",
        "https://example.com:/", "https://[::1]:/",
        "https://./", "https://foo..bar/", "https://foo bar/",
        "https://-bad.com/", "https://bad-.com/",
        "https://example.com/%0aBAD", "https://example.com/?x=%0D",
        "https://example.com/?x=%00", "https://example.com/\r\nHost:x",
        "https://example.com/\tbad", "https://example.com/#a b",
    };
    for (guint i = 0; i < G_N_ELEMENTS(good); i++) {
        char *normalized = NULL;
        GError *error = NULL;
        g_assert_true(nurabrowser_nav_normalize_url(good[i], &normalized, &error));
        g_assert_no_error(error);
        g_assert_nonnull(normalized);
        g_assert_cmpint(strlen(normalized), >, 7);
        g_free(normalized);
    }
    for (guint i = 0; i < G_N_ELEMENTS(bad); i++) {
        char *normalized = NULL;
        GError *error = NULL;
        gboolean ok = nurabrowser_nav_normalize_url(bad[i], &normalized, &error);
        if (ok)
            g_error("Unexpected URL acceptance: %s", bad[i]);
        g_assert_error(error, G_IO_ERROR, G_IO_ERROR_INVALID_ARGUMENT);
        g_assert_null(normalized);
        g_assert_cmpuint(strlen(error->message), <=, 160);
        g_clear_error(&error);
    }
    char *long_url = g_malloc0(9000);
    strcpy(long_url, "https://example.com/");
    memset(long_url + strlen(long_url), 'a', 8500);
    GError *error = NULL;
    char *normalized = NULL;
    g_assert_false(nurabrowser_nav_normalize_url(long_url, &normalized, &error));
    g_assert_error(error, G_IO_ERROR, G_IO_ERROR_INVALID_ARGUMENT);
    g_clear_error(&error);
    g_free(long_url);
    g_assert_false(nurabrowser_nav_normalize_url(NULL, &normalized, &error));
    g_assert_error(error, G_IO_ERROR, G_IO_ERROR_INVALID_ARGUMENT);
    g_clear_error(&error);
}

static char *
new_dir(void)
{
    GError *error = NULL;
    char *dir = g_dir_make_tmp("nura-nav-XXXXXX", &error);
    g_assert_no_error(error);
    g_assert_nonnull(dir);
    g_assert_cmpint(g_chmod(dir, 0700), ==, 0);
    return dir;
}

static void
remove_dir(char *dir)
{
    char *state = g_build_filename(dir, "navigation-state.v1", NULL);
    g_unlink(state);
    g_free(state);
    g_assert_cmpint(g_rmdir(dir), ==, 0);
    g_free(dir);
}

static char *
dispatch(NuraBrowserContext *ctx, const char *cmd, const char *arg)
{
    char *response = NULL;
    GError *error = NULL;
    g_assert_true(nurabrowser_nav_dispatch(ctx, cmd, arg, &response, &error));
    g_assert_no_error(error);
    g_assert_nonnull(response);
    g_assert_true(g_str_has_prefix(response, "{\"command\":"));
    return response;
}

static void
dispatch_fails(NuraBrowserContext *ctx, const char *cmd, const char *arg,
               GIOErrorEnum expected)
{
    /* Output parameters are caller-uninitialized or NULL; verify even a
     * non-NULL sentinel gets cleared, without leaking caller-owned memory. */
    char *response = (char *)"sentinel";
    GError *error = NULL;
    g_assert_false(nurabrowser_nav_dispatch(ctx, cmd, arg, &response, &error));
    g_assert_null(response);
    g_assert_error(error, G_IO_ERROR, (int)expected);
    g_assert_cmpuint(strlen(error->message), <=, 160);
    g_clear_error(&error);
}

static void
test_dispatch(void)
{
    char *dir = new_dir();
    WebKitWebView *view = fake_webkit_view_new();
    NuraBrowserContext ctx = { view, NULL, dir };
    char *result;

    dispatch_fails(&ctx, "uri", NULL, G_IO_ERROR_FAILED);
    nurabrowser_nav_attach(&ctx);
    nurabrowser_nav_attach(&ctx); /* idempotent */
    result = dispatch(&ctx, "uri", NULL);
    g_assert_nonnull(strstr(result, "\"uri\":\"\""));
    g_free(result);
    dispatch_fails(&ctx, "back", NULL, G_IO_ERROR_FAILED);
    dispatch_fails(&ctx, "forward", NULL, G_IO_ERROR_FAILED);
    dispatch_fails(&ctx, "reload", NULL, G_IO_ERROR_FAILED);
    dispatch_fails(&ctx, "eval", NULL, G_IO_ERROR_NOT_SUPPORTED);
    dispatch_fails(&ctx, "stop", "bad", G_IO_ERROR_INVALID_ARGUMENT);
    dispatch_fails(&ctx, "uri", "http://example.com/", G_IO_ERROR_INVALID_ARGUMENT);
    dispatch_fails(&ctx, "open", "file:///etc/passwd", G_IO_ERROR_INVALID_ARGUMENT);
    dispatch_fails(&ctx, "open", "", G_IO_ERROR_INVALID_ARGUMENT);

    WebKitWebView *other = fake_webkit_view_new();
    ctx.view = other;
    dispatch_fails(&ctx, "uri", NULL, G_IO_ERROR_CLOSED);
    ctx.view = view;
    g_object_unref(other);

    result = dispatch(&ctx, "open", "https://example.com/one");
    g_assert_nonnull(strstr(result, "\"uri\":\"https://example.com/one\""));
    g_assert_nonnull(strstr(result, "\"is_loading\":true"));
    g_free(result);
    fake_webkit_set_title(view, "hello\"\nfoo\\bar");
    fake_webkit_finish_load(view);
    result = dispatch(&ctx, "uri", "");
    g_assert_nonnull(strstr(result, "\"title\":\"hello\\\"\\u000afoo\\\\bar\""));
    g_assert_nonnull(strstr(result, "\"is_loading\":false"));
    g_free(result);

    g_free(dispatch(&ctx, "open", "https://example.com/two"));
    result = dispatch(&ctx, "back", NULL);
    g_assert_nonnull(strstr(result, "\"uri\":\"https://example.com/one\""));
    g_assert_nonnull(strstr(result, "\"can_go_forward\":true"));
    g_free(result);
    result = dispatch(&ctx, "forward", NULL);
    g_assert_nonnull(strstr(result, "\"uri\":\"https://example.com/two\""));
    g_assert_nonnull(strstr(result, "\"can_go_back\":true"));
    g_free(result);
    g_free(dispatch(&ctx, "reload", NULL));
    g_assert_cmpuint(fake_webkit_reload_count(view), ==, 1);
    g_free(dispatch(&ctx, "stop", NULL));
    g_assert_false(webkit_web_view_is_loading(view));
    nurabrowser_nav_shutdown(&ctx);
    nurabrowser_nav_shutdown(&ctx); /* idempotent */
    /* If signal handlers survived shutdown this could access freed state. */
    fake_webkit_set_title(view, "safe after shutdown");
    dispatch_fails(&ctx, "uri", NULL, G_IO_ERROR_CLOSED);
    g_object_unref(view);
    remove_dir(dir);
}

static void
test_persistence(void)
{
    char *dir = new_dir();
    WebKitWebView *view = fake_webkit_view_new();
    NuraBrowserContext ctx = { view, NULL, dir };
    nurabrowser_nav_attach(&ctx);
    g_free(dispatch(&ctx, "open", "https://example.com/saved"));
    /* Shutdown flushes pending atomic write, no timer wait. */
    nurabrowser_nav_shutdown(&ctx);
    int fd = nurabrowser_nav_state_open(dir);
    g_assert_cmpint(fd, >=, 0);
    char *saved = nurabrowser_nav_state_read(fd);
    g_assert_cmpstr(saved, ==, "https://example.com/saved");
    g_free(saved);
    close(fd);
    g_object_unref(view);

    view = fake_webkit_view_new();
    ctx.view = view;
    nurabrowser_nav_attach(&ctx);
    g_assert_cmpstr(webkit_web_view_get_uri(view), ==,
                    "https://example.com/saved");
    nurabrowser_nav_shutdown(&ctx);
    g_object_unref(view);

    /* Preloaded engine pages must not be replaced by the restored URL. */
    view = fake_webkit_view_new();
    webkit_web_view_load_uri(view, "https://example.com/engine-preloaded");
    ctx.view = view;
    nurabrowser_nav_attach(&ctx);
    g_assert_cmpstr(webkit_web_view_get_uri(view), ==,
                    "https://example.com/engine-preloaded");
    nurabrowser_nav_shutdown(&ctx);
    g_object_unref(view);
    remove_dir(dir);
}

static void
test_corrupt_and_symlink_state(void)
{
    char *dir = new_dir();
    char *target = g_build_filename(dir, "target", NULL);
    char *link = g_build_filename(dir, "navigation-state.v1", NULL);
    g_assert_true(g_file_set_contents(target, "do-not-touch", -1, NULL));
    g_assert_cmpint(symlink("target", link), ==, 0);
    int fd = nurabrowser_nav_state_open(dir);
    g_assert_cmpint(fd, >=, 0);
    g_assert_null(nurabrowser_nav_state_read(fd));
    g_assert_true(nurabrowser_nav_state_write(fd, "https://example.com/safe"));
    char *text = NULL;
    g_assert_true(g_file_get_contents(target, &text, NULL, NULL));
    g_assert_cmpstr(text, ==, "do-not-touch");
    g_free(text);
    char *saved = nurabrowser_nav_state_read(fd);
    g_assert_cmpstr(saved, ==, "https://example.com/safe");
    g_free(saved);
    close(fd);
    g_assert_cmpint(g_unlink(link), ==, 0);
    g_assert_true(g_file_set_contents(link, "NURABROWSER_STATE_V1\nfile:///etc/passwd\n",
                                      -1, NULL));
    fd = nurabrowser_nav_state_open(dir);
    g_assert_cmpint(fd, >=, 0);
    g_assert_null(nurabrowser_nav_state_read(fd));
    close(fd);
    g_assert_cmpint(g_unlink(link), ==, 0);
    g_assert_cmpint(g_unlink(target), ==, 0);
    g_free(target);
    g_free(link);
    remove_dir(dir);
}

static void
test_state_directory_security(void)
{
    char *dir = new_dir();
    char *alias = g_strconcat(dir, "-alias", NULL);
    g_assert_cmpint(symlink(dir, alias), ==, 0);
    g_assert_cmpint(nurabrowser_nav_state_open(alias), ==, -1);
    g_assert_cmpint(g_chmod(dir, 0755), ==, 0);
    g_assert_cmpint(nurabrowser_nav_state_open(dir), ==, -1);
    g_assert_cmpint(g_chmod(dir, 0700), ==, 0);
    g_assert_cmpint(g_unlink(alias), ==, 0);
    g_free(alias);
    remove_dir(dir);
}

typedef struct { NuraBrowserContext *ctx; gboolean denied; } ThreadCase;
static gpointer
foreign_thread(gpointer data)
{
    ThreadCase *t = data;
    char *response = NULL;
    GError *error = NULL;
    t->denied = !nurabrowser_nav_dispatch(t->ctx, "uri", NULL, &response, &error) &&
                error && error->code == G_IO_ERROR_FAILED && !response;
    g_clear_error(&error);
    g_free(response);
    return NULL;
}
static void
test_foreign_thread(void)
{
    char *dir = new_dir();
    WebKitWebView *view = fake_webkit_view_new();
    NuraBrowserContext ctx = { view, NULL, dir };
    nurabrowser_nav_attach(&ctx);
    ThreadCase t = { &ctx, FALSE };
    GThread *thread = g_thread_new("foreign-ipc", foreign_thread, &t);
    g_thread_join(thread);
    g_assert_true(t.denied);
    nurabrowser_nav_shutdown(&ctx);
    g_object_unref(view);
    remove_dir(dir);
}

int
main(int argc, char **argv)
{
    g_test_init(&argc, &argv, NULL);
    g_test_add_func("/nav/url/strict", test_urls);
    g_test_add_func("/nav/dispatch/stateful", test_dispatch);
    g_test_add_func("/nav/state/restart", test_persistence);
    g_test_add_func("/nav/state/symlink-corrupt", test_corrupt_and_symlink_state);
    g_test_add_func("/nav/state/dir-permissions", test_state_directory_security);
    g_test_add_func("/nav/dispatch/foreign-thread", test_foreign_thread);
    return g_test_run();
}
