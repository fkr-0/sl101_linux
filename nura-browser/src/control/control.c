/* SPDX-License-Identifier: MIT
 * NuraBrowser NuraLoumi control IPC. Linux AF_UNIX, same UID only.
 *
 * Lifecycle and all callbacks belong to the browser's GLib main context.
 * No WebKit code or subprocesses are invoked here; navigation is delegated
 * solely to the reviewed native contract.
 */
#define _GNU_SOURCE
#include <nurabrowser/contract.h>
#include "control-private.h"

#include <json-glib/json-glib.h>
#include <gio/gunixsocketaddress.h>
#include <glib/gstdio.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/un.h>
#include <unistd.h>
#include <errno.h>
#include <string.h>

#define CONTROL_NAME "nura-browser.sock"
#define MAX_FRAME 8192u             /* Request payload must be < 8 KiB. */
#define MAX_RESULT 4096u
#define MAX_CLIENTS 32u
#define MAX_PENDING 32768u
#define READ_CHUNK 2048u
#ifndef NURABROWSER_CONTROL_IDLE_SECONDS
#define NURABROWSER_CONTROL_IDLE_SECONDS 15
#endif
#define IDLE_SECONDS NURABROWSER_CONTROL_IDLE_SECONDS

typedef struct _ControlServer ControlServer;
typedef struct _ControlClient ControlClient;

struct _ControlServer {
    gint refs;
    NuraBrowserContext *ctx;        /* Borrowed; engine must stop first. */
    GSocketService *listener;
    GMainContext *main_context;
    GHashTable *clients;            /* Owns one ref per active client. */
    char *path;
    dev_t socket_dev;
    ino_t socket_ino;
    gboolean has_identity;
    gboolean stopping;
};

struct _ControlClient {
    gint refs;
    ControlServer *server;          /* Strong reference. */
    GSocketConnection *connection;
    GCancellable *cancel;
    GSource *idle;
    GString *incoming;
    GQueue outgoing;                /* GBytes* queue. */
    GBytes *current;
    gsize offset;
    gsize pending_bytes;
    guint8 scratch[READ_CHUNK];
    gboolean reading;
    gboolean writing;
    gboolean draining;
    gboolean closed;
};

/* All public calls must be made from the engine's owning main thread. */
static GHashTable *servers;

static ControlServer *server_ref(ControlServer *server)
{
    g_atomic_int_inc(&server->refs);
    return server;
}

static void server_unref(ControlServer *server)
{
    if (!g_atomic_int_dec_and_test(&server->refs))
        return;
    g_clear_object(&server->listener);
    g_clear_pointer(&server->clients, g_hash_table_unref);
    g_clear_pointer(&server->main_context, g_main_context_unref);
    g_free(server->path);
    g_free(server);
}

static ControlClient *client_ref(ControlClient *client)
{
    g_atomic_int_inc(&client->refs);
    return client;
}

static void client_unref(ControlClient *client)
{
    if (!g_atomic_int_dec_and_test(&client->refs))
        return;
    if (client->idle) {
        g_source_destroy(client->idle);
        g_source_unref(client->idle);
    }
    if (client->current)
        g_bytes_unref(client->current);
    while (!g_queue_is_empty(&client->outgoing))
        g_bytes_unref(g_queue_pop_head(&client->outgoing));
    g_string_free(client->incoming, TRUE);
    g_clear_object(&client->cancel);
    g_clear_object(&client->connection);
    server_unref(client->server);
    g_free(client);
}

static void client_close(ControlClient *client)
{
    if (client->closed)
        return;
    client->closed = TRUE;
    g_cancellable_cancel(client->cancel);
    if (client->idle) {
        g_source_destroy(client->idle);
        g_source_unref(client->idle);
        client->idle = NULL;
    }
    /* Close is local, nonblocking socket shutdown; never wait for peer. */
    g_socket_close(g_socket_connection_get_socket(client->connection), NULL);
    g_hash_table_remove(client->server->clients, client);
    client_unref(client);           /* Drop client-table ownership. */
}

static gboolean idle_expired(gpointer data)
{
    ControlClient *client = data;
    client_close(client);
    return G_SOURCE_REMOVE;
}

static void touch_idle(ControlClient *client)
{
    if (client->idle)
        g_source_set_ready_time(client->idle,
                                g_get_monotonic_time() + IDLE_SECONDS * G_USEC_PER_SEC);
}

static void client_read_begin(ControlClient *client);
static void client_write_begin(ControlClient *client);

