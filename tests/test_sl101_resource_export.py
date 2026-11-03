"""Host-only compiled characterization of the actual Grate callback from patched Mesa source."""
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
MESA = ROOT / "build/mesa-grate-clean/mesa-25.0.7"
PATCH = ROOT / "patches/grate-resource-export/0001-grate-linear-export-fail-closed.patch"
HEADER = r"""
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#define PIPE_BUFFER 1
#define DRM_FORMAT_MOD_LINEAR 0ULL
#define DRM_FORMAT_MOD_INVALID UINT64_MAX
enum pipe_resource_param {
 PIPE_RESOURCE_PARAM_NPLANES, PIPE_RESOURCE_PARAM_STRIDE,
 PIPE_RESOURCE_PARAM_OFFSET, PIPE_RESOURCE_PARAM_LAYER_STRIDE,
 PIPE_RESOURCE_PARAM_MODIFIER, PIPE_RESOURCE_PARAM_HANDLE_TYPE_SHARED,
 PIPE_RESOURCE_PARAM_HANDLE_TYPE_KMS, PIPE_RESOURCE_PARAM_HANDLE_TYPE_FD
};
enum { WINSYS_HANDLE_TYPE_SHARED = 1, WINSYS_HANDLE_TYPE_KMS = 2, WINSYS_HANDLE_TYPE_FD = 3 };
struct pipe_screen { int unused; };
struct pipe_context { int unused; };
struct pipe_resource { unsigned target, depth0, array_size, last_level, height0, format; };
struct grate_resource {
 struct pipe_resource base; void *bo; unsigned pitch;
 unsigned tiled:1; uint64_t import_modifier; bool imported; unsigned format:5;
};
struct winsys_handle { int type; unsigned handle; unsigned stride, offset; };
static struct grate_resource *grate_resource(struct pipe_resource *r) { return (struct grate_resource *)r; }
static unsigned util_format_get_num_planes(unsigned format) { return format == 2 ? 2 : 1; }
static int fail_export = 0;
static int calls = 0;
static int drm_tegra_bo_get_name(void *bo, unsigned *h) {
 (void)bo; calls++; if(fail_export) return -1; *h=42; return 0;
}
static int drm_tegra_bo_get_handle(void *bo, unsigned *h) {
 (void)bo; calls++; if(fail_export) return -1; *h=43; return 0;
}
static int drm_tegra_bo_to_dmabuf(void *bo, unsigned *h) {
 (void)bo; calls++; if(fail_export) return -1; *h=17; return 0;
}
"""
MAIN = r"""
int main(void) {
 struct grate_resource r = {0};
 uint64_t v = 999;
 r.bo=&r; r.pitch=64; r.base.height0=8;
 r.base.depth0=1; r.base.array_size=1;
 assert(grate_resource_get_param(0,0,&r.base,0,0,0,PIPE_RESOURCE_PARAM_MODIFIER,0,&v) && v==DRM_FORMAT_MOD_LINEAR);
 assert(grate_resource_get_param(0,0,&r.base,0,0,0,PIPE_RESOURCE_PARAM_LAYER_STRIDE,0,&v) && v==512);
 r.pitch=UINT32_MAX; r.base.height0=UINT32_MAX;
 assert(grate_resource_get_param(0,0,&r.base,0,0,0,PIPE_RESOURCE_PARAM_LAYER_STRIDE,0,&v));
 assert(v==(uint64_t)UINT32_MAX*UINT32_MAX);
 r.pitch=64; r.base.height0=8;
 r.tiled=1; v=999;
 assert(!grate_resource_get_param(0,0,&r.base,0,0,0,PIPE_RESOURCE_PARAM_MODIFIER,0,&v) && v==999);
 r.tiled=0; r.imported=true; r.import_modifier=DRM_FORMAT_MOD_INVALID;
 assert(!grate_resource_get_param(0,0,&r.base,0,0,0,PIPE_RESOURCE_PARAM_MODIFIER,0,&v) && v==999);
 r.import_modifier=DRM_FORMAT_MOD_LINEAR;
 assert(grate_resource_get_param(0,0,&r.base,0,0,0,PIPE_RESOURCE_PARAM_MODIFIER,0,&v) && v==0);
 int old_calls=calls; fail_export=1; v=999;
 assert(!grate_resource_get_param(0,0,&r.base,0,0,0,PIPE_RESOURCE_PARAM_HANDLE_TYPE_FD,0,&v) && v==999);
 assert(calls==old_calls+1);
 fail_export=0;
 assert(grate_resource_get_param(0,0,&r.base,0,0,0,PIPE_RESOURCE_PARAM_HANDLE_TYPE_FD,0,&v) && v==17);
 assert(grate_resource_get_param(0,0,&r.base,0,0,0,PIPE_RESOURCE_PARAM_HANDLE_TYPE_SHARED,0,&v) && v==42);
 assert(!grate_resource_get_param(0,0,&r.base,1,0,0,PIPE_RESOURCE_PARAM_STRIDE,0,&v));
 assert(!grate_resource_get_param(0,0,&r.base,0,1,0,PIPE_RESOURCE_PARAM_STRIDE,0,&v));
 assert(!grate_resource_get_param(0,0,&r.base,0,0,1,PIPE_RESOURCE_PARAM_STRIDE,0,&v));
 r.base.format=2;
 assert(!grate_resource_get_param(0,0,&r.base,0,0,0,PIPE_RESOURCE_PARAM_NPLANES,0,&v));
 r.base.format=1; r.base.target=PIPE_BUFFER;
 assert(!grate_resource_get_param(0,0,&r.base,0,0,0,PIPE_RESOURCE_PARAM_MODIFIER,0,&v));
 r.base.target=0; r.base.array_size=2;
 assert(!grate_resource_get_param(0,0,&r.base,0,0,0,PIPE_RESOURCE_PARAM_LAYER_STRIDE,0,&v));
 puts("compiled callback assertions pass");
 return 0;
}
"""


class TestResourceExport(unittest.TestCase):
    def test_strict_replay_and_compiled_callback(self):
        with tempfile.TemporaryDirectory() as td:
            td = pathlib.Path(td)
            src = MESA / "src/gallium/drivers/grate"
            for name in ("grate_resource.c", "grate_resource.h"):
                dest = td / "src/gallium/drivers/grate" / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes((src / name).read_bytes())
            subprocess.run(["patch", "--batch", "--fuzz=0", "-p1", "-i", str(PATCH)],
                           cwd=td, check=True, capture_output=True, text=True)
            text = (td / "src/gallium/drivers/grate/grate_resource.c").read_text()
            start = text.index("static bool\ngrate_resource_get_handle(")
            end = text.index("\nstatic void\ngrate_resource_destroy", start)
            test = td / "callback_test.c"
            test.write_text(HEADER + text[start:end] + MAIN)
            subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                            "-UNDEBUG", str(test), "-o", str(td / "callback_test")],
                           check=True, capture_output=True, text=True)
            subprocess.run([str(td / "callback_test")], check=True,
                           capture_output=True, text=True)
            subprocess.run(["patch", "--batch", "--fuzz=0", "-R", "-p1", "-i", str(PATCH)],
                           cwd=td, check=True, capture_output=True, text=True)
            for name in ("grate_resource.c", "grate_resource.h"):
                self.assertEqual((td / "src/gallium/drivers/grate" / name).read_bytes(),
                                 (src / name).read_bytes())


if __name__ == "__main__":
    unittest.main()
