/* SPDX-License-Identifier: MIT */
#include <wpe/webkit.h>

struct _WebKitWebView {
    GObject parent_instance;
    GPtrArray *history;
    gint index;
    gchar *title;
    gboolean loading;
    guint reloads;
};
struct _WebKitWebViewClass { GObjectClass parent_class; };
G_DEFINE_TYPE(WebKitWebView, webkit_web_view, G_TYPE_OBJECT)
enum { PROP_0, PROP_URI, PROP_TITLE, PROP_IS_LOADING, PROP_COUNT };
static GParamSpec *properties[PROP_COUNT];
static guint load_signal;

const gchar *
webkit_web_view_get_uri(WebKitWebView *view)
{
    return view->index < 0 ? NULL : g_ptr_array_index(view->history, view->index);
}
const gchar *
webkit_web_view_get_title(WebKitWebView *view) { return view->title; }
gboolean
webkit_web_view_can_go_back(WebKitWebView *view) { return view->index > 0; }
gboolean
webkit_web_view_can_go_forward(WebKitWebView *view)
{
    return view->index >= 0 &&
        view->index + 1 < (gint)view->history->len;
}
gboolean
webkit_web_view_is_loading(WebKitWebView *view) { return view->loading; }

static void
fake_get_property(GObject *object, guint id, GValue *value, GParamSpec *spec)
{
    WebKitWebView *view = (WebKitWebView *)object;
    if (id == PROP_URI)
        g_value_set_string(value, webkit_web_view_get_uri(view));
    else if (id == PROP_TITLE)
        g_value_set_string(value, view->title);
    else if (id == PROP_IS_LOADING)
        g_value_set_boolean(value, view->loading);
    else
        G_OBJECT_WARN_INVALID_PROPERTY_ID(object, id, spec);
}
static void
fake_finalize(GObject *object)
{
    WebKitWebView *view = (WebKitWebView *)object;
    g_ptr_array_unref(view->history);
    g_free(view->title);
    G_OBJECT_CLASS(webkit_web_view_parent_class)->finalize(object);
}
static void
webkit_web_view_class_init(WebKitWebViewClass *klass)
{
    GObjectClass *base = G_OBJECT_CLASS(klass);
    base->get_property = fake_get_property;
    base->finalize = fake_finalize;
    properties[PROP_URI] = g_param_spec_string("uri", "URI", "Current URI",
                                               NULL, G_PARAM_READABLE);
    properties[PROP_TITLE] = g_param_spec_string("title", "Title", "Page title",
                                                 NULL, G_PARAM_READABLE);
    properties[PROP_IS_LOADING] = g_param_spec_boolean("is-loading", "Loading",
                                                       "Whether loading", FALSE,
                                                       G_PARAM_READABLE);
    g_object_class_install_properties(base, PROP_COUNT, properties);
    load_signal = g_signal_new("load-changed", G_TYPE_FROM_CLASS(klass),
                               G_SIGNAL_RUN_LAST, 0, NULL, NULL, NULL,
                               G_TYPE_NONE, 1, G_TYPE_INT);
}
static void
webkit_web_view_init(WebKitWebView *view)
{
    view->history = g_ptr_array_new_with_free_func(g_free);
    view->index = -1;
}
WebKitWebView *
fake_webkit_view_new(void) { return g_object_new(WEBKIT_TYPE_WEB_VIEW, NULL); }
void
fake_webkit_set_title(WebKitWebView *view, const gchar *title)
{
    g_free(view->title);
    view->title = g_strdup(title);
    g_object_notify(G_OBJECT(view), "title");
}
static void
set_uri(WebKitWebView *view)
{
    view->loading = TRUE;
    g_object_notify(G_OBJECT(view), "uri");
    g_object_notify(G_OBJECT(view), "is-loading");
    g_signal_emit(view, load_signal, 0, WEBKIT_LOAD_STARTED);
    g_signal_emit(view, load_signal, 0, WEBKIT_LOAD_COMMITTED);
}
void
webkit_web_view_load_uri(WebKitWebView *view, const gchar *uri)
{
    if (view->index + 1 < (gint)view->history->len)
        g_ptr_array_remove_range(view->history, view->index + 1,
                                 view->history->len - view->index - 1);
    g_ptr_array_add(view->history, g_strdup(uri));
    view->index++;
    set_uri(view);
}
void
webkit_web_view_go_back(WebKitWebView *view)
{
    if (webkit_web_view_can_go_back(view)) {
        view->index--;
        set_uri(view);
    }
}
void
webkit_web_view_go_forward(WebKitWebView *view)
{
    if (webkit_web_view_can_go_forward(view)) {
        view->index++;
        set_uri(view);
    }
}
void
webkit_web_view_reload(WebKitWebView *view)
{
    view->reloads++;
    set_uri(view);
}
void
webkit_web_view_stop_loading(WebKitWebView *view)
{
    view->loading = FALSE;
    g_object_notify(G_OBJECT(view), "is-loading");
}
void
fake_webkit_finish_load(WebKitWebView *view)
{
    webkit_web_view_stop_loading(view);
    g_signal_emit(view, load_signal, 0, WEBKIT_LOAD_FINISHED);
}
guint
fake_webkit_reload_count(WebKitWebView *view) { return view->reloads; }