static void written(GObject *source, GAsyncResult *result, gpointer data)
{
    ControlClient *client = data;
    GError *error = NULL;
    gssize count = g_output_stream_write_finish(G_OUTPUT_STREAM(source),
                                                  result, &error);
    client->writing = FALSE;
    if (!client->closed) {
        if (count <= 0) {
            client_close(client);
        } else {
            client->offset += (gsize) count;
            client->pending_bytes -= (gsize) count;
            if (client->offset == g_bytes_get_size(client->current)) {
                g_bytes_unref(client->current);
                client->current = NULL;
                client->offset = 0;
            }
            touch_idle(client);
            client_write_begin(client);
            if (!client->closed && !client->draining &&
                client->pending_bytes < MAX_PENDING / 2)
                client_read_begin(client);
        }
    }
    g_clear_error(&error);
    client_unref(client);
}

static void client_write_begin(ControlClient *client)
{
    if (client->closed || client->writing)
        return;
    if (!client->current) {
        client->current = g_queue_pop_head(&client->outgoing);
        client->offset = 0;
    }
    if (!client->current) {
        if (client->draining)
            client_close(client);
        return;
    }
    gsize length = 0;
    const guint8 *bytes = g_bytes_get_data(client->current, &length);
    client->writing = TRUE;
    g_output_stream_write_async(
        g_io_stream_get_output_stream(G_IO_STREAM(client->connection)),
        bytes + client->offset, length - client->offset, G_PRIORITY_DEFAULT,
        client->cancel, written, client_ref(client));
}

static gboolean enqueue(ControlClient *client, char *owned_line)
{
    if (client->closed) {
        g_free(owned_line);
        return FALSE;
    }
    const gsize length = strlen(owned_line);
    if (length > MAX_FRAME || client->pending_bytes + length > MAX_PENDING) {
        g_free(owned_line);
        client_close(client);       /* Bounded queue; no unbounded buffering. */
        return FALSE;
    }
    client->pending_bytes += length;
    g_queue_push_tail(&client->outgoing, g_bytes_new_take(owned_line, length));
    client_write_begin(client);
    return !client->closed;
}

static void send_error(ControlClient *client, const char *code)
{
    /* Error codes are static and controlled by this module, never peer data. */
    char *line = g_strdup_printf("{\"ok\":false,\"error\":\"%s\"}\n", code);
    enqueue(client, line);
}

static void send_success(ControlClient *client, const char *result)
{
    JsonBuilder *builder = json_builder_new();
    json_builder_begin_object(builder);
    json_builder_set_member_name(builder, "ok");
    json_builder_add_boolean_value(builder, TRUE);
    json_builder_set_member_name(builder, "result");
    /* Navigation B returns a serialized JSON object snapshot. Embed that
     * as a value, not a doubly JSON-encoded string. Preserve plain-text
     * results from other reviewed native dispatch implementations. */
    JsonParser *parsed_result = NULL;
    if (result && result[0] == '{') {
        parsed_result = json_parser_new();
        if (!json_parser_load_from_data(parsed_result, result, -1, NULL) ||
            !JSON_NODE_HOLDS_OBJECT(json_parser_get_root(parsed_result))) {
            g_clear_object(&parsed_result);
        }
    }
    if (parsed_result)
        json_builder_add_value(builder,
                               json_node_copy(json_parser_get_root(parsed_result)));
    else if (result)
        json_builder_add_string_value(builder, result);
    else
        json_builder_add_null_value(builder);
    g_clear_object(&parsed_result);
    json_builder_end_object(builder);

    JsonGenerator *generator = json_generator_new();
    JsonNode *root = json_builder_get_root(builder);
    json_generator_set_root(generator, root);
    char *json = json_generator_to_data(generator, NULL);
    json_node_free(root);
    g_object_unref(generator);
    g_object_unref(builder);

    if (!json || strlen(json) + 1 > MAX_FRAME) {
        g_free(json);
        send_error(client, "result_too_large");
        return;
    }
    char *line = g_strconcat(json, "\n", NULL);
    g_free(json);
    enqueue(client, line);
}

static gboolean allowed_command(const char *command)
{
    return g_strcmp0(command, "open") == 0 ||
           g_strcmp0(command, "back") == 0 ||
           g_strcmp0(command, "forward") == 0 ||
           g_strcmp0(command, "reload") == 0 ||
           g_strcmp0(command, "stop") == 0 ||
           g_strcmp0(command, "uri") == 0;
}

static gboolean is_string_member(JsonNode *node)
{
    return node && JSON_NODE_HOLDS_VALUE(node) &&
           json_node_get_value_type(node) == G_TYPE_STRING;
}

