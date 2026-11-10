/* SPDX-License-Identifier: MIT
 * Host-only GLib test; tests actual socket I/O with fake navigation ABI.
 */
#define _GNU_SOURCE
#include <nurabrowser/contract.h>
#include "control-private.h"
#include <gio/gunixsocketaddress.h>
#include <json-glib/json-glib.h>
#include <glib/gstdio.h>
#include <sys/stat.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>
#include <string.h>

static guint dispatches;
static char *shared_runtime_dir;
static char *last_command, *last_argument;

/* Navigation double; no WebKit, eval or process creation. */
gboolean nurabrowser_nav_dispatch(NuraBrowserContext *ctx,
                                   const char *command, const char *argument,
                                   char **response, GError **error)
{
    g_assert_nonnull(ctx);
    dispatches++;
    g_free(last_command);
    g_free(last_argument);
    last_command = g_strdup(command);
    last_argument = g_strdup(argument);
    if (g_str_equal(command, "open") &&
        (!argument || !(g_str_has_prefix(argument, "http://") ||
                        g_str_has_prefix(argument, "https://")))) {
        g_set_error_literal(error, G_IO_ERROR, G_IO_ERROR_INVALID_ARGUMENT,
                            "sensitive internal navigation detail");
        return FALSE;
    }
    *response = g_str_equal(command, "uri") ?
        g_strdup("https://example.org/?a=\"quoted\"\n") : g_strdup("ack");
    return TRUE;
}

typedef struct {
    char *runtime_dir;
    char *socket_path;
    NuraBrowserContext ctx;
} Fixture;

static void setup(Fixture *f, gconstpointer data)
{
    (void) data;
    memset(f, 0, sizeof(*f));
    f->runtime_dir = g_strdup(shared_runtime_dir);
    f->socket_path = g_build_filename(f->runtime_dir,
                                      "nura-browser.sock", NULL);
    dispatches = 0;
    g_clear_pointer(&last_command, g_free);
    g_clear_pointer(&last_argument, g_free);
}

static void teardown(Fixture *f, gconstpointer data)
{
    (void) data;
    nurabrowser_control_stop(&f->ctx);
    g_free(f->socket_path);
    g_free(f->runtime_dir);
    g_clear_pointer(&last_command, g_free);
    g_clear_pointer(&last_argument, g_free);
}

static void start(Fixture *f)
{
    GError *error = NULL;
    g_assert_true(nurabrowser_control_start(&f->ctx, NULL, &error));
    g_assert_no_error(error);
}

static GSocketConnection *connect_to(Fixture *f)
{
    GError *error = NULL;
    GSocketClient *client = g_socket_client_new();
    GSocketAddress *addr = g_unix_socket_address_new(f->socket_path);
    GSocketConnection *conn =
        g_socket_client_connect(client, G_SOCKET_CONNECTABLE(addr), NULL, &error);
    g_assert_no_error(error);
    g_assert_nonnull(conn);
    g_object_unref(client);
    g_object_unref(addr);
    return conn;
}

typedef struct {
    GMainLoop *loop;
    char *line;
    GError *error;
    gboolean complete;
} Reply;

static void read_complete(GObject *src, GAsyncResult *res, gpointer data)
{
    Reply *r = data;
    r->line = g_data_input_stream_read_line_finish(
        G_DATA_INPUT_STREAM(src), res, NULL, &r->error);
    r->complete = TRUE;
    g_main_loop_quit(r->loop);
}

static gboolean timed_out(gpointer data)
{
    Reply *r = data;
    g_main_loop_quit(r->loop);
    return G_SOURCE_REMOVE;
}

