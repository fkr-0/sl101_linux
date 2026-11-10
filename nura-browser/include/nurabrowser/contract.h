/* SPDX-License-Identifier: MIT
 * Shared, reviewed contract for four independent NuraBrowser workers.
 * Do NOT change this header without coordinating all four worker lanes.
 * WebKit 2.54 WPEPlatform API, not deprecated libwpe/Cog backend-fdo API.
 */
#ifndef NURABROWSER_CONTRACT_H
#define NURABROWSER_CONTRACT_H

#include <glib.h>
#include <gio/gio.h>
#include <wpe/webkit.h>

G_BEGIN_DECLS

typedef struct {
    /* Owned by the engine lane. Valid until both subsystems stop. */
    WebKitWebView *view;
    GMainLoop *loop;
    /* A persistent user-private directory (mode 0700). */
    char *state_dir;
} NuraBrowserContext;

/* Navigation lane: every command must be validated and handled on the GLib
 * main thread. Commands: open <absolute http(s) URL>, back, forward,
 * reload, stop, uri (query). A NULL argument is valid for zero-arg commands.
 * On failure return FALSE and set GError. Never evaluate arbitrary JS. */
gboolean nurabrowser_nav_dispatch(
    NuraBrowserContext *ctx, const char *command, const char *argument,
    char **response, GError **error);
void nurabrowser_nav_attach(NuraBrowserContext *ctx);
void nurabrowser_nav_shutdown(NuraBrowserContext *ctx);

/* Control lane: private Unix socket, 0600, under XDG_RUNTIME_DIR.
 * Reject non-matching peer UID using SO_PEERCRED / GCredentials. Use
 * bounded requests and GLib main-context dispatch; no shell execution.
 * Response format: one line JSON: {"ok":true,"result":...} or error. */
gboolean nurabrowser_control_start(
    NuraBrowserContext *ctx, const char *socket_path, GError **error);
void nurabrowser_control_stop(NuraBrowserContext *ctx);

G_END_DECLS
#endif
