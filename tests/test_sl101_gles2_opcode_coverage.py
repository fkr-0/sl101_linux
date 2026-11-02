"""Host-only GLES2 opcode audit checks for Mesa 25.0.7 Grate.

These tests prove source invariants and validate ESSL 1.00 syntax with glslang.
They do NOT create NIR/TGSI, run a Mesa driver, or qualify Tegra20 pixels.
The expected-negative static checks intentionally require maintenance when the
associated missing functionality is integrated.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MESA = ROOT / "build/mesa-grate-clean/mesa-25.0.7"
GRATE = MESA / "src/gallium/drivers/grate"
NIR_TO_TGSI = MESA / "src/gallium/auxiliary/nir/nir_to_tgsi.c"
TOKENS = MESA / "src/gallium/include/pipe/p_shader_tokens.h"

# ESSL 1.00 compilable positive fixtures. Successful glslang validation is
# deliberately only a language-front-end check, not a Grate backend test.
FRAGMENTS = {
    "discard": "precision mediump float; void main(){if(gl_FragCoord.x>2.0) discard; gl_FragColor=vec4(1.0);}",
    "cube": "precision mediump float; uniform samplerCube t; varying vec3 uv; void main(){gl_FragColor=textureCube(t,uv);}",
    "computed_coords": "precision mediump float; uniform sampler2D t; varying vec2 uv; void main(){gl_FragColor=texture2D(t,uv*2.0+vec2(0.1));}",
    "flow": "precision mediump float; uniform float x; void main(){float y=0.0; for(int i=0;i<4;i++){if(x>0.0)y+=0.2;else y-=0.1;}gl_FragColor=vec4(y);}",
    "vectors": "precision mediump float; varying vec3 v; void main(){vec3 n=normalize(v); gl_FragColor=vec4(mix(n,abs(n),0.5),1.0);}",
    "projected": "precision mediump float; uniform sampler2D t; varying vec3 uv; void main(){gl_FragColor=texture2DProj(t,uv);}",
}
VERTICES = {
    "matrices": "attribute vec4 a; uniform mat4 m; varying vec2 uv; void main(){gl_Position=m*a; uv=a.xy;}",
    "dynamic_uniform": "attribute vec4 a; uniform vec4 u[8]; void main(){int k=int(a.x); gl_Position=u[k]+a;}",
}
# An OES extension, not a requirement of unextended ESSL 1.00.
NEGATIVE_FRAGMENT = "precision mediump float; void main(){gl_FragColor=vec4(dFdx(1.0));}"


def source(path: Path) -> str:
    if not path.is_file():
        raise unittest.SkipTest(f"untracked Mesa 25.0.7 source not present: {path}")
    return path.read_text(encoding="utf-8")


def body(text: str, name: str) -> str:
    """Extract a concrete C function body using brace balance."""
    match = re.search(r"\b" + re.escape(name) + r"\s*\([^;{}]*\)\s*\{", text, re.S)
    if not match:
        raise AssertionError(f"function definition not found: {name}")
    start = match.end()
    depth = 1
    for index in range(start, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if not depth:
                return text[start:index]
    raise AssertionError(f"unterminated function body: {name}")


def cases(text: str) -> set[str]:
    return set(re.findall(r"\bcase\s+TGSI_OPCODE_([A-Z][A-Z0-9_]*)\s*:", text))


def inventory() -> dict[str, list[str]]:
    fp = source(GRATE / "fp/tgsi.c")
    vp = source(GRATE / "vp/tgsi.c")
    return {
        "fp_alu": sorted(cases(body(fp, "fp_emit_alu"))),
        "fp_dispatch": sorted(cases(body(fp, "grate_tgsi_to_fp"))),
        "vp_dispatch": sorted(cases(body(vp, "tgsi_to_vp"))),
    }


class StaticGrateAudit(unittest.TestCase):
    def test_real_mesa_opcode_vocabulary(self) -> None:
        header = source(TOKENS)
        ops = set(re.findall(r"\bTGSI_OPCODE_([A-Z][A-Z0-9_]*)\s*=", header))
        observed = set().union(*map(set, inventory().values()))
        self.assertFalse(observed - ops, f"driver dispatches invented Mesa opcodes: {observed - ops}")
        for mandatory in ("TEX", "KILL", "KILL_IF", "IF", "ELSE", "BGNLOOP", "ENDLOOP"):
            self.assertIn(mandatory, ops)

    def test_current_dispatch_snapshot(self) -> None:
        dispatch = inventory()
        self.assertGreaterEqual(set(dispatch["fp_alu"]),
                                {"MOV", "ADD", "MUL", "MAD", "MIN", "MAX"})
        self.assertGreaterEqual(set(dispatch["fp_dispatch"]),
                                {"LG2", "SQRT", "EX2", "SIN", "COS"})
        self.assertGreaterEqual(set(dispatch["vp_dispatch"]),
                                {"MOV", "ADD", "MUL", "MAD", "DP3", "DP4", "RSQ"})
        # These are live-tree cases, not unmerged patch/checkpoint claims.
        print("\nLIVE GRATE TGSI DISPATCH INVENTORY:", dispatch)

    def test_nir_to_tgsi_is_conversion_not_shader_emulation(self) -> None:
        grate = source(GRATE / "grate_program.c")
        ntt = source(NIR_TO_TGSI)
        for token in ("pipe_shader_state_to_tgsi_tokens", "grate_tgsi_to_fp", "grate_tgsi_to_vp"):
            self.assertIn(token, grate)
        for token in ("nir_lower_discard_if", "nir_lower_indirect_derefs",
                      "nir_to_tgsi_lower_tex", "nir_lower_bool_to_float"):
            self.assertIn(token, ntt)

    def test_unimplemented_fragment_paths_reject_instead_of_succeed(self) -> None:
        fp = source(GRATE / "fp/tgsi.c")
        tex = body(fp, "fp_emit_tex")
        self.assertIn("TGSI_TEXTURE_2D", tex)
        self.assertIn("coord->File != TGSI_FILE_INPUT", tex)
        dispatch = cases(body(fp, "grate_tgsi_to_fp"))
        # Expected-negative tests are intentionally revised when the feature is
        # implemented. A Mesa IR pass alone does not provide a backend path.
        self.assertFalse({"KILL", "KILL_IF", "IF", "ELSE", "BGNLOOP", "ENDLOOP"} & dispatch)
        self.assertIn("fp_emit_alu", body(fp, "grate_tgsi_to_fp"))

    def test_mandatory_sampler_mip_and_stencil_deficiencies_are_visible(self) -> None:
        state = source(GRATE / "grate_state.c")
        screen = source(GRATE / "grate_screen.c")
        self.assertIn("min_mip_filter != PIPE_TEX_MIPFILTER_NONE", state)
        self.assertIn("template->u.tex.last_level != 0", state)
        self.assertIn("template->target != PIPE_TEXTURE_2D", state)
        self.assertNotIn("template->stencil[", body(state, "grate_create_zsa_state"))
        self.assertIn("caps->max_texture_cube_levels = 16", screen)

    def test_fragment_uniform_hard_limit_is_below_es2_minimum(self) -> None:
        fp = source(GRATE / "fp/tgsi.c")
        screen = source(GRATE / "grate_screen.c")
        ir = source(GRATE / "fp/fpir.h")
        self.assertRegex(ir, r"#define\s+FP_UNIFORM_COUNT\s+32")
        self.assertIn("scalar >= FP_UNIFORM_COUNT", body(fp, "fp_src_component"))
        self.assertIn("FP_UNIFORM_COUNT * sizeof(float)", screen)
        self.assertLess(32 // 4, 16)  # GLES2: MAX_FRAGMENT_UNIFORM_VECTORS >= 16


class GLSL100Fixtures(unittest.TestCase):
    def compile_shader(self, stage: str, snippet: str) -> subprocess.CompletedProcess[str]:
        if not shutil.which("glslangValidator"):
            self.skipTest("glslangValidator unavailable (host GLSL syntax fixtures)")
        with tempfile.TemporaryDirectory(prefix="sl101-gles2-glsl-") as tempdir:
            path = Path(tempdir) / f"fixture.{stage}"
            path.write_text(snippet + "\n", encoding="utf-8")
            return subprocess.run(
                ["glslangValidator", "-S", stage, str(path)],
                capture_output=True, text=True, timeout=20, check=False,
            )

    def test_essl100_valid_positive_fixtures(self) -> None:
        for stage, snippets in (("frag", FRAGMENTS), ("vert", VERTICES)):
            for name, snippet in snippets.items():
                with self.subTest(stage=stage, feature=name):
                    result = self.compile_shader(stage, snippet)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_optional_derivative_requires_extension(self) -> None:
        result = self.compile_shader("frag", NEGATIVE_FRAGMENT)
        self.assertNotEqual(result.returncode, 0, "dFdx must not pass unextended ESSL 1.00")


if __name__ == "__main__":
    unittest.main()
