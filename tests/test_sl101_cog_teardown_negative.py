"""Source-extracted negative oracle: current Cog teardown patch is NOT reentrancy-safe.

Runs two actual patched function bodies, not the prior invented State model.
ASan finding is expected and records why this candidate remains HOLD.
"""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from tests.test_sl101_cog_teardown import ROOT, SRC


def extract_c_function(text, name):
    marker = "\n" + name + "("
    start = text.index(marker)
    opening = text.index("{", start)
    depth = 0
    for index in range(opening, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                # Include declaration, omitting the preceding static void marker.
                return "static void " + text[start + 1:index + 1]
    raise AssertionError("unterminated function: " + name)


class CogTeardownNegativeOracle(unittest.TestCase):
    def test_release_reentrant_destroy_asan(self):
        cc = shutil.which("cc")
        if cc is None:
            self.skipTest("host compiler absent")
        source = (SRC / "platform/drm/cog-drm-modeset-renderer.c").read_text()
        release = extract_c_function(source, "release_buffer_exports")
        destroy = extract_c_function(source, "destroy_buffer")
        body = r"""
#include <assert.h>
#include <stdlib.h>
#include <stdint.h>
#include <stdio.h>
struct wl_resource { int marker; };
struct wpe_fdo_shm_exported_buffer { int marker; };
struct gbm_bo { int marker; };
struct wpe_view_backend_exportable_fdo { int marker; };
struct buffer_object {
    uint32_t fb_id;
    struct gbm_bo *bo;
    struct {
        struct wl_resource *resource;
        struct wpe_fdo_shm_exported_buffer *shm_buffer;
    } export;
};
typedef struct CogDrmModesetRenderer {
    struct wpe_view_backend_exportable_fdo *exportable;
} CogDrmModesetRenderer;
#define g_assert(x) assert(x)
#define g_steal_pointer(x) ({ __typeof__(*(x)) v = *(x); *(x) = NULL; v; })
#define g_free free
static struct buffer_object *tracked;
static int get_drm_fd(CogDrmModesetRenderer *self) { (void)self; return 1; }
static int drmModeRmFB(int fd, uint32_t fb) { (void)fd; (void)fb; return 0; }
static void gbm_bo_destroy(struct gbm_bo *bo) { free(bo); }
static void wpe_view_backend_exportable_fdo_dispatch_release_buffer(
  struct wpe_view_backend_exportable_fdo *exp, struct wl_resource *resource) {
    (void)exp; (void)resource;
    /* FDO may synchronously notify wl_resource destruction. The current
       destroy_buffer path then frees the same buffer before outer returns. */
    free(tracked->bo);
    tracked->bo = NULL;
    free(tracked);
    tracked = NULL;
}
static void wpe_view_backend_exportable_fdo_dispatch_release_shm_exported_buffer(
  struct wpe_view_backend_exportable_fdo *exp,
  struct wpe_fdo_shm_exported_buffer *shm) { (void)exp; (void)shm; }
"""
        main = r"""
int main(void) {
    CogDrmModesetRenderer renderer = { .exportable =
        (struct wpe_view_backend_exportable_fdo *)1 };
    tracked = calloc(1, sizeof(*tracked));
    tracked->fb_id = 42;
    tracked->bo = calloc(1, sizeof(struct gbm_bo));
    tracked->export.resource = (struct wl_resource *)1;
    destroy_buffer(&renderer, tracked);
    return 0;
}
"""
        with tempfile.TemporaryDirectory(prefix="cog-teardown-negative-") as temp:
            src = Path(temp) / "oracle.c"
            exe = Path(temp) / "oracle"
            src.write_text(body + "\n" + release + "\n" + destroy + "\n" + main)
            build = subprocess.run(
                [cc, "-std=gnu11", "-O0", "-g", "-fsanitize=address",
                 "-fno-omit-frame-pointer", "-Wall", "-Wextra",
                 str(src), "-o", str(exe)], text=True, capture_output=True)
            if build.returncode:
                self.fail("failed to compile source-extracted Cog oracle: " + build.stderr)
            env = dict(os.environ, ASAN_OPTIONS="detect_leaks=0:halt_on_error=1")
            result = subprocess.run([str(exe)], env=env, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("heap-use-after-free", result.stderr)


if __name__ == "__main__":
    unittest.main()
