/* SPDX-License-Identifier: MIT
 * WebKit 2.54+ / WPEPlatform navigation lane.
 * No legacy libwpe backend, DOM injection, threads or subprocesses.
 */
#define _POSIX_C_SOURCE 200809L
#include <nurabrowser/contract.h>

#include "state.h"
#include "url.h"

#include <unistd.h>

typedef struct {
    NuraBrowserContext *context; /* engine keeps this alive until shutdown */
    WebKitWebView *view;          /* strong reference, released on shutdown */
    GThread *owner;
    int directory_fd;
    GSource *save_source;
    char *committed_uri;
    char *uri;
    char *title;
    gboolean loading;
    gboolean can_back;
    gboolean can_forward;
    gulong uri_signal;
    gulong title_signal;
    gulong loading_signal;
    gulong load_signal;
} NavState;

/* Engine and control both execute on the same GLib main thread. The table is
 * deliberately not synchronized: dispatch from foreign threads is rejected. */
static GHashTable *states;
static GThread *main_thread;

static void
snapshot(NavState *state)
{
    const char *uri = webkit_web_view_get_uri(state->view);
    const char *title = webkit_web_view_get_title(state->view);
    g_free(state->uri);
    g_free(state->title);
    /* Page-controlled title and redirect URL must not cause unbounded IPC
     * responses. The JSON emitter replaces truncated invalid UTF-8. */
    state->uri = g_strndup(uri ? uri : "", 8192);
    state->title = g_strndup(title ? title : "", 1024);
    state->loading = webkit_web_view_is_loading(state->view);
    state->can_back = webkit_web_view_can_go_back(state->view);
    state->can_forward = webkit_web_view_can_go_forward(state->view);
}

static void
json_string(GString *json, const char *text, gsize max_bytes)
{
    gsize length = text ? strnlen(text, max_bytes) : 0;
    g_string_append_c(json, '"');
    for (gsize i = 0; i < length; ) {
        unsigned char c = (unsigned char)text[i];
        if (c < 0x20 || c == '"' || c == '\\') {
            if (c == '"' || c == '\\') {
                g_string_append_c(json, '\\');
                g_string_append_c(json, (char)c);
            } else
                g_string_append_printf(json, "\\u%04x", (unsigned int)c);
            i++;
        } else if (c < 0x80) {
            g_string_append_c(json, (char)c);
            i++;
        } else {
            gunichar cp = g_utf8_get_char_validated(text + i, length - i);
            if (cp == (gunichar)-1 || cp == (gunichar)-2) {
                g_string_append(json, "\\ufffd");
                i++;
            } else {
                char bytes[8] = { 0 };
                gint count = g_unichar_to_utf8(cp, bytes);
                g_string_append_len(json, bytes, count);
                i += (gsize)count;
            }
        }
    }
    g_string_append_c(json, '"');
}

static char *
response_json(NavState *state, const char *command)
{
    GString *json = g_string_new("{\"command\":");
    json_string(json, command, 32);
    g_string_append(json, ",\"uri\":");
    json_string(json, state->uri, 8192);
    g_string_append(json, ",\"title\":");
    json_string(json, state->title, 1024);
    g_string_append_printf(json,
                           ",\"is_loading\":%s,\"can_go_back\":%s,"
                           "\"can_go_forward\":%s}",
                           state->loading ? "true" : "false",
                           state->can_back ? "true" : "false",
                           state->can_forward ? "true" : "false");
    return g_string_free(json, FALSE);
}

static gboolean
save_committed(gpointer data)
{
    NavState *state = data;
    GSource *source = state->save_source;
    state->save_source = NULL;
    if (state->committed_uri)
        nurabrowser_nav_state_write(state->directory_fd, state->committed_uri);
    g_source_unref(source);
    return G_SOURCE_REMOVE;
}

static void
schedule_save(NavState *state, const char *uri)
{
    char *safe_uri = NULL;
    if (state->directory_fd < 0 ||
        !nurabrowser_nav_normalize_url(uri, &safe_uri, NULL))
        return;
    g_free(state->committed_uri);
    state->committed_uri = safe_uri;
    if (state->save_source)
        return; /* coalesce redirects and rapid navigation */
    state->save_source = g_timeout_source_new(250);
    g_source_set_callback(state->save_source, save_committed, state, NULL);
    g_source_attach(state->save_source,
                    state->context->loop ?
                    g_main_loop_get_context(state->context->loop) :
                    g_main_context_default());
}

static void
view_changed(WebKitWebView *view, GParamSpec *property, gpointer data)
{
    NavState *state = data;
    (void)view;
    (void)property;
    snapshot(state);
}

static void
load_changed(WebKitWebView *view, WebKitLoadEvent event, gpointer data)
{
    NavState *state = data;
    snapshot(state);
    if (event == WEBKIT_LOAD_COMMITTED)
        schedule_save(state, webkit_web_view_get_uri(view));
}

static gboolean
fail_dispatch(GError **error, GIOErrorEnum code, const char *message)
{
    g_set_error_literal(error, G_IO_ERROR, code, message);
    return FALSE;
}