static void process_frame(ControlClient *client, const char *line, gsize length)
{
    if (length == 0 || length >= MAX_FRAME) {
        send_error(client, "invalid_frame");
        return;
    }
    if (!g_utf8_validate(line, length, NULL) ||
        g_strstr_len(line, (gssize) length, "\\u0000")) {
        send_error(client, "invalid_utf8");
        return;
    }

    GError *error = NULL;
    JsonParser *parser = json_parser_new();
    if (!json_parser_load_from_data(parser, line, (gssize) length, &error)) {
        send_error(client, "invalid_json");
        goto done;
    }
    JsonNode *root = json_parser_get_root(parser);
    if (!root || !JSON_NODE_HOLDS_OBJECT(root)) {
        send_error(client, "invalid_request");
        goto done;
    }

    JsonObject *object = json_node_get_object(root);
    JsonNode *cmd_node = json_object_get_member(object, "command");
    JsonNode *arg_node = json_object_get_member(object, "argument");
    if (!is_string_member(cmd_node) || json_object_get_size(object) > 2 ||
        (json_object_get_size(object) == 2 && !arg_node)) {
        send_error(client, "invalid_request");
        goto done;
    }

    const char *command = json_node_get_string(cmd_node);
    if (!allowed_command(command)) {
        send_error(client, "unknown_command");
        goto done;
    }
    const gboolean is_open = g_str_equal(command, "open");
    const char *argument = NULL;
    if (is_open) {
        if (!is_string_member(arg_node)) {
            send_error(client, "invalid_argument");
            goto done;
        }
        argument = json_node_get_string(arg_node);
        if (!argument || !*argument || strlen(argument) > MAX_RESULT) {
            send_error(client, "invalid_argument");
            goto done;
        }
    } else if (arg_node && !JSON_NODE_HOLDS_NULL(arg_node)) {
        send_error(client, "invalid_argument");
        goto done;
    }

    char *response = NULL;
    if (!nurabrowser_nav_dispatch(client->server->ctx, command, argument,
                                  &response, &error)) {
        send_error(client, "navigation_failed");
    } else if (response && (!g_utf8_validate(response, -1, NULL) ||
                            strlen(response) > MAX_RESULT)) {
        send_error(client, "result_too_large");
    } else {
        send_success(client, response);
    }
    g_free(response);
done:
    g_clear_error(&error);          /* Do not leak internal detail to clients. */
    g_object_unref(parser);
}

static void received(GObject *source, GAsyncResult *result, gpointer data)
{
    ControlClient *client = data;
    GError *error = NULL;
    gssize count = g_input_stream_read_finish(G_INPUT_STREAM(source),
                                               result, &error);
    client->reading = FALSE;
    if (client->closed)
        goto done;
    if (count <= 0) {
        client_close(client);       /* EOF, timeout/cancel, or read error. */
        goto done;
    }
    touch_idle(client);

    const guint8 *cursor = client->scratch;
    const guint8 *end = cursor + count;
    while (cursor < end && !client->closed && !client->draining) {
        const guint8 *newline = memchr(cursor, '\n', (gsize)(end - cursor));
        gsize piece = (gsize)((newline ? newline : end) - cursor);
        if (piece + client->incoming->len >= MAX_FRAME) {
            send_error(client, "frame_too_large");
            client->draining = TRUE;    /* Reply once and close. */
            client_write_begin(client);
            break;
        }
        g_string_append_len(client->incoming, (const char *) cursor,
                            (gssize) piece);
        if (!newline)
            break;
        process_frame(client, client->incoming->str, client->incoming->len);
        g_string_truncate(client->incoming, 0);
        cursor = newline + 1;
    }
    if (!client->closed && !client->draining &&
        client->pending_bytes < MAX_PENDING / 2)
        client_read_begin(client);
done:
    g_clear_error(&error);
    client_unref(client);
}

static void client_read_begin(ControlClient *client)
{
    if (client->closed || client->draining || client->reading ||
        client->pending_bytes >= MAX_PENDING / 2)
        return;
    client->reading = TRUE;
    g_input_stream_read_async(
        g_io_stream_get_input_stream(G_IO_STREAM(client->connection)),
        client->scratch, sizeof(client->scratch), G_PRIORITY_DEFAULT,
        client->cancel, received, client_ref(client));
}