static char *read_line(GDataInputStream *in)
{
    Reply r = {0};
    r.loop = g_main_loop_new(NULL, FALSE);
    g_data_input_stream_read_line_async(in, G_PRIORITY_DEFAULT,
                                        NULL, read_complete, &r);
    guint timer = g_timeout_add_seconds(4, timed_out, &r);
    g_main_loop_run(r.loop);
    if (r.complete)
        g_source_remove(timer);
    g_assert_true(r.complete);
    g_assert_no_error(r.error);
    g_main_loop_unref(r.loop);
    return r.line;
}

static void send_data(GSocketConnection *conn, const void *buf, gsize len)
{
    GError *error = NULL;
    gsize done = 0;
    g_assert_true(g_output_stream_write_all(
        g_io_stream_get_output_stream(G_IO_STREAM(conn)),
        buf, len, &done, NULL, &error));
    g_assert_no_error(error);
    g_assert_cmpuint(done, ==, len);
}

static void send_text(GSocketConnection *conn, const char *str)
{
    send_data(conn, str, strlen(str));
}

static void expect(GDataInputStream *in, gboolean ok, const char *error_code)
{
    char *line = read_line(in);
    g_assert_nonnull(line);
    JsonParser *parser = json_parser_new();
    GError *error = NULL;
    g_assert_true(json_parser_load_from_data(parser, line, -1, &error));
    g_assert_no_error(error);
    JsonNode *root = json_parser_get_root(parser);
    g_assert_true(JSON_NODE_HOLDS_OBJECT(root));
    JsonObject *object = json_node_get_object(root);
    g_assert_cmpint(json_object_get_boolean_member(object, "ok"), ==, ok);
    if (!ok)
        g_assert_cmpstr(json_object_get_string_member(object, "error"),
                        ==, error_code);
    else
        g_assert_true(json_object_has_member(object, "result"));
    g_object_unref(parser);
    g_free(line);
}

static void test_socket_permissions(Fixture *f, gconstpointer data)
{
    (void) data;
    start(f);
    struct stat st;
    g_assert_cmpint(lstat(f->socket_path, &st), ==, 0);
    g_assert_true(S_ISSOCK(st.st_mode));
    g_assert_cmpuint(st.st_mode & 0777, ==, 0600);
    g_assert_cmpuint(st.st_uid, ==, geteuid());

    GSocketConnection *conn = connect_to(f);
    GDataInputStream *in = g_data_input_stream_new(
        g_io_stream_get_input_stream(G_IO_STREAM(conn)));
    send_text(conn, "{\"command\":\"back\"}\n");
    expect(in, TRUE, NULL);
    g_assert_cmpstr(last_command, ==, "back");
    g_assert_null(last_argument);
    g_object_unref(in);
    g_object_unref(conn);
}

static void test_multiframe(Fixture *f, gconstpointer data)
{
    (void) data;
    start(f);
    GSocketConnection *conn = connect_to(f);
    GDataInputStream *in = g_data_input_stream_new(
        g_io_stream_get_input_stream(G_IO_STREAM(conn)));
    send_text(conn, "{\"command\":\"op");
    while (g_main_context_pending(NULL))
        g_main_context_iteration(NULL, FALSE);
    send_text(conn, "en\",\"argument\":\"https://example.org\"}\n"
                    "{\"command\":\"uri\"}\n");
    expect(in, TRUE, NULL);
    expect(in, TRUE, NULL);
    g_assert_cmpuint(dispatches, ==, 2);
    g_assert_cmpstr(last_command, ==, "uri");
    g_object_unref(in);
    g_object_unref(conn);
}

