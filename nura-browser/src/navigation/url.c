/* SPDX-License-Identifier: MIT */
#define _POSIX_C_SOURCE 200809L
#include "url.h"

#include <string.h>

#define NAV_URL_MAX_BYTES 8192

static gboolean
bad_url(GError **error, const char *message)
{
    g_set_error_literal(error, G_IO_ERROR, G_IO_ERROR_INVALID_ARGUMENT, message);
    return FALSE;
}

gboolean
nurabrowser_nav_normalize_url(const char *input, char **normalized, GError **error)
{
    gsize size;
    const char *authority, *authority_end;
    GUri *uri;
    char *canonical;
    const char *scheme, *host;
    gint port;

    if (normalized)
        *normalized = NULL;
    if (!normalized || !input)
        return bad_url(error, "A nonempty absolute HTTP(S) URL is required");

    /* Bound the scan, including the NUL terminator; reject embedded controls,
     * backslashes, and encoded CR/LF/NUL (common header-smuggling vectors).
     * No shell, data, file, javascript, or about scheme reaches WebKit. */
    size = strnlen(input, NAV_URL_MAX_BYTES + 1);
    if (!size || size > NAV_URL_MAX_BYTES)
        return bad_url(error, "URL is empty or exceeds 8192 bytes");
    if (!g_utf8_validate(input, size, NULL))
        return bad_url(error, "URL must be valid UTF-8");
    for (gsize i = 0; i < size; i++) {
        const unsigned char c = (unsigned char)input[i];
        if (c <= 0x20 || c == 0x7f || c == '\\')
            return bad_url(error, "URL contains forbidden whitespace or control bytes");
        if (c == '%' && i + 2 < size && input[i + 1] == '0' &&
            (input[i + 2] == '0' || input[i + 2] == 'A' ||
             input[i + 2] == 'a' || input[i + 2] == 'D' ||
             input[i + 2] == 'd'))
            return bad_url(error, "URL contains an encoded control byte");
    }

    if (!(g_ascii_strncasecmp(input, "http://", 7) == 0 ||
          g_ascii_strncasecmp(input, "https://", 8) == 0))
        return bad_url(error, "Only absolute http:// and https:// URLs are supported");

    authority = strstr(input, "://");
    if (!authority)
        return bad_url(error, "URL has no authority");
    authority += 3;
    authority_end = authority + strcspn(authority, "/?#");
    if (authority == authority_end)
        return bad_url(error, "URL host is missing");
    if (authority_end[-1] == ':')
        return bad_url(error, "URL port is empty");
    /* No userinfo, percent escapes in authority, or ambiguous @ parsing.
     * Literal IPv6 [host] is parsed by GLib; opaque authorities are rejected. */
    for (const char *p = authority; p < authority_end; p++)
        if (*p == '@' || *p == '%')
            return bad_url(error, "URL authority may not contain credentials or escapes");

    GError *parse_error = NULL;
    uri = g_uri_parse(input, G_URI_FLAGS_NONE, &parse_error);
    if (!uri) {
        g_clear_error(&parse_error);
        return bad_url(error, "URL syntax or authority is invalid");
    }
    scheme = g_uri_get_scheme(uri);
    host = g_uri_get_host(uri);
    port = g_uri_get_port(uri);
    if (!scheme ||
        (g_ascii_strcasecmp(scheme, "http") != 0 &&
         g_ascii_strcasecmp(scheme, "https") != 0) ||
        !host || !*host || g_uri_get_userinfo(uri) ||
        (port != -1 && (port < 1 || port > 65535))) {
        g_uri_unref(uri);
        return bad_url(error, "URL scheme, host, port or credentials are invalid");
    }
    /* Validate reg-name domains: GLib's parser can accept malformed host
     * text that a browser would reinterpret. IPv4/IPv6 literals are allowed. */
    if (!g_hostname_is_ip_address(host)) {
        gsize label_size = 0;
        if (strlen(host) > 253) {
            g_uri_unref(uri);
            return bad_url(error, "URL domain is too long");
        }
        for (const char *p = host; *p; p++) {
            if (!(g_ascii_isalnum(*p) || *p == '-' || *p == '.')) {
                g_uri_unref(uri);
                return bad_url(error, "URL host must be an ASCII domain or IP address");
            }
            if (*p == '.') {
                if (!label_size || p[-1] == '-') {
                    g_uri_unref(uri);
                    return bad_url(error, "URL domain label is invalid");
                }
                label_size = 0;
            } else {
                if ((!label_size && *p == '-') || ++label_size > 63) {
                    g_uri_unref(uri);
                    return bad_url(error, "URL domain label is invalid");
                }
            }
        }
        if ((label_size && host[strlen(host) - 1] == '-') ||
            (host[0] == '.')) {
            g_uri_unref(uri);
            return bad_url(error, "URL host has an invalid domain label");
        }
    }
    canonical = g_uri_to_string(uri);
    g_uri_unref(uri);
    if (!canonical || strlen(canonical) > NAV_URL_MAX_BYTES) {
        g_free(canonical);
        return bad_url(error, "Normalized URL exceeds 8192 bytes");
    }
    *normalized = canonical;
    return TRUE;
}