static ControlClient *client_new(ControlServer *server, GSocketConnection *conn)
{
    ControlClient *client = g_new0(ControlClient, 1);
    client->refs = 1;
    client->server = server_ref(server);
    client->connection = g_object_ref(conn);
    client->cancel = g_cancellable_new();
    client->incoming = g_string_sized_new(512);
    g_queue_init(&client->outgoing);
    client->idle = g_timeout_source_new_seconds(IDLE_SECONDS);
    g_source_set_callback(client->idle, idle_expired, client, NULL);
    g_source_attach(client->idle, server->main_context);
    g_hash_table_add(server->clients, client);
    client_read_begin(client);
    return client;
}

/* Exposed only to the internal CPU tests; not part of the shared ABI. */
gboolean nurabrowser_control_peer_uid_allowed(GCredentials *credentials,
                                               uid_t expected_uid)
{
    if (!credentials)
        return FALSE;
    GError *error = NULL;
    uid_t peer_uid = g_credentials_get_unix_user(credentials, &error);
    gboolean allowed = error == NULL && peer_uid == expected_uid;
    g_clear_error(&error);
    return allowed;
}

static gboolean incoming_connection(GSocketService *service,
                                    GSocketConnection *connection,
                                    GObject *source_object,
                                    gpointer data)
{
    (void) service;
    (void) source_object;
    ControlServer *server = data;
    if (server->stopping || g_hash_table_size(server->clients) >= MAX_CLIENTS)
        return TRUE;                /* GSocketService disposes rejected conn. */

    GError *error = NULL;
    GCredentials *credentials =
        g_socket_get_credentials(g_socket_connection_get_socket(connection),
                                 &error);
    gboolean authorized = error == NULL &&
        nurabrowser_control_peer_uid_allowed(credentials, geteuid());
    g_clear_error(&error);
    g_clear_object(&credentials);
    if (!authorized)
        return TRUE;                /* Kernel UID only, never JSON claims. */

    client_new(server, connection);
    return TRUE;
}

static gboolean check_runtime_dir(const char *dir, GError **error)
{
    if (!dir || *dir != '/') {
        g_set_error_literal(error, G_IO_ERROR, G_IO_ERROR_INVALID_ARGUMENT,
                            "XDG_RUNTIME_DIR must be an absolute path");
        return FALSE;
    }
    char *canonical = g_canonicalize_filename(dir, NULL);
    gboolean valid = g_strcmp0(dir, canonical) == 0;
    g_free(canonical);
    if (!valid) {
        g_set_error_literal(error, G_IO_ERROR, G_IO_ERROR_INVALID_ARGUMENT,
                            "XDG_RUNTIME_DIR must not contain traversal");
        return FALSE;
    }

    /* Check every component: do not follow symlinks, including ancestors. */
    char *prefix = g_strdup(dir);
    for (char *it = prefix + 1; ; it++) {
        if (*it != '/' && *it != '\0')
            continue;
        char saved = *it;
        *it = '\0';
        struct stat st;
        gboolean ok = lstat(prefix, &st) == 0 && S_ISDIR(st.st_mode);
        *it = saved;
        if (!ok) {
            g_set_error_literal(error, G_IO_ERROR, G_IO_ERROR_INVALID_ARGUMENT,
                                "XDG_RUNTIME_DIR has missing or unsafe path components");
            g_free(prefix);
            return FALSE;
        }
        if (saved == '\0')
            break;
    }
    g_free(prefix);

    struct stat st;
    if (lstat(dir, &st) != 0 || !S_ISDIR(st.st_mode) ||
        st.st_uid != geteuid() || (st.st_mode & 0777) != 0700) {
        g_set_error_literal(error, G_IO_ERROR, G_IO_ERROR_PERMISSION_DENIED,
                            "XDG_RUNTIME_DIR must be an owned 0700 directory");
        return FALSE;
    }
    return TRUE;
}

static gboolean safe_socket_path(const char *dir, const char *socket_path,
                                 char **out, GError **error)
{
    char *path = socket_path ? g_strdup(socket_path)
                             : g_build_filename(dir, CONTROL_NAME, NULL);
    char *parent = g_path_get_dirname(path);
    char *leaf = g_path_get_basename(path);
    gboolean valid = g_strcmp0(parent, dir) == 0 &&
                     leaf[0] != '\0' && strcmp(leaf, ".") != 0 &&
                     strcmp(leaf, "..") != 0 &&
                     strlen(path) < sizeof(((struct sockaddr_un *)0)->sun_path);
    for (const char *p = leaf; valid && *p; p++)
        if (!(g_ascii_isalnum(*p) || *p == '.' || *p == '_' || *p == '-'))
            valid = FALSE;

    g_free(parent);
    g_free(leaf);
    if (!valid) {
        g_set_error_literal(error, G_IO_ERROR, G_IO_ERROR_INVALID_ARGUMENT,
                            "Socket path must be a simple filename directly under XDG_RUNTIME_DIR");
        g_free(path);
        return FALSE;
    }
    *out = path;
    return TRUE;
}