static void test_bad_requests(Fixture *f, gconstpointer data)
{
    (void) data;
    start(f);
    GSocketConnection *conn = connect_to(f);
    GDataInputStream *in = g_data_input_stream_new(
        g_io_stream_get_input_stream(G_IO_STREAM(conn)));
    send_text(conn, "not json\n"
                    "{}\n"
                    "{\"command\":\"exec\",\"argument\":\"id\"}\n"
                    "{\"command\":\"open\"}\n"
                    "{\"command\":\"back\",\"argument\":\"nope\"}\n"
                    "{\"command\":\"open\",\"argument\":55}\n"
                    "{\"command\":\"open\",\"argument\":\"file:///etc/passwd\"}\n"
                    "{\"command\":\"back\",\"extra\":true}\n"
                    "{\"command\":\"back\",\"argument\":\"\\u0000\"}\n");
    const char *errors[] = {
        "invalid_json", "invalid_request", "unknown_command",
        "invalid_argument", "invalid_argument", "invalid_argument",
        "navigation_failed", "invalid_request", "invalid_utf8"
    };
    for (gsize i = 0; i < G_N_ELEMENTS(errors); i++)
        expect(in, FALSE, errors[i]);
    const char bad[] = {'{','"','x','"',':','"',(char)0xff,'"','}','\n'};
    send_data(conn, bad, sizeof bad);
    expect(in, FALSE, "invalid_utf8");
    g_assert_cmpuint(dispatches, ==, 1);
    g_object_unref(in);
    g_object_unref(conn);
}

static void test_oversized(Fixture *f, gconstpointer data)
{
    (void) data;
    start(f);
    GSocketConnection *conn = connect_to(f);
    GDataInputStream *in = g_data_input_stream_new(
        g_io_stream_get_input_stream(G_IO_STREAM(conn)));
    char *frame = g_malloc0(9001);
    memset(frame, 'x', 8999);
    frame[8999] = '\n';
    send_data(conn, frame, 9000);
    expect(in, FALSE, "frame_too_large");
    g_free(frame);
    g_object_unref(in);
    g_object_unref(conn);
}

static void test_restarts(Fixture *f, gconstpointer data)
{
    (void) data;
    GError *error = NULL;
    g_assert_true(g_file_set_contents(f->socket_path, "occupied", -1, &error));
    g_assert_no_error(error);
    g_assert_false(nurabrowser_control_start(&f->ctx, NULL, &error));
    g_assert_error(error, G_IO_ERROR, G_IO_ERROR_EXISTS);
    g_clear_error(&error);
    char *contents = NULL;
    g_assert_true(g_file_get_contents(f->socket_path, &contents, NULL, &error));
    g_assert_no_error(error);
    g_assert_cmpstr(contents, ==, "occupied");
    g_free(contents);
    g_assert_cmpint(g_unlink(f->socket_path), ==, 0);
    start(f);
    g_assert_false(nurabrowser_control_start(&f->ctx, NULL, &error));
    g_assert_error(error, G_IO_ERROR, G_IO_ERROR_EXISTS);
    g_clear_error(&error);
    nurabrowser_control_stop(&f->ctx);
    nurabrowser_control_stop(&f->ctx);
    start(f);
    nurabrowser_control_stop(&f->ctx);
}

static void test_path_security(Fixture *f, gconstpointer data)
{
    (void) data;
    GError *error = NULL;
    char *target = g_build_filename(f->runtime_dir, "absent", NULL);
    g_assert_cmpint(symlink(target, f->socket_path), ==, 0);
    g_assert_false(nurabrowser_control_start(&f->ctx, NULL, &error));
    g_assert_error(error, G_IO_ERROR, G_IO_ERROR_EXISTS);
    g_clear_error(&error);
    g_assert_cmpint(g_unlink(f->socket_path), ==, 0);
    g_free(target);

    g_assert_cmpint(g_chmod(f->runtime_dir, 0755), ==, 0);
    g_assert_false(nurabrowser_control_start(&f->ctx, NULL, &error));
    g_assert_error(error, G_IO_ERROR, G_IO_ERROR_PERMISSION_DENIED);
    g_clear_error(&error);
    g_assert_cmpint(g_chmod(f->runtime_dir, 0700), ==, 0);

    char *path = g_build_filename(f->runtime_dir, "..", "wrong.sock", NULL);
    g_assert_false(nurabrowser_control_start(&f->ctx, path, &error));
    g_assert_error(error, G_IO_ERROR, G_IO_ERROR_INVALID_ARGUMENT);
    g_clear_error(&error);
    g_free(path);
}

