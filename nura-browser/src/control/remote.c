/* SPDX-License-Identifier: MIT
 * Bounded, same-UID control client for NuraBrowser's private JSONL socket.
 * This is NOT a web API, remote TCP interface, or DOM bridge.
 */
#define _POSIX_C_SOURCE 200809L
#include "remote.h"

#include <gio/gio.h>
#include <gio/gunixsocketaddress.h>
#include <glib/gstdio.h>
#include <json-glib/json-glib.h>

#include <errno.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/un.h>
#include <unistd.h>

#define REMOTE_MAX_FRAME 8192
#define REMOTE_MAX_URL 4096
#define REMOTE_TIMEOUT_SECONDS 2

static gboolean
private_runtime_dir(const char *dir)
{
    if (!dir || *dir != '/')
        return FALSE;
    g_autofree char *canonical = g_canonicalize_filename(dir, NULL);
    if (g_strcmp0(dir, canonical) != 0)
        return FALSE;

    /* Reject symlink components, including the ancestors of the 0700 dir. */
    g_autofree char *prefix = g_strdup(dir);
    for (char *it = prefix + 1; ; it++) {
        if (*it != '/' && *it != '\0')
            continue;
        char saved = *it;
        *it = '\0';
        struct stat st;
        gboolean safe = g_lstat(prefix, &st) == 0 && S_ISDIR(st.st_mode);
        *it = saved;
        if (!safe)
            return FALSE;
        if (saved == '\0')
            break;
    }
    struct stat st;
    return g_lstat(dir, &st) == 0 &&
           S_ISDIR(st.st_mode) && st.st_uid == geteuid() &&
           (st.st_mode & 0777) == 0700;
}

static gboolean
allowed_command(const char *command, const char *argument)
{
    if (g_strcmp0(command, "open") == 0) {
        if (!argument)
            return FALSE;
        gsize bytes = strnlen(argument, REMOTE_MAX_URL + 1);
        if (bytes == 0 || bytes > REMOTE_MAX_URL ||
            !g_utf8_validate(argument, bytes, NULL))
            return FALSE;
        /* WebKit's navigation lane additionally checks scheme, authority,
         * credentials and encoded controls. Reject raw controls early. */
        for (gsize i = 0; i < bytes; i++) {
            if ((unsigned char)argument[i] < 0x20 ||
                (unsigned char)argument[i] == 0x7f)
                return FALSE;
        }
        return TRUE;
    }
    return argument == NULL &&
        (g_strcmp0(command, "back") == 0 ||
         g_strcmp0(command, "forward") == 0 ||
         g_strcmp0(command, "reload") == 0 ||
         g_strcmp0(command, "stop") == 0 ||
         g_strcmp0(command, "uri") == 0);
}

static char *
request_line(const char *command, const char *argument)
{
    g_autoptr(JsonBuilder) builder = json_builder_new();
    json_builder_begin_object(builder);
    json_builder_set_member_name(builder, "command");
    json_builder_add_string_value(builder, command);
    if (argument) {
        json_builder_set_member_name(builder, "argument");
        json_builder_add_string_value(builder, argument);
    }
    json_builder_end_object(builder);
    g_autoptr(JsonNode) node = json_builder_get_root(builder);
    g_autoptr(JsonGenerator) generator = json_generator_new();
    json_generator_set_root(generator, node);
    g_autofree char *json = json_generator_to_data(generator, NULL);
    return g_strconcat(json, "\n", NULL);
}

/* Only a single bounded reply is accepted. No GDataInputStream read_line()
 * which could allocate an unbounded buffer from a malfunctioning peer. */
static gboolean
read_bounded_line(GSocket *socket, GString **out, GError **error)
{
    g_autoptr(GString) line = g_string_sized_new(256);
    char bytes[1024];
    while (line->len < REMOTE_MAX_FRAME) {
        gssize count = g_socket_receive(socket, bytes, sizeof(bytes), NULL, error);
        if (count <= 0) {
            if (count == 0)
                g_set_error_literal(error, G_IO_ERROR, G_IO_ERROR_PARTIAL_INPUT,
                                    "Browser control reply closed before newline");
            return FALSE;
        }
        for (gssize i = 0; i < count; i++) {
            if (bytes[i] == '\0') {
                g_set_error_literal(error, G_IO_ERROR, G_IO_ERROR_INVALID_DATA,
                                    "NUL byte in browser control reply");
                return FALSE;
            }
            if (bytes[i] == '\n') {
                if (i + 1 != count) {
                    g_set_error_literal(error, G_IO_ERROR, G_IO_ERROR_INVALID_DATA,
                                        "Multiple browser control replies");
                    return FALSE;
                }
                *out = g_steal_pointer(&line);
                return TRUE;
            }
            if (line->len + 1 >= REMOTE_MAX_FRAME) {
                g_set_error_literal(error, G_IO_ERROR, G_IO_ERROR_NO_SPACE,
                                    "Browser control reply exceeds limit");
                return FALSE;
            }
            g_string_append_c(line, bytes[i]);
        }
    }
    return FALSE;
}

