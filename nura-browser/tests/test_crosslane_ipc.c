/* SPDX-License-Identifier: MIT
 * Host-only real navigation/control linkage and AF_UNIX integration.
 * Fake WebKit is supplied only by navigation/tests; not a WebKit build.
 */
#define _POSIX_C_SOURCE 200809L
#include <nurabrowser/contract.h>
#include <gio/gunixsocketaddress.h>
#include <json-glib/json-glib.h>
#include <glib/gstdio.h>
#include <string.h>
#include <unistd.h>

typedef struct {
    NuraBrowserContext ctx;
    char *socket_path;
} Fixture;
static char *runtime_dir;

static void setup(Fixture *f, gconstpointer data)
{
    (void)data;
    memset(f, 0, sizeof(*f));
    f->socket_path = g_build_filename(runtime_dir, "nura-browser.sock", NULL);
    f->ctx.state_dir = runtime_dir;
    f->ctx.view = fake_webkit_view_new();
    nurabrowser_nav_attach(&f->ctx);
    GError *error = NULL;
    g_assert_true(nurabrowser_control_start(&f->ctx, f->socket_path, &error));
    g_assert_no_error(error);
}

static void teardown(Fixture *f, gconstpointer data)
{
    (void)data;
    nurabrowser_control_stop(&f->ctx);
    nurabrowser_nav_shutdown(&f->ctx);
    g_clear_object(&f->ctx.view);
    char *path = g_build_filename(runtime_dir, "navigation-state.v1", NULL);
    g_unlink(path);
    g_free(path);
    g_assert_false(g_file_test(f->socket_path, G_FILE_TEST_EXISTS));
    g_free(f->socket_path);
}

typedef struct {
    GMainLoop *loop;
    char *line;
    GError *error;
    gboolean finished;
} AsyncRead;

static void done_read(GObject *source, GAsyncResult *result, gpointer data)
{
    AsyncRead *r = data;
    r->line = g_data_input_stream_read_line_finish(G_DATA_INPUT_STREAM(source),
                                                    result, NULL, &r->error);
    r->finished = TRUE;
    g_main_loop_quit(r->loop);
}
static gboolean timeout_read(gpointer data)
{
    g_main_loop_quit(((AsyncRead *)data)->loop);
    return G_SOURCE_REMOVE;
}
static char *read_line(GDataInputStream *in)
{
    AsyncRead r = {0};
    r.loop = g_main_loop_new(NULL, FALSE);
    g_data_input_stream_read_line_async(in, G_PRIORITY_DEFAULT, NULL,
                                        done_read, &r);
    guint timer = g_timeout_add_seconds(3, timeout_read, &r);
    g_main_loop_run(r.loop);
    if (r.finished)
        g_source_remove(timer);
    g_assert_true(r.finished);
    g_assert_no_error(r.error);
    g_assert_nonnull(r.line);
    g_main_loop_unref(r.loop);
    return r.line;
}
static GSocketConnection *connect_to(Fixture *f)
{
    GSocketClient *client = g_socket_client_new();
    GSocketAddress *addr = g_unix_socket_address_new(f->socket_path);
    GError *error = NULL;
    GSocketConnection *conn =
        g_socket_client_connect(client, G_SOCKET_CONNECTABLE(addr), NULL, &error);
    g_assert_no_error(error);
    g_assert_nonnull(conn);
    g_object_unref(addr);
    g_object_unref(client);
    return conn;
}
static void send_text(GSocketConnection *conn, const char *text)
{
    GError *error = NULL;
    gsize written = 0;
    g_assert_true(g_output_stream_write_all(
        g_io_stream_get_output_stream(G_IO_STREAM(conn)),
        text, strlen(text), &written, NULL, &error));
    g_assert_no_error(error);
    g_assert_cmpuint(written, ==, strlen(text));
}
static JsonParser *parse_object(const char *text)
{
    JsonParser *p = json_parser_new();
    GError *error = NULL;
    g_assert_true(json_parser_load_from_data(p, text, -1, &error));
    g_assert_no_error(error);
    g_assert_true(JSON_NODE_HOLDS_OBJECT(json_parser_get_root(p)));
    return p;
}
/* The native navigation JSON snapshot must be a structured result object,
 * not an opaque doubly JSON-encoded string. */
