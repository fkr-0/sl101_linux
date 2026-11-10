/* SPDX-License-Identifier: MIT
 *
 * NuraBrowser's single-threaded WPEPlatform lifecycle. Platform selection is
 * performed by WebKit using WPE_PLATFORM, not a libwpe backend object.
 */
#include "engine.h"

#include <nurabrowser/contract.h>
#include <wpe/wpe-platform.h>

#include <errno.h>
#include <glib-unix.h>
#include <glib/gstdio.h>
#include <signal.h>
#include <stdlib.h>
#include <sys/stat.h>
#include <unistd.h>

typedef struct {
    NuraBrowserContext context;
    int result;
    gboolean stopping;
    gboolean nav_attached;
    gboolean control_started;
    guint sigint_source;
    guint sigterm_source;
    guint timer_source;
    WPEView *wpe_view;       /* Borrowed: owned by context.view. */
    WPEDisplay *display;     /* Borrowed: owned by WPEView. */
} NuraBrowserEngine;

static void
request_stop(NuraBrowserEngine *engine, int result)
{
    if (engine->stopping)
        return;
    engine->stopping = TRUE;
    engine->result = result;
    if (engine->context.loop)
        g_main_loop_quit(engine->context.loop);
}

static void
on_wpe_closed(WPEView *view, gpointer user_data)
{
    (void)view;
    request_stop(user_data, EXIT_SUCCESS);
}

static void
on_web_process_terminated(WebKitWebView *view,
                          WebKitWebProcessTerminationReason reason,
                          gpointer user_data)
{
    (void)view;
    const char *detail = "unexpected termination";
    switch (reason) {
    case WEBKIT_WEB_PROCESS_CRASHED:
        detail = "WebProcess crashed";
        break;
    case WEBKIT_WEB_PROCESS_EXCEEDED_MEMORY_LIMIT:
        detail = "WebProcess exceeded memory limit";
        break;
    case WEBKIT_WEB_PROCESS_TERMINATED_BY_API:
        detail = "WebProcess terminated by API";
        break;
    default:
        break;
    }
    g_warning("NuraBrowser: %s; shutting down without automatic restart", detail);
    request_stop(user_data, EXIT_FAILURE);
}

static gboolean
on_load_failed(WebKitWebView *view, WebKitLoadEvent stage,
               const char *uri, GError *error, gpointer user_data)
{
    (void)view;
    (void)uri; /* Never log navigation URLs, which may contain secrets. */
    (void)user_data;
    /* Avoid error->message: some transport errors embed the full URI. */
    g_warning("NuraBrowser: navigation load failed at stage %d (domain=%s, code=%d)",
              (int)stage, error ? g_quark_to_string(error->domain) : "unknown",
              error ? error->code : -1);
    /* FALSE allows WebKit's own error-page handler. A failed navigation
     * must not trigger a busy reload or terminate the control endpoint. */
    return FALSE;
}

static void
on_display_disconnected(WPEDisplay *display, GError *error, gpointer user_data)
{
    (void)display;
    g_warning("NuraBrowser: WPE display disconnected: %s",
              error ? error->message : "no detail");
    request_stop(user_data, EXIT_FAILURE);
}

static gboolean
on_sigint(gpointer user_data)
{
    NuraBrowserEngine *engine = user_data;
    engine->sigint_source = 0;
    request_stop(engine, EXIT_SUCCESS);
    return G_SOURCE_REMOVE;
}

static gboolean
on_sigterm(gpointer user_data)
{
    NuraBrowserEngine *engine = user_data;
    engine->sigterm_source = 0;
    request_stop(engine, EXIT_SUCCESS);
    return G_SOURCE_REMOVE;
}

static gboolean
on_ci_timeout(gpointer user_data)
{
    NuraBrowserEngine *engine = user_data;
    engine->timer_source = 0;
    g_message("NuraBrowser: headless CI exit deadline reached");
    request_stop(engine, EXIT_SUCCESS);
    return G_SOURCE_REMOVE;
}

/* The directory is persistent (not runtime/socket storage) and must not be
 * a symlink or accessible by other users. The navigation lane may store its
 * session metadata in context.state_dir. */
static gboolean
create_private_state_dir(NuraBrowserContext *ctx, GError **error)
{
    const char *state_base = g_get_user_state_dir();
    if (!state_base || !g_path_is_absolute(state_base)) {
        g_set_error_literal(error, G_IO_ERROR, G_IO_ERROR_INVALID_ARGUMENT,
                            "XDG state directory must be an absolute path");
        return FALSE;
    }
    ctx->state_dir = g_build_filename(state_base, "nura-browser", NULL);
    if (g_mkdir_with_parents(ctx->state_dir, 0700) != 0) {
        int saved_errno = errno;
        g_set_error(error, G_IO_ERROR, g_io_error_from_errno(saved_errno),
                    "Cannot create private browser state directory: %s",
                    g_strerror(saved_errno));
        return FALSE;
    }

    struct stat st;
    if (g_lstat(ctx->state_dir, &st) != 0 ||
        !S_ISDIR(st.st_mode) ||
        st.st_uid != geteuid() ||
        (st.st_mode & 0777) != 0700) {
        g_set_error_literal(error, G_IO_ERROR, G_IO_ERROR_PERMISSION_DENIED,
                            "Browser state directory must be owned by this user, real, and mode 0700");
        return FALSE;
    }
    return TRUE;
}

/* XDG_RUNTIME_DIR is pre-provisioned by the session manager. Never invent
 * /tmp fallbacks or mkdir arbitrary runtime paths. Control owns the socket. */
