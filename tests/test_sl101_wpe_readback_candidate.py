"""Host-only regression: source, ABI compilation, and fail-closed runtime probe."""
import ctypes
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
C=ROOT/"work/sl101-wpe-readback-20261105/sl101-wpe-readback.c"
HEADER=ROOT/"work/sl101-wpe-readback-20261105/sl101-wpe-readback.h"
PATCH=ROOT/"work/sl101-wpe-readback-20261105/0001-cog-wayland-producer-metadata-hook.patch"
COG=ROOT/"work/scanout-followups-20261103/cog-teardown/cog-src/platform/wayland/cog-platform-wl.c"

class ReadbackCandidate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory()
        cls.so=Path(cls.temp.name)/"libsl101-readback.so"
        subprocess.run(["cc","-std=c11","-Wall","-Wextra","-Werror","-shared","-fPIC",
                        str(C),"-o",str(cls.so),"-lEGL"],check=True,capture_output=True)
        cls.lib=ctypes.CDLL(str(cls.so))
        cls.lib.sl101_rb_readback.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_uint,
                                          ctypes.c_uint,ctypes.c_int,ctypes.c_void_p]
        cls.lib.sl101_rb_readback.restype=ctypes.c_int
        cls.lib.sl101_rb_probe.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_uint,
                                        ctypes.c_uint,ctypes.c_void_p]
        cls.lib.sl101_rb_probe.restype=ctypes.c_int
    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()
    def test_no_producer_fence_is_rejected(self):
        # -1 must reject BEFORE dereferencing an EGLImage or EGLDisplay.
        output=ctypes.create_string_buffer(128)
        result=self.lib.sl101_rb_readback(None,None,1024,720,-1,output)
        self.assertEqual(result,2)
        self.assertEqual(output.raw,bytes(len(output)))
    def test_null_output_is_rejected(self):
        self.assertEqual(self.lib.sl101_rb_readback(None,None,1,1,-1,None),3)
    def test_invalid_egl_probe_rejected(self):
        output=ctypes.create_string_buffer(128)
        self.assertEqual(self.lib.sl101_rb_probe(None,None,1024,720,output),3)
    def test_too_large_dimensions_rejected(self):
        output=ctypes.create_string_buffer(128)
        self.assertEqual(self.lib.sl101_rb_probe(None,None,5000,720,output),3)
    def test_probe_requires_output(self):
        self.assertEqual(self.lib.sl101_rb_probe(None,None,1,1,None),3)
    def test_linear_copy_with_mocked_export_and_sync(self):
        fixture=ROOT/'work/sl101-wpe-readback-20261105/readback_mock.c'
        exe=Path(self.temp.name)/'mock-copy'
        subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror',
                        str(fixture),'-o',str(exe),'-lEGL'],
                       check=True,capture_output=True)
        result=subprocess.run([str(exe)],check=True,capture_output=True,text=True)
        self.assertIn('MOCK_LINEAR_COPY_PASS',result.stdout)
    def test_strict_sync_file_checks_exist(self):
        src=C.read_text()
        for token in ["SYNC_IOC_FILE_INFO","info.status == 1","info.num_fences > 0",
                      "DMA_BUF_IOCTL_SYNC","DMA_BUF_SYNC_START","DMA_BUF_SYNC_END",
                      "eglExportDMABUFImageQueryMESA","eglExportDMABUFImageMESA",
                      "EGL_MESA_image_dma_buf_export","modifier != 0",
                      "mmap(","munmap(","close(fd)"]:
            with self.subTest(token=token):
                self.assertIn(token,src)
    def test_patch_is_correctly_scoped_and_applies(self):
        patch=PATCH.read_text()
        self.assertIn("pixels=UNVERIFIED reason=no_producer_fence",patch)
        self.assertIn("sl101_rb_probe(",patch)
        self.assertNotIn("sl101_rb_readback(",patch)
        with tempfile.TemporaryDirectory() as d:
            dest=Path(d)/"platform/wayland"
            dest.mkdir(parents=True)
            (dest/"cog-platform-wl.c").write_bytes(COG.read_bytes())
            result=subprocess.run(["patch","--batch","--fuzz=0","-p1","-i",str(PATCH)],
                                  cwd=d,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            updated=(dest/"cog-platform-wl.c").read_text()
            self.assertLess(updated.index("sl101_rb_probe("),updated.index("wl_surface_attach ("))
    def test_no_prod_activation_without_fence(self):
        patch=PATCH.read_text()
        self.assertNotIn("wl_buffer_destroy",patch)
        self.assertNotIn("wpe_view_backend_exportable_fdo_egl_dispatch_release",patch)

if __name__=="__main__":
    unittest.main()