static void test_credentials(Fixture *f, gconstpointer data)
{
    (void) f;
    (void) data;
    g_assert_false(nurabrowser_control_peer_uid_allowed(NULL, geteuid()));
    GCredentials *c = g_credentials_new();
    g_assert_true(nurabrowser_control_peer_uid_allowed(c, geteuid()));
    GError *error = NULL;
    g_assert_true(g_credentials_set_unix_user(c, geteuid() + 1, &error));
    g_assert_no_error(error);
    g_assert_false(nurabrowser_control_peer_uid_allowed(c, geteuid()));
    g_object_unref(c);
}

static void test_no_shell(Fixture *f, gconstpointer data)
{
    (void) data;
    start(f);
    GSocketConnection *conn = connect_to(f);
    GDataInputStream *in = g_data_input_stream_new(
        g_io_stream_get_input_stream(G_IO_STREAM(conn)));
    char *proof = g_build_filename(f->runtime_dir, "SHOULD_NOT_EXIST", NULL);
    char *request = g_strdup_printf(
        "{\"command\":\"open\",\"argument\":\"https://example.org/$(touch %s)\"}\n",
        proof);
    send_text(conn, request);
    expect(in, TRUE, NULL);
    g_assert_nonnull(strstr(last_argument, "$(touch"));
    g_assert_false(g_file_test(proof, G_FILE_TEST_EXISTS));
    g_free(request);
    g_free(proof);
    g_object_unref(in);
    g_object_unref(conn);
}

static void test_multiple_clients(Fixture *f, gconstpointer data)
{
    (void) data;
    start(f);
    GSocketConnection *a = connect_to(f), *b = connect_to(f);
    GDataInputStream *ra = g_data_input_stream_new(
        g_io_stream_get_input_stream(G_IO_STREAM(a)));
    GDataInputStream *rb = g_data_input_stream_new(
        g_io_stream_get_input_stream(G_IO_STREAM(b)));
    send_text(a, "{\"command\":\"reload\"}\n");
    send_text(b, "{\"command\":\"stop\"}\n");
    expect(rb, TRUE, NULL);
    expect(ra, TRUE, NULL);
    g_assert_cmpuint(dispatches, ==, 2);
    g_object_unref(ra); g_object_unref(rb);
    g_object_unref(a); g_object_unref(b);
}

static void test_idle_timeout(Fixture *f, gconstpointer data)
{
    (void) data;
    start(f);
    GSocketConnection *conn = connect_to(f);
    GDataInputStream *in = g_data_input_stream_new(
        g_io_stream_get_input_stream(G_IO_STREAM(conn)));
    /* Test binary uses a 1-second idle timeout, production uses 15. */
    char *line = read_line(in);
    g_assert_null(line);
    g_object_unref(in);
    g_object_unref(conn);
}

static void test_stop_pending(Fixture *f, gconstpointer data)
{
    (void) data;
    start(f);
    GSocketConnection *conn = connect_to(f);
    GDataInputStream *in = g_data_input_stream_new(
        g_io_stream_get_input_stream(G_IO_STREAM(conn)));
    send_text(conn, "{\"command\":\"back\"}\n");
    expect(in, TRUE, NULL);
    send_text(conn, "{\"command\":\"op"); /* Pending incomplete frame. */
    nurabrowser_control_stop(&f->ctx);
    g_assert_false(g_file_test(f->socket_path, G_FILE_TEST_EXISTS));
    g_object_unref(in);
    g_object_unref(conn);
    while (g_main_context_pending(NULL))
        g_main_context_iteration(NULL, FALSE);
    start(f); /* No dangling client callbacks may corrupt new instance. */
    nurabrowser_control_stop(&f->ctx);
}