static void expect_uri(GDataInputStream *reader, const char *uri)
{
    char *line = read_line(reader);
    JsonParser *outer = parse_object(line);
    JsonObject *response = json_node_get_object(json_parser_get_root(outer));
    g_assert_true(json_object_get_boolean_member(response, "ok"));
    JsonNode *result = json_object_get_member(response, "result");
    g_assert_nonnull(result);
    g_assert_true(JSON_NODE_HOLDS_OBJECT(result));
    JsonObject *snapshot = json_node_get_object(result);
    g_assert_cmpstr(json_object_get_string_member(snapshot, "uri"), ==, uri);
    g_object_unref(outer);
    g_free(line);
}
static void expect_error(GDataInputStream *reader, const char *reason)
{
    char *line = read_line(reader);
    JsonParser *p = parse_object(line);
    JsonObject *response = json_node_get_object(json_parser_get_root(p));
    g_assert_false(json_object_get_boolean_member(response, "ok"));
    g_assert_cmpstr(json_object_get_string_member(response, "error"), ==, reason);
    g_object_unref(p);
    g_free(line);
}
static void test_open_uri(Fixture *f, gconstpointer unused)
{
    (void)unused;
    GSocketConnection *conn = connect_to(f);
    GDataInputStream *reader =
        g_data_input_stream_new(g_io_stream_get_input_stream(G_IO_STREAM(conn)));
    send_text(conn, "{\"command\":\"open\",\"argument\":\"https://example.org/x\"}\n");
    expect_uri(reader, "https://example.org/x");
    send_text(conn, "{\"command\":\"uri\"}\n");
    expect_uri(reader, "https://example.org/x");
    g_object_unref(reader);
    g_object_unref(conn);
}
static void test_history(Fixture *f, gconstpointer unused)
{
    (void)unused;
    GSocketConnection *conn = connect_to(f);
    GDataInputStream *reader =
        g_data_input_stream_new(g_io_stream_get_input_stream(G_IO_STREAM(conn)));
    send_text(conn, "{\"command\":\"open\",\"argument\":\"https://example.org/one\"}\n"
                    "{\"command\":\"open\",\"argument\":\"https://example.org/two\"}\n"
                    "{\"command\":\"back\"}\n"
                    "{\"command\":\"forward\"}\n");
    expect_uri(reader, "https://example.org/one");
    expect_uri(reader, "https://example.org/two");
    expect_uri(reader, "https://example.org/one");
    expect_uri(reader, "https://example.org/two");
    g_object_unref(reader);
    g_object_unref(conn);
}
static void test_reject(Fixture *f, gconstpointer unused)
{
    (void)unused;
    GSocketConnection *conn = connect_to(f);
    GDataInputStream *reader =
        g_data_input_stream_new(g_io_stream_get_input_stream(G_IO_STREAM(conn)));
    send_text(conn, "{\"command\":\"open\",\"argument\":\"file:///etc/shadow\"}\n"
                    "{\"command\":\"eval\",\"argument\":\"alert(1)\"}\n"
                    "{\"command\":\"open\",\"argument\":\"http://user:pass@example.org/\"}\n"
                    "{\"command\":\"open\",\"argument\":\"javascript:alert(1)\"}\n");
    expect_error(reader, "navigation_failed");
    expect_error(reader, "unknown_command");
    expect_error(reader, "navigation_failed");
    expect_error(reader, "navigation_failed");
    g_object_unref(reader);
    g_object_unref(conn);
}
int main(int argc, char **argv)
{
    runtime_dir = g_dir_make_tmp("nura-crosslane-XXXXXX", NULL);
    g_assert_nonnull(runtime_dir);
    g_assert_cmpint(g_chmod(runtime_dir, 0700), ==, 0);
    g_setenv("XDG_RUNTIME_DIR", runtime_dir, TRUE);
    g_test_init(&argc, &argv, NULL);
    g_test_add("/nura/integration/open_uri", Fixture, NULL,
               setup, test_open_uri, teardown);
    g_test_add("/nura/integration/history", Fixture, NULL,
               setup, test_history, teardown);
    g_test_add("/nura/integration/reject_unsafe", Fixture, NULL,
               setup, test_reject, teardown);
    int result = g_test_run();
    g_assert_cmpint(g_rmdir(runtime_dir), ==, 0);
    g_free(runtime_dir);
    return result;
}