static char *
control_socket_path(GError **error)
{
    const char *dir = g_getenv("XDG_RUNTIME_DIR");
    if (!dir || !g_path_is_absolute(dir)) {
        g_set_error_literal(error, G_IO_ERROR, G_IO_ERROR_INVALID_ARGUMENT,
                            "XDG_RUNTIME_DIR is required for control; use --no-control in standalone CI");
        return NULL;
    }

    g_autofree char *canonical = g_canonicalize_filename(dir, NULL);
    struct stat st;
    if (g_strcmp0(canonical, dir) != 0 ||
        g_lstat(dir, &st) != 0 || !S_ISDIR(st.st_mode) ||
        st.st_uid != geteuid() || (st.st_mode & 0077) != 0) {
        g_set_error_literal(error, G_IO_ERROR, G_IO_ERROR_PERMISSION_DENIED,
                            "XDG_RUNTIME_DIR must be a canonical, private directory owned by this user");
        return NULL;
    }
    return g_build_filename(dir, "nura-browser.sock", NULL);
}

static void
cleanup_engine(NuraBrowserEngine *engine)
{
    if (engine->timer_source)
        g_source_remove(engine->timer_source);
    if (engine->sigterm_source)
        g_source_remove(engine->sigterm_source);
    if (engine->sigint_source)
        g_source_remove(engine->sigint_source);

    if (engine->control_started)
        nurabrowser_control_stop(&engine->context);
    if (engine->nav_attached)
        nurabrowser_nav_shutdown(&engine->context);

    if (engine->wpe_view)
        g_signal_handlers_disconnect_by_data(engine->wpe_view, engine);
    if (engine->display)
        g_signal_handlers_disconnect_by_data(engine->display, engine);
    if (engine->context.view) {
        g_signal_handlers_disconnect_by_data(engine->context.view, engine);
        g_clear_object(&engine->context.view);
    }
    if (engine->context.loop)
        g_main_loop_unref(engine->context.loop);
    g_clear_pointer(&engine->context.state_dir, g_free);
}

int
nurabrowser_engine_run(const NuraBrowserOptions *options)
{
    g_return_val_if_fail(options && options->url && options->platform,
                         EXIT_FAILURE);

    NuraBrowserEngine engine = { 0 };
    engine.result = EXIT_FAILURE;
    g_autoptr(GError) error = NULL;
    g_autofree char *socket_path = NULL;

    /* The modern WPE (2022 GLib) API intentionally has no sandbox-disable
     * setter. Do not accept the WebKit emergency bypass environment flag. */
    if (g_getenv("WEBKIT_DISABLE_SANDBOX_THIS_IS_DANGEROUS")) {
        g_printerr("nura-browser: refusing to run with WebKit sandbox disabled\n");
        return EXIT_FAILURE;
    }
    if (getuid() != geteuid()) {
        g_printerr("nura-browser: setuid execution is unsupported\n");
        return EXIT_FAILURE;
    }
    if (!g_setenv("WPE_PLATFORM", options->platform, TRUE)) {
        g_printerr("nura-browser: cannot select WPE_PLATFORM\n");
        return EXIT_FAILURE;
    }

    if (!create_private_state_dir(&engine.context, &error)) {
        g_printerr("nura-browser: %s\n", error->message);
        goto done;
    }
    if (!options->no_control) {
        socket_path = control_socket_path(&error);
        if (!socket_path) {
            g_printerr("nura-browser: %s\n", error->message);
            goto done;
        }
    }

    engine.context.loop = g_main_loop_new(NULL, FALSE);
    engine.context.view = WEBKIT_WEB_VIEW(g_object_new(WEBKIT_TYPE_WEB_VIEW,
                                                       NULL));
    if (!engine.context.view) {
        g_printerr("nura-browser: WebKitWebView construction failed\n");
        goto done;
    }

    engine.wpe_view = webkit_web_view_get_wpe_view(engine.context.view);
    if (!engine.wpe_view) {
        g_printerr("nura-browser: WPEPlatform view unavailable (verify WPE 2.54+ build)\n");
        goto done;
    }

    /* WPEView and WPEDisplay are borrowed references: the view keeps them
     * alive until webkit_web_view's final unref below. */
    g_signal_connect(engine.wpe_view, "closed",
                     G_CALLBACK(on_wpe_closed), &engine);
    engine.display = wpe_view_get_display(engine.wpe_view);
    if (engine.display)
        g_signal_connect(engine.display, "disconnected",
                         G_CALLBACK(on_display_disconnected), &engine);
    g_signal_connect(engine.context.view, "web-process-terminated",
                     G_CALLBACK(on_web_process_terminated), &engine);
    g_signal_connect(engine.context.view, "load-failed",
                     G_CALLBACK(on_load_failed), &engine);

    nurabrowser_nav_attach(&engine.context);
    engine.nav_attached = TRUE;

    if (!options->no_control) {
        if (!nurabrowser_control_start(&engine.context, socket_path, &error)) {
            g_printerr("nura-browser: control startup failed: %s\n",
                       error ? error->message : "unknown error");
            goto done;
        }
        engine.control_started = TRUE;
    }

    engine.sigint_source = g_unix_signal_add(SIGINT, on_sigint, &engine);
    engine.sigterm_source = g_unix_signal_add(SIGTERM, on_sigterm, &engine);
    if (options->exit_after_ms)
        engine.timer_source = g_timeout_add(options->exit_after_ms,
                                            on_ci_timeout, &engine);

    g_message("NuraBrowser: starting WPEPlatform '%s' (control %s)",
              options->platform, options->no_control ? "off" : "on");
    webkit_web_view_load_uri(engine.context.view, options->url);
    if (!engine.stopping)
        g_main_loop_run(engine.context.loop);
    engine.result = engine.stopping ? engine.result : EXIT_SUCCESS;

done:
    cleanup_engine(&engine);
    return engine.result;
}
