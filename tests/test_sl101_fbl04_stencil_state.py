"""Host-only compiled register/dispatch oracle for FBL04 stencil candidate.

The source is copied into temporary storage; both patches use zero fuzz.
This does NOT qualify device pixels, CSS clipping, or undocumented partial masks.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
DRIVER = Path("src/gallium/drivers/grate")
SOURCE = ROOT / "build/mesa-grate-clean/mesa-25.0.7" / DRIVER
PATCH32 = ROOT / "patches/mesa-25.0.7/0032-grate-stencil-state-readonly.patch"
PATCH38 = ROOT / "patches/mesa-25.0.7/0038-grate-stencil-state-fbl04.patch"
UPSTREAM = (
    (Path("/tmp/sl101-upstream-grate-3d.c"),
     "d1deb368df39c908babcd1c378b3a3aeeedafe443602420ce05f8e13c9207a31"),
    (Path("/tmp/sl101-upstream-grate-stencil.c"),
     "9a2db9cc0b430c8c05f34a67271f2472655a48cd3f2f8c42a9cb487e1813be71"),
)


def apply_patch(directory: Path, patch_file: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["patch", "--batch", "--fuzz=0", "-p1", "-i", str(patch_file)],
        cwd=directory, text=True, capture_output=True,
    )


class StencilCandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not all((SOURCE / n).is_file()
                   for n in ("grate_state.c", "grate_draw.c", "grate_state.h", "tgr_3d.xml.h")):
            raise unittest.SkipTest("exact local Mesa source snapshot unavailable")
        if not shutil.which("patch"):
            raise unittest.SkipTest("patch utility unavailable")
        cls.temp = tempfile.TemporaryDirectory(prefix="sl101-fbl04-")
        cls.root = Path(cls.temp.name)
        cls.driver = cls.root / DRIVER
        cls.driver.mkdir(parents=True)
        cls.pristine = {}
        for name in ("grate_state.c", "grate_draw.c", "grate_state.h"):
            cls.pristine[name] = (SOURCE / name).read_bytes()
            (cls.driver / name).write_bytes(cls.pristine[name])
        first = apply_patch(cls.root, PATCH32)
        if first.returncode:
            raise AssertionError("0032 base replay: " + first.stdout + first.stderr)
        cls.previous = (cls.driver / "grate_state.c").read_bytes()
        second = apply_patch(cls.root, PATCH38)
        if second.returncode:
            raise AssertionError("0038 candidate replay: " + second.stdout + second.stderr)
        cls.state = (cls.driver / "grate_state.c").read_text()
        cls.draw = (cls.driver / "grate_draw.c").read_text()

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "temp"):
            cls.temp.cleanup()

    def test_pinned_upstream_hashes_and_sequences(self):
        for path, digest in UPSTREAM:
            if not path.is_file():
                self.skipTest(f"pinned upstream cache missing: {path}")
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest)
        upstream = UPSTREAM[0][0].read_text()
        emitter = upstream.split("static void grate_3d_set_stencil_test(", 1)[1].split(
            "\nstatic void grate_3d_set_vp_attributes_in_out_mask(", 1)[0]
        self.assertIn("HOST1X_OPCODE_INCR(TGR3D_STENCIL_FRONT1, 3)", emitter)
        self.assertIn("HOST1X_OPCODE_INCR(TGR3D_STENCIL_FRONT2, 2)", emitter)
        self.assertIn("value |= 0x8;", emitter)
        self.assertEqual(emitter.count("value |= 0x1fe00;"), 2)
        checks = UPSTREAM[1][0].read_text()
        for expected in ("CHECK(indices_bo, 0x55)", "CHECK(indices_bo, 0x11)",
                         "GRATE_3D_CTX_STENCIL_OP_ZERO",
                         "GRATE_3D_CTX_STENCIL_OP_REPLACE"):
            self.assertIn(expected, checks)

    def test_exact_reverse_and_negative_current_source_replay(self):
        reverse = subprocess.run(
            ["patch", "--batch", "--fuzz=0", "-p1", "-R", "-i", str(PATCH38)],
            cwd=self.root, text=True, capture_output=True,
        )
        self.assertEqual(reverse.returncode, 0, reverse.stdout + reverse.stderr)
        self.assertEqual((self.driver / "grate_state.c").read_bytes(), self.previous)
        forward = apply_patch(self.root, PATCH38)
        self.assertEqual(forward.returncode, 0, forward.stdout + forward.stderr)
        self.assertEqual((self.driver / "grate_state.c").read_text(), self.state)
        with tempfile.TemporaryDirectory(prefix="sl101-fbl04-negative-") as tmp:
            scratch = Path(tmp)
            source = scratch / DRIVER
            source.mkdir(parents=True)
            (source / "grate_state.c").write_bytes(self.pristine["grate_state.c"])
            failure = apply_patch(scratch, PATCH38)
            self.assertNotEqual(failure.returncode, 0,
                                "0038 must not silently apply without 0032")

    def test_dispatch_guard_precedes_submission(self):
        body = self.draw.split("static void\ngrate_draw_vbo(", 1)[1]
        guard = body.index("!grate_stencil_draw_supported(grate_context(pcontext))")
        self.assertLess(guard, body.index("for (unsigned i = 0; i < num_draws"))
        self.assertLess(guard, body.index("grate_draw_vbo_single("))

    def test_compiled_full_width_reference_and_dispatch(self):
        cc = shutil.which("cc") or shutil.which("gcc")
        if not cc:
            self.skipTest("C compiler unavailable")
        source = self.state
        compare = "static int\ngrate_compare_func(" + source.split(
            "static int\ngrate_compare_func(", 1)[1].split(
            "\n/* The XML describes", 1)[0]
        gate = "static bool\ngrate_stencil_keep_only(" + source.split(
            "static bool\ngrate_stencil_keep_only(", 1)[1].split(
            "\nstatic void *\ngrate_create_zsa_state(", 1)[0]
        encode = "static uint32_t\ngrate_stencil_compare(" + source.split(
            "static uint32_t\ngrate_stencil_compare(", 1)[1].split(
            "\nstatic void\nemit_zsa_state(", 1)[0]
        emit = "static void\nemit_zsa_state(" + source.split(
            "static void\nemit_zsa_state(", 1)[1].split(
            "\nstatic void\nemit_vs_uniforms(", 1)[0]
        preamble = r"""
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include "tgr_3d.xml.h"
#define TGR3D_VAL(reg, field, value) \
  (((uint32_t)(value) << TGR3D_ ## reg ## _ ## field ## __SHIFT) & \
    TGR3D_ ## reg ## _ ## field ## __MASK)
#define unreachable(x) __builtin_unreachable()
enum pipe_compare_func {
 PIPE_FUNC_NEVER, PIPE_FUNC_LESS, PIPE_FUNC_EQUAL, PIPE_FUNC_LEQUAL,
 PIPE_FUNC_GREATER, PIPE_FUNC_NOTEQUAL, PIPE_FUNC_GEQUAL, PIPE_FUNC_ALWAYS
};
enum pipe_stencil_op {
 PIPE_STENCIL_OP_KEEP, PIPE_STENCIL_OP_ZERO, PIPE_STENCIL_OP_REPLACE,
 PIPE_STENCIL_OP_INCR, PIPE_STENCIL_OP_DECR, PIPE_STENCIL_OP_INCR_WRAP,
 PIPE_STENCIL_OP_DECR_WRAP, PIPE_STENCIL_OP_INVERT
};
enum pipe_format { PIPE_FORMAT_OTHER, PIPE_FORMAT_Z16_UNORM, PIPE_FORMAT_S8_UINT };
struct pipe_stencil_state {
 unsigned enabled;
 enum pipe_compare_func func;
 enum pipe_stencil_op fail_op, zfail_op, zpass_op;
 unsigned valuemask, writemask;
};
struct pipe_resource { enum pipe_format format; };
struct pipe_surface { struct pipe_resource *texture; };
struct grate_zsa_state {
 struct {struct pipe_stencil_state stencil[2];} base;
 uint32_t commands[2];
 bool stencil_unsupported;
};
struct grate_stream { uint32_t words[32]; unsigned count; };
struct grate_channel { struct grate_stream stream; };
struct grate_context {
 struct {struct {struct pipe_surface *zsbuf;} base;} framebuffer;
 struct grate_zsa_state *zsa;
 struct {unsigned ref_value[2];} stencil_ref;
 struct grate_channel *gr3d;
};
static uint32_t host1x_opcode_incr(unsigned offset, unsigned count) {
 return 0x10000000u | (offset << 16) | count;
}
static void grate_stream_push(struct grate_stream *s, uint32_t v) {
 s->words[s->count++] = v;
}
static void grate_stream_push_words(struct grate_stream *s,
 const uint32_t *p, unsigned n, unsigned unused) {
 (void)unused;
 for (unsigned i=0;i<n;++i) grate_stream_push(s,p[i]);
}
"""
        checks = r"""
#define REQUIRE(x) do {if (!(x)) { fprintf(stderr,"failed line %d: %s\n",__LINE__,#x); return __LINE__; }} while (0)
int main(void) {
 struct pipe_stencil_state s = {
   .enabled=1, .func=PIPE_FUNC_EQUAL, .fail_op=PIPE_STENCIL_OP_KEEP,
   .zfail_op=PIPE_STENCIL_OP_KEEP, .zpass_op=PIPE_STENCIL_OP_REPLACE,
   .valuemask=0x5a, .writemask=0xff };
 struct grate_zsa_state z = {0};
 struct grate_channel channel = {0};
 struct pipe_resource resource = {.format=PIPE_FORMAT_S8_UINT};
 struct pipe_surface surface = {.texture=&resource};
 struct grate_context ctx = {
  .framebuffer.base.zsbuf=&surface, .zsa=&z, .gr3d=&channel,
  .stencil_ref.ref_value={0x55,0x11}
 };
 z.base.stencil[0]=s; z.base.stencil[1]=s;
 z.base.stencil[1].func=PIPE_FUNC_GEQUAL;
 z.base.stencil[1].valuemask=0x3c;
 z.commands[0]=0x123; z.commands[1]=0x456;
 REQUIRE(grate_stencil_state_supported(&s));
 s.writemask=0x7f;
 REQUIRE(!grate_stencil_state_supported(&s)); /* partial write fails closed */
 s.writemask=0xff;
 s.zpass_op=PIPE_STENCIL_OP_INVERT;
 REQUIRE(!grate_stencil_state_supported(&s)); /* unsupported op */
 s.zpass_op=PIPE_STENCIL_OP_REPLACE;
 s.func=(enum pipe_compare_func)99;
 REQUIRE(!grate_stencil_state_supported(&s)); /* invalid enum */
 s.func=PIPE_FUNC_EQUAL;
 REQUIRE(grate_stencil_state_supported(&s));
 REQUIRE(grate_stencil_draw_supported(&ctx));
 resource.format=PIPE_FORMAT_Z16_UNORM;
 REQUIRE(!grate_stencil_draw_supported(&ctx));
 resource.format=PIPE_FORMAT_S8_UINT;
 z.stencil_unsupported=true;
 REQUIRE(!grate_stencil_draw_supported(&ctx));
 z.stencil_unsupported=false;
 REQUIRE(grate_stencil_ops_ref(&s,0x55,false) ==
   (TGR3D_VAL(STENCIL_FRONT2,REF,0x55) |
    TGR3D_VAL(STENCIL_FRONT2,OP_FAIL,TGR3D_STENCIL_OP_KEEP) |
    TGR3D_VAL(STENCIL_FRONT2,OP_ZFAIL,TGR3D_STENCIL_OP_KEEP) |
    TGR3D_VAL(STENCIL_FRONT2,OP_ZPASS,TGR3D_STENCIL_OP_REPLACE) |
    0x1fe00u));
 emit_zsa_state(&ctx);
 struct grate_stream *stream=&channel.stream;
 REQUIRE(stream->count==9);
 REQUIRE(stream->words[0]==0x123 && stream->words[1]==0x456);
 REQUIRE(stream->words[2]==host1x_opcode_incr(TGR3D_STENCIL_FRONT1,3));
 REQUIRE(stream->words[3]==grate_stencil_compare(&z.base.stencil[0],false));
 REQUIRE(stream->words[4]==grate_stencil_compare(&z.base.stencil[1],true));
 REQUIRE(stream->words[5]==(0x8u | TGR3D_STENCIL_PARAMS_STENCIL_TEST));
 REQUIRE(!(stream->words[5] & TGR3D_STENCIL_PARAMS_STENCIL_WRITE_EARLY));
 REQUIRE(stream->words[6]==host1x_opcode_incr(TGR3D_STENCIL_FRONT2,2));
 REQUIRE(stream->words[7]==grate_stencil_ops_ref(&z.base.stencil[0],0x55,false));
 REQUIRE(stream->words[8]==grate_stencil_ops_ref(&z.base.stencil[1],0x11,true));
 REQUIRE((stream->words[7] & TGR3D_STENCIL_FRONT2_REF__MASK)!=0);
 return 0;
}
"""
        with tempfile.TemporaryDirectory(prefix="sl101-fbl04-cc-") as tmp:
            cfile = Path(tmp) / "oracle.c"
            exe = Path(tmp) / "oracle"
            cfile.write_text(preamble + compare + gate + encode + emit + checks)
            build = subprocess.run([
                cc, "-std=c11", "-Wall", "-Wextra", "-Werror",
                "-I", str(SOURCE), str(cfile), "-o", str(exe),
            ], capture_output=True, text=True)
            self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
            run = subprocess.run([str(exe)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)


if __name__ == "__main__":
    unittest.main()