static void unlink_our_socket(ControlServer *server)
{
    struct stat current;
    if (server->has_identity && lstat(server->path, &current) == 0 &&
        S_ISSOCK(current.st_mode) && current.st_uid == geteuid() &&
        current.st_dev == server->socket_dev &&
        current.st_ino == server->socket_ino)
        unlink(server->path);
}

gboolean nurabrowser_control_start(NuraBrowserContext *ctx,
                                    const char *socket_path, GError **error)
{
    g_return_val_if_fail(ctx != NULL, FALSE);
    g_return_val_if_fail(error == NULL || *error == NULL, FALSE);

    if (!servers)
        servers = g_hash_table_new(g_direct_hash, g_direct_equal);
    if (g_hash_table_contains(servers, ctx)) {
        g_set_error_literal(error, G_IO_ERROR, G_IO_ERROR_EXISTS,
                            "Control service already started for this context");
        return FALSE;
    }
    const char *dir = g_getenv("XDG_RUNTIME_DIR");
    if (!check_runtime_dir(dir, error))
        return FALSE;

    char *path = NULL;
    if (!safe_socket_path(dir, socket_path, &path, error))
        return FALSE;
    struct stat existing;
    if (lstat(path, &existing) == 0 || errno != ENOENT) {
        g_set_error_literal(error, G_IO_ERROR, G_IO_ERROR_EXISTS,
                            "Control socket path is occupied; refusing collision");
        g_free(path);
        return FALSE;
    }

    ControlServer *server = g_new0(ControlServer, 1);
    server->refs = 1;
    server->ctx = ctx;
    server->path = path;
    server->main_context = g_main_context_ref_thread_default();
    server->clients = g_hash_table_new(g_direct_hash, g_direct_equal);
    server->listener = g_socket_service_new();
    g_signal_connect(server->listener, "incoming",
                     G_CALLBACK(incoming_connection), server);

    GSocketAddress *address = g_unix_socket_address_new(path);
    gboolean bound = g_socket_listener_add_address(
        G_SOCKET_LISTENER(server->listener), address,
        G_SOCKET_TYPE_STREAM, G_SOCKET_PROTOCOL_DEFAULT, NULL, NULL, error);
    g_object_unref(address);
    if (!bound) {
        server_unref(server);
        return FALSE;
    }

    struct stat created;
    if (lstat(path, &created) == 0 && S_ISSOCK(created.st_mode) &&
        created.st_uid == geteuid()) {
        server->has_identity = TRUE;
        server->socket_dev = created.st_dev;
        server->socket_ino = created.st_ino;
    }
    if (!server->has_identity || chmod(path, 0600) != 0 ||
        lstat(path, &created) != 0 || !S_ISSOCK(created.st_mode) ||
        created.st_dev != server->socket_dev ||
        created.st_ino != server->socket_ino ||
        (created.st_mode & 0777) != 0600) {
        g_set_error_literal(error, G_IO_ERROR, G_IO_ERROR_PERMISSION_DENIED,
                            "Unable to secure control socket permissions");
        g_socket_service_stop(server->listener);
        g_socket_listener_close(G_SOCKET_LISTENER(server->listener));
        unlink_our_socket(server);
        server_unref(server);
        return FALSE;
    }
    g_hash_table_insert(servers, ctx, server);
    g_socket_service_start(server->listener);
    return TRUE;
}

void nurabrowser_control_stop(NuraBrowserContext *ctx)
{
    if (!ctx || !servers)
        return;
    ControlServer *server = g_hash_table_lookup(servers, ctx);
    if (!server)
        return;
    g_hash_table_remove(servers, ctx);
    server->stopping = TRUE;
    g_signal_handlers_disconnect_by_data(server->listener, server);
    g_socket_service_stop(server->listener);
    g_socket_listener_close(G_SOCKET_LISTENER(server->listener));

    while (g_hash_table_size(server->clients)) {
        GHashTableIter iter;
        gpointer key;
        g_hash_table_iter_init(&iter, server->clients);
        if (!g_hash_table_iter_next(&iter, &key, NULL))
            break;
        client_close(key);
    }
    unlink_our_socket(server);
    server_unref(server);
}
