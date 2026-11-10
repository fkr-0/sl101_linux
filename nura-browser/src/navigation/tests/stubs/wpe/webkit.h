/* SPDX-License-Identifier: MIT
 * TEST DOUBLE ONLY: intentionally not a WPE WebKit development header.
 * Never include this directory in the production or ARMHF build.
 */
#ifndef NAV_TEST_WPE_WEBKIT_H
#define NAV_TEST_WPE_WEBKIT_H

#include <glib-object.h>

G_BEGIN_DECLS
typedef enum {
    WEBKIT_LOAD_STARTED,
    WEBKIT_LOAD_REDIRECTED,
    WEBKIT_LOAD_COMMITTED,
    WEBKIT_LOAD_FINISHED
} WebKitLoadEvent;

typedef struct _WebKitWebView WebKitWebView;
typedef struct _WebKitWebViewClass WebKitWebViewClass;

GType webkit_web_view_get_type(void);
#define WEBKIT_TYPE_WEB_VIEW (webkit_web_view_get_type())
#define WEBKIT_IS_WEB_VIEW(object) (G_TYPE_CHECK_INSTANCE_TYPE((object), WEBKIT_TYPE_WEB_VIEW))

void webkit_web_view_load_uri(WebKitWebView *view, const gchar *uri);
const gchar *webkit_web_view_get_uri(WebKitWebView *view);
const gchar *webkit_web_view_get_title(WebKitWebView *view);
gboolean webkit_web_view_can_go_back(WebKitWebView *view);
gboolean webkit_web_view_can_go_forward(WebKitWebView *view);
gboolean webkit_web_view_is_loading(WebKitWebView *view);
void webkit_web_view_go_back(WebKitWebView *view);
void webkit_web_view_go_forward(WebKitWebView *view);
void webkit_web_view_reload(WebKitWebView *view);
void webkit_web_view_stop_loading(WebKitWebView *view);

/* Fixtures, absent from actual WPE WebKit. */
WebKitWebView *fake_webkit_view_new(void);
void fake_webkit_set_title(WebKitWebView *view, const gchar *title);
void fake_webkit_finish_load(WebKitWebView *view);
guint fake_webkit_reload_count(WebKitWebView *view);

G_END_DECLS
#endif