static void test_inode_guard(Fixture *f, gconstpointer data)
{
    (void) data;
    start(f);
    g_assert_cmpint(g_unlink(f->socket_path), ==, 0);
    GError *error = NULL;
    g_assert_true(g_file_set_contents(f->socket_path, "replacement", -1, &error));
    g_assert_no_error(error);
    nurabrowser_control_stop(&f->ctx);
    char *contents = NULL;
    g_assert_true(g_file_get_contents(f->socket_path, &contents, NULL, &error));
    g_assert_no_error(error);
    g_assert_cmpstr(contents, ==, "replacement");
    g_free(contents);
    g_assert_cmpint(g_unlink(f->socket_path), ==, 0);
}

static void test_stale_socket(Fixture *f, gconstpointer data)
{
    (void) data;
    int fd = socket(AF_UNIX, SOCK_STREAM, 0);
    g_assert_cmpint(fd, >=, 0);
    struct sockaddr_un address = {0};
    address.sun_family = AF_UNIX;
    g_assert_cmpuint(strlen(f->socket_path), <, sizeof(address.sun_path));
    strcpy(address.sun_path, f->socket_path);
    g_assert_cmpint(bind(fd, (struct sockaddr *)&address, sizeof(address)), ==, 0);
    g_assert_cmpint(close(fd), ==, 0);
    GError *error = NULL;
    g_assert_false(nurabrowser_control_start(&f->ctx, NULL, &error));
    g_assert_error(error, G_IO_ERROR, G_IO_ERROR_EXISTS);
    g_clear_error(&error);
    struct stat st;
    g_assert_cmpint(lstat(f->socket_path, &st), ==, 0);
    g_assert_true(S_ISSOCK(st.st_mode));
    g_assert_cmpint(g_unlink(f->socket_path), ==, 0);
}

int main(int argc, char **argv)
{
    shared_runtime_dir = g_dir_make_tmp("nura-control-XXXXXX", NULL);
    g_assert_nonnull(shared_runtime_dir);
    g_assert_cmpint(g_chmod(shared_runtime_dir, 0700), ==, 0);
    g_setenv("XDG_RUNTIME_DIR", shared_runtime_dir, TRUE);
    g_test_init(&argc, &argv, NULL);
    g_test_add("/nura/control/socket_permissions", Fixture, NULL,
               setup, test_socket_permissions, teardown);
    g_test_add("/nura/control/multiframe", Fixture, NULL,
               setup, test_multiframe, teardown);
    g_test_add("/nura/control/bad_requests", Fixture, NULL,
               setup, test_bad_requests, teardown);
    g_test_add("/nura/control/oversized", Fixture, NULL,
               setup, test_oversized, teardown);
    g_test_add("/nura/control/restarts", Fixture, NULL,
               setup, test_restarts, teardown);
    g_test_add("/nura/control/path_security", Fixture, NULL,
               setup, test_path_security, teardown);
    g_test_add("/nura/control/credentials", Fixture, NULL,
               setup, test_credentials, teardown);
    g_test_add("/nura/control/no_shell", Fixture, NULL,
               setup, test_no_shell, teardown);
    g_test_add("/nura/control/multiple_clients", Fixture, NULL,
               setup, test_multiple_clients, teardown);
    g_test_add("/nura/control/idle_timeout", Fixture, NULL,
               setup, test_idle_timeout, teardown);
    g_test_add("/nura/control/stop_pending", Fixture, NULL,
               setup, test_stop_pending, teardown);
    g_test_add("/nura/control/inode_guard", Fixture, NULL,
               setup, test_inode_guard, teardown);
    g_test_add("/nura/control/stale_socket", Fixture, NULL,
               setup, test_stale_socket, teardown);
    int result = g_test_run();
    g_assert_cmpint(g_rmdir(shared_runtime_dir), ==, 0);
    g_free(shared_runtime_dir);
    return result;
}