int
nurabrowser_remote_main(int argc, char **argv)
{
    if (argc < 1 || argc > 2 ||
        !allowed_command(argv[0], argc == 2 ? argv[1] : NULL)) {
        g_printerr("nura-browser: --remote requires back|forward|reload|stop|uri "
                   "or open HTTP(S)-URL\n");
        return 2;
    }
    const char *dir = g_getenv("XDG_RUNTIME_DIR");
    if (!private_runtime_dir(dir)) {
        g_printerr("nura-browser: unsafe XDG_RUNTIME_DIR (expected owned 0700, no symlinks)\n");
        return 1;
    }
    g_autofree char *socket_path = g_build_filename(dir, "nura-browser.sock", NULL);
    if (strlen(socket_path) >= sizeof(((struct sockaddr_un *)0)->sun_path)) {
        g_printerr("nura-browser: control socket path too long\n");
        return 1;
    }
    struct stat st;
    if (g_lstat(socket_path, &st) != 0 || !S_ISSOCK(st.st_mode) ||
        st.st_uid != geteuid() || (st.st_mode & 0777) != 0600) {
        g_printerr("nura-browser: private control socket unavailable or unsafe\n");
        return 1;
    }
    g_autoptr(GSocketClient) client = g_socket_client_new();
    g_socket_client_set_timeout(client, REMOTE_TIMEOUT_SECONDS);
    g_autoptr(GSocketConnectable) address =
        G_SOCKET_CONNECTABLE(g_unix_socket_address_new(socket_path));
    g_autoptr(GError) error = NULL;
    g_autoptr(GSocketConnection) conn =
        g_socket_client_connect(client, address, NULL, &error);
    if (!conn) {
        g_printerr("nura-browser: cannot connect to browser control socket\n");
        return 1;
    }
    GSocket *socket = g_socket_connection_get_socket(conn);
    g_socket_set_timeout(socket, REMOTE_TIMEOUT_SECONDS);
    g_autoptr(GCredentials) credentials = g_socket_get_credentials(socket, &error);
    if (!credentials || g_credentials_get_unix_user(credentials, &error) != geteuid() ||
        error) {
        g_printerr("nura-browser: browser control peer UID mismatch\n");
        return 1;
    }
    g_autofree char *request = request_line(argv[0], argc == 2 ? argv[1] : NULL);
    gsize len = strlen(request);
    if (len >= REMOTE_MAX_FRAME) {
        g_printerr("nura-browser: browser control request exceeds limit\n");
        return 1;
    }
    gsize written = 0;
    if (!g_output_stream_write_all(
            g_io_stream_get_output_stream(G_IO_STREAM(conn)),
            request, len, &written, NULL, &error) || written != len) {
        g_printerr("nura-browser: browser control write failed\n");
        return 1;
    }
    GString *line = NULL;
    if (!read_bounded_line(socket, &line, &error)) {
        g_printerr("nura-browser: browser control reply missing or malformed\n");
        return 1;
    }
    g_autoptr(GString) owned_line = line;
    g_autoptr(JsonParser) parser = json_parser_new();
    if (!g_utf8_validate(line->str, line->len, NULL) ||
        !json_parser_load_from_data(parser, line->str, (gssize)line->len, &error) ||
        !JSON_NODE_HOLDS_OBJECT(json_parser_get_root(parser))) {
        g_printerr("nura-browser: browser control reply is not a JSON object\n");
        return 1;
    }
    JsonObject *object = json_node_get_object(json_parser_get_root(parser));
    JsonNode *ok = json_object_get_member(object, "ok");
    if (!ok || !JSON_NODE_HOLDS_VALUE(ok) ||
        json_node_get_value_type(ok) != G_TYPE_BOOLEAN) {
        g_printerr("nura-browser: browser control reply missing status\n");
        return 1;
    }
    if (!json_node_get_boolean(ok)) {
        g_printerr("nura-browser: browser rejected navigation request\n");
        return 1;
    }
    if (!json_object_has_member(object, "result")) {
        g_printerr("nura-browser: browser control reply missing result\n");
        return 1;
    }
    /* stdout is JSON, intended for a future native NuraLoumi surface.
     * Never pass any of these values to a shell or interpreter. */
    g_print("%s\n", line->str);
    return 0;
}
