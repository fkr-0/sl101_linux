/* SPDX-License-Identifier: MIT
 * ARMHF *runtime* probes against the prepared Debian 2.54.0-2 toolchain.
 * Does NOT qualify WebKit render, child processes, JIT or media playback.
 */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <math.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include <sys/auxv.h>

static volatile double x = 1.2345678, y = 0.7654321, z = 0.00000001;
static volatile float xf = 1.234567f, yf = 0.765432f, zf = 0.000001f;

typedef const char *(*CheckVersion)(const char *);
typedef void (*HashBuffer)(int, void *, const void *, size_t);
typedef const char *(*Rav1eVersion)(void);

int
main(void)
{
    unsigned long hwcap = getauxval(AT_HWCAP);
    printf("HWCAP=0x%08lx NEON=%d\n", hwcap,
           !!(hwcap & HWCAP_ARM_NEON));
    fflush(stdout);
    if (hwcap & HWCAP_ARM_NEON)
        return 10; /* A passing test MUST be on a no-NEON guest. */

    double result[] = {sin(x), cos(x), tan(x), exp(x), log(x),
                       pow(x, y), atan2(x, y), hypot(x, y),
                       erf(x), fma(x, y, z), fmaf(xf, yf, zf)};
    for (size_t i = 0; i < sizeof(result) / sizeof(result[0]); i++) {
        if (!isfinite(result[i]))
            return 11;
    }
    puts("LIBM=PASS sin cos tan exp log pow atan2 hypot erf fma fmaf");
    fflush(stdout);

    const char *libraries[] = {
        "libjpeg.so.62", "libgcrypt.so.20", "libwebp.so.7",
        "libsharpyuv.so.0", "librav1e.so.0.8",
    };
    for (size_t i = 0; i < sizeof(libraries) / sizeof(libraries[0]); i++) {
        void *handle = dlopen(libraries[i], RTLD_NOW | RTLD_LOCAL);
        if (!handle) {
            fprintf(stderr, "DLOPEN_FAIL %s %s\n", libraries[i], dlerror());
            return 12;
        }
        printf("DLOPEN_OK %s\n", libraries[i]);
        fflush(stdout);
        if (strcmp(libraries[i], "libgcrypt.so.20") == 0) {
            CheckVersion check = (CheckVersion)dlsym(handle, "gcry_check_version");
            HashBuffer hash = (HashBuffer)dlsym(handle, "gcry_md_hash_buffer");
            if (!check || !hash || !check(NULL))
                return 13;
            unsigned char digest[32] = {0};
            hash(8, digest, "abc", 3); /* GCRY_MD_SHA256 is 8. */
            const unsigned char expected[32] = {
                0xba,0x78,0x16,0xbf,0x8f,0x01,0xcf,0xea,
                0x41,0x41,0x40,0xde,0x5d,0xae,0x22,0x23,
                0xb0,0x03,0x61,0xa3,0x96,0x17,0x7a,0x9c,
                0xb4,0x10,0xff,0x61,0xf2,0x00,0x15,0xad
            };
            if (memcmp(digest, expected, sizeof(expected)) != 0)
                return 14;
            puts("GCRYPT_SHA256=PASS");
        }
        if (strcmp(libraries[i], "librav1e.so.0.8") == 0) {
            Rav1eVersion version = (Rav1eVersion)dlsym(handle,
                                                      "rav1e_version_full");
            if (!version || !version())
                return 15;
            printf("RAV1E_VERSION=%s\n", version());
        }
        fflush(stdout);
        dlclose(handle);
    }
    puts("TEGRA2_NO_NEON_QEMU_PROBE=PASS");
    return 0;
}