gboolean
nurabrowser_nav_dispatch(NuraBrowserContext *ctx, const char *command,
                         const char *argument, char **response, GError **error)
{
    NavState *state;
    char *normalized = NULL;

    if (response)
        *response = NULL;
    if (!ctx || !response || !command)
        return fail_dispatch(error, G_IO_ERROR_INVALID_ARGUMENT,
                             "Missing navigation context, command or response");
    if (!main_thread || main_thread != g_thread_self())
        return fail_dispatch(error, G_IO_ERROR_FAILED,
                             "Navigation must run on the engine's GLib main thread");
    state = states ? g_hash_table_lookup(states, ctx) : NULL;
    if (!state || !ctx->view || ctx->view != state->view)
        return fail_dispatch(error, G_IO_ERROR_CLOSED,
                             "Navigation is not attached to the active WebView");
    if (g_strcmp0(command, "open") == 0) {
        if (!nurabrowser_nav_normalize_url(argument, &normalized, error))
            return FALSE;
        webkit_web_view_load_uri(state->view, normalized);
        g_free(normalized);
    } else {
        if (argument && *argument)
            return fail_dispatch(error, G_IO_ERROR_INVALID_ARGUMENT,
                                 "This navigation command does not take an argument");
        if (g_strcmp0(command, "back") == 0) {
            if (!webkit_web_view_can_go_back(state->view))
                return fail_dispatch(error, G_IO_ERROR_FAILED, "No previous history entry");
            webkit_web_view_go_back(state->view);
        } else if (g_strcmp0(command, "forward") == 0) {
            if (!webkit_web_view_can_go_forward(state->view))
                return fail_dispatch(error, G_IO_ERROR_FAILED, "No next history entry");
            webkit_web_view_go_forward(state->view);
        } else if (g_strcmp0(command, "reload") == 0) {
            if (!webkit_web_view_get_uri(state->view))
                return fail_dispatch(error, G_IO_ERROR_FAILED, "No page to reload");
            webkit_web_view_reload(state->view);
        } else if (g_strcmp0(command, "stop") == 0)
            webkit_web_view_stop_loading(state->view);
        else if (g_strcmp0(command, "uri") != 0)
            return fail_dispatch(error, G_IO_ERROR_NOT_SUPPORTED,
                                 "Unsupported navigation command");
    }
    snapshot(state);
    *response = response_json(state, command);
    return TRUE;
}

void
nurabrowser_nav_attach(NuraBrowserContext *ctx)
{
    NavState *state;
    char *restored;

    if (!ctx || !ctx->view || !WEBKIT_IS_WEB_VIEW(ctx->view))
        return;
    if (main_thread && main_thread != g_thread_self())
        return;
    if (!main_thread)
        main_thread = g_thread_self();
    if (!states)
        states = g_hash_table_new(g_direct_hash, g_direct_equal);
    if (g_hash_table_contains(states, ctx))
        return;

    state = g_new0(NavState, 1);
    state->context = ctx;
    state->view = g_object_ref(ctx->view);
    state->owner = g_thread_self();
    state->directory_fd = nurabrowser_nav_state_open(ctx->state_dir);
    state->uri_signal = g_signal_connect(state->view, "notify::uri",
                                         G_CALLBACK(view_changed), state);
    state->title_signal = g_signal_connect(state->view, "notify::title",
                                           G_CALLBACK(view_changed), state);
    state->loading_signal = g_signal_connect(state->view, "notify::is-loading",
                                             G_CALLBACK(view_changed), state);
    state->load_signal = g_signal_connect(state->view, "load-changed",
                                          G_CALLBACK(load_changed), state);
    g_hash_table_insert(states, ctx, state);
    snapshot(state);

    /* One last committed HTTP(S) URL is restored. We deliberately do not
     * load a blank page or replace a URL already loaded by the engine. */
    restored = nurabrowser_nav_state_read(state->directory_fd);
    if (restored && (!webkit_web_view_get_uri(state->view) ||
                     g_strcmp0(webkit_web_view_get_uri(state->view),
                               "about:blank") == 0))
        webkit_web_view_load_uri(state->view, restored);
    g_free(restored);
}

void
nurabrowser_nav_shutdown(NuraBrowserContext *ctx)
{
    NavState *state;
    if (!ctx || !main_thread || main_thread != g_thread_self() || !states)
        return;
    state = g_hash_table_lookup(states, ctx);
    if (!state)
        return;
    /* First disconnect signals, then destroy callbacks, then persist the
     * last known COMMITTED URI. No callback may retain a freed state. */
    g_signal_handler_disconnect(state->view, state->uri_signal);
    g_signal_handler_disconnect(state->view, state->title_signal);
    g_signal_handler_disconnect(state->view, state->loading_signal);
    g_signal_handler_disconnect(state->view, state->load_signal);
    if (state->save_source) {
        g_source_destroy(state->save_source);
        g_source_unref(state->save_source);
        state->save_source = NULL;
    }
    if (state->committed_uri)
        nurabrowser_nav_state_write(state->directory_fd, state->committed_uri);
    if (state->directory_fd >= 0)
        close(state->directory_fd);
    g_object_unref(state->view);
    g_free(state->uri);
    g_free(state->title);
    g_free(state->committed_uri);
    g_hash_table_remove(states, ctx);
    g_free(state);
}
