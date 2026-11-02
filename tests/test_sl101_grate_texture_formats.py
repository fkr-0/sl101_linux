"""CPU-only validation of Tegra20 native sampler formats (no device mutation)."""

from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "patches/mesa-25.0.7/0004-grate-single-channel-sampler-formats.patch"
BASE = ROOT / "work/sl101-grate-production-20261004/grate-src"
FILES = ("grate_state.c", "grate_screen.c", "grate_resource.c")
PREFIX = Path("src/gallium/drivers/grate")


def extract(source, start, end):
    begin = source.index(start)
    return source[begin:source.index(end, begin)]


class GrateTextureFormatTests(unittest.TestCase):
    def test_patch_is_per_file_and_keeps_pitch_contract(self):
        patch = PATCH.read_text()
        for name in FILES:
            self.assertIn(f"diff --git a/{PREFIX}/{name} b/{PREFIX}/{name}", patch)
        self.assertIn("case PIPE_FORMAT_A8_UNORM:", patch)
        self.assertIn("case PIPE_FORMAT_L8_UNORM:", patch)
        self.assertIn("case PIPE_FORMAT_L8A8_UNORM:", patch)
        self.assertIn("PIPE_BIND_SCANOUT", patch)
        self.assertIn("PIPE_SWIZZLE_0", patch)
        self.assertNotIn("resource->pitch = align(resource->pitch, 64)", patch)

    def test_patch_compiles_and_rejects_unsupported_swizzles_and_uses(self):
        if not BASE.is_dir():
            self.skipTest("local Mesa production source not available")
        cc = shutil.which("cc")
        patcher = shutil.which("patch")
        if not cc or not patcher:
            self.skipTest("C compiler or patch utility unavailable")

        with tempfile.TemporaryDirectory(prefix="sl101-grate-textures-") as temp:
            temp = Path(temp)
            dst = temp / PREFIX
            dst.mkdir(parents=True)
            for name in FILES:
                shutil.copyfile(BASE / name, dst / name)
            subprocess.run([patcher, "-s", "-p1", "-i", str(PATCH)],
                           cwd=temp, check=True, capture_output=True, text=True)

            state = (dst / "grate_state.c").read_text()
            screen = (dst / "grate_screen.c").read_text()
            resource = (dst / "grate_resource.c").read_text()

            self.assertIn("resource->pitch = align(resource->pitch, 16);", resource)
            self.assertIn("resource->pitch != align(texture->width0 * blocksize, 16)", state)

            # Compile the three real driver functions in a tiny C harness,
            # avoiding a full ARM cross-build and any live GPU/device access.
            source = r'''
#include <stdbool.h>
#include <assert.h>
enum pipe_format {
    PIPE_FORMAT_A8_UNORM, PIPE_FORMAT_L8_UNORM, PIPE_FORMAT_L8A8_UNORM,
    PIPE_FORMAT_B5G6R5_UNORM, PIPE_FORMAT_B5G5R5A1_UNORM,
    PIPE_FORMAT_B4G4R4A4_UNORM, PIPE_FORMAT_R8G8B8A8_UNORM,
    PIPE_FORMAT_B8G8R8A8_UNORM, PIPE_FORMAT_B8G8R8X8_UNORM,
    PIPE_FORMAT_R32G32B32A32_FLOAT, PIPE_FORMAT_S8_UINT,
    PIPE_FORMAT_Z16_UNORM, PIPE_FORMAT_UNKNOWN
};
enum pipe_texture_target { PIPE_TEXTURE_2D, PIPE_TEXTURE_1D };
struct pipe_screen { int unused; };
#define PIPE_SWIZZLE_X 0
#define PIPE_SWIZZLE_Y 1
#define PIPE_SWIZZLE_Z 2
#define PIPE_SWIZZLE_W 3
#define PIPE_SWIZZLE_0 4
#define PIPE_SWIZZLE_1 5
#define PIPE_BIND_SAMPLER_VIEW 1
#define PIPE_BIND_RENDER_TARGET 2
#define PIPE_BIND_DEPTH_STENCIL 4
#define PIPE_BIND_SCANOUT 8
#define TGR3D_PIXEL_FORMAT_A8 1
#define TGR3D_PIXEL_FORMAT_L8 2
#define TGR3D_PIXEL_FORMAT_LA88 4
#define TGR3D_PIXEL_FORMAT_RGB565 6
#define TGR3D_PIXEL_FORMAT_RGBA5551 9
#define TGR3D_PIXEL_FORMAT_RGBA4444 10
#define TGR3D_PIXEL_FORMAT_BGRA8888 14
#define TGR3D_PIXEL_FORMAT_RGBA_FP32 18
#define TGR3D_PIXEL_FORMAT_S8 3
#define TGR3D_PIXEL_FORMAT_D16_LINEAR 11
'''
            source += extract(resource, "int\ngrate_pixel_format(",
                              "static struct pipe_resource *\ngrate_screen_resource_create")
            source += extract(state, "static bool\ngrate_sampler_view_format_supported(",
                              "static struct pipe_sampler_view *\ngrate_create_sampler_view")
            source += extract(screen, "static bool\ngrate_screen_is_format_supported(",
                              "struct pipe_fence_handle *\ngrate_fence_create")
            source += r'''
int main(void) {
    const struct {
        enum pipe_format format;
        unsigned r, g, b, a;
        int hw_format;
        unsigned bytes_per_pixel;
    } formats[] = {
        {PIPE_FORMAT_A8_UNORM, PIPE_SWIZZLE_0, PIPE_SWIZZLE_0,
         PIPE_SWIZZLE_0, PIPE_SWIZZLE_X, TGR3D_PIXEL_FORMAT_A8, 1},
        {PIPE_FORMAT_L8_UNORM, PIPE_SWIZZLE_X, PIPE_SWIZZLE_X,
         PIPE_SWIZZLE_X, PIPE_SWIZZLE_1, TGR3D_PIXEL_FORMAT_L8, 1},
        {PIPE_FORMAT_L8A8_UNORM, PIPE_SWIZZLE_X, PIPE_SWIZZLE_X,
         PIPE_SWIZZLE_X, PIPE_SWIZZLE_Y, TGR3D_PIXEL_FORMAT_LA88, 2},
    };
    for (unsigned i = 0; i < sizeof(formats) / sizeof(formats[0]); i++) {
        enum pipe_format fmt = formats[i].format;
        assert(grate_sampler_view_format_supported(fmt));
        assert(grate_pixel_format(fmt) == formats[i].hw_format);
        assert(grate_check_sampler_swizzle(fmt, formats[i].r, formats[i].g,
                                          formats[i].b, formats[i].a));
        assert(!grate_check_sampler_swizzle(fmt, formats[i].r, formats[i].g,
                                           formats[i].b, PIPE_SWIZZLE_Z));
        assert(grate_screen_is_format_supported(0, fmt, PIPE_TEXTURE_2D, 1, 1,
                                                PIPE_BIND_SAMPLER_VIEW));
        assert(!grate_screen_is_format_supported(0, fmt, PIPE_TEXTURE_1D, 1, 1,
                                                 PIPE_BIND_SAMPLER_VIEW));
        assert(!grate_screen_is_format_supported(0, fmt, PIPE_TEXTURE_2D, 2, 2,
                                                 PIPE_BIND_SAMPLER_VIEW));
        assert(!grate_screen_is_format_supported(0, fmt, PIPE_TEXTURE_2D, 1, 1,
                                                 PIPE_BIND_RENDER_TARGET));
        assert(!grate_screen_is_format_supported(0, fmt, PIPE_TEXTURE_2D, 1, 1,
                                                 PIPE_BIND_DEPTH_STENCIL));
        assert(!grate_screen_is_format_supported(0, fmt, PIPE_TEXTURE_2D, 1, 1,
                                                 PIPE_BIND_SCANOUT));
        assert(!grate_screen_is_format_supported(0, fmt, PIPE_TEXTURE_2D, 1, 1,
                                PIPE_BIND_SAMPLER_VIEW | PIPE_BIND_RENDER_TARGET));
        for (unsigned width = 1; width <= 65; width++) {
            unsigned stride = (width * formats[i].bytes_per_pixel + 15u) & ~15u;
            assert(stride % 16u == 0);
            assert(stride >= width * formats[i].bytes_per_pixel);
            assert(stride - width * formats[i].bytes_per_pixel < 16u);
        }
    }
    assert(!grate_sampler_view_format_supported(PIPE_FORMAT_UNKNOWN));
    assert(!grate_check_sampler_swizzle(PIPE_FORMAT_UNKNOWN, 0, 0, 0, 0));
    assert(grate_check_sampler_swizzle(PIPE_FORMAT_R8G8B8A8_UNORM,
           PIPE_SWIZZLE_X, PIPE_SWIZZLE_Y, PIPE_SWIZZLE_Z, PIPE_SWIZZLE_W));
    assert(grate_check_sampler_swizzle(PIPE_FORMAT_B8G8R8X8_UNORM,
           PIPE_SWIZZLE_X, PIPE_SWIZZLE_Y, PIPE_SWIZZLE_Z, PIPE_SWIZZLE_1));
    return 0;
}
'''
            harness = temp / "validate.c"
            executable = temp / "validate"
            harness.write_text(source)
            subprocess.run([cc, "-std=c11", "-Wall", "-Wextra", "-Werror",
                            "-Wno-unused-parameter", str(harness),
                            "-o", str(executable)], check=True,
                           capture_output=True, text=True)
            subprocess.run([str(executable)], check=True, capture_output=True)


if __name__ == "__main__":
    unittest.main()
