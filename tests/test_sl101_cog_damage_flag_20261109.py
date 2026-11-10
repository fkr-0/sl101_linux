import pathlib, re, subprocess, unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
FLAG = "--features=-UseDamagingInformationForCompositing"
FILES = [ROOT / "docs/sl101-device-config/usr/local/libexec/sl101-cog-wpe-enter",
         ROOT / "scripts/sl101-cog-session"]


def gpu_and_software(text: str) -> tuple[str, str]:
    # Find the actual rendering branch, not the first fi in the script:
    # Cog's optional JS-injection preflight now has its own if/fi.
    marker = '\nif [ "$mode" = gpu ]; then'
    assert text.count(marker) == 1, "GPU branch missing or ambiguous"
    _, remainder = text.split(marker, 1)
    gpu, soft = remainder.split("\nfi\n", 1)
    return gpu, soft


class CogDamageFlag(unittest.TestCase):
    def test_scripts_parse(self):
        for f in FILES:
            self.assertEqual(subprocess.run(["sh", "-n", str(f)]).returncode, 0, f.name)

    def test_gpu_branch_has_flag_after_platform_and_software_branch_does_not(self):
        for f in FILES:
            s = f.read_text()
            gpu, soft = gpu_and_software(s)
            self.assertEqual(len(re.findall(r"cog --platform=wl \\\n\s+" + re.escape(FLAG) + r' "\$@"', gpu)), 1, f.name)
            self.assertIn("--platform=wl", soft)
            self.assertNotIn("UseDamagingInformationForCompositing", soft, f.name)

    def test_software_branch_uses_cpu_skia_like_the_gate(self):
        # the device enter script needs it in both branches; scripts/sl101-cog-session is an older variant
        # whose GPU branch (a different Grate overlay) never had it, so only its software branch is pinned
        for f in FILES:
            gpu, soft = gpu_and_software(f.read_text())
            self.assertIn("WEBKIT_SKIA_ENABLE_CPU_RENDERING=1", soft, f.name)
        gpu, _ = gpu_and_software(FILES[0].read_text())
        self.assertIn("WEBKIT_SKIA_ENABLE_CPU_RENDERING=1", gpu)

    def test_flag_is_documented_where_it_is_set(self):
        for f in FILES:
            self.assertIn("damage-based compositing", f.read_text(), f.name)


if __name__ == "__main__":
    unittest.main()
