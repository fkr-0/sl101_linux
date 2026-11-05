"""Pure host synthetic regression for the offline pixel gate."""
import hashlib
import importlib.util
from pathlib import Path
import unittest

path=Path(__file__).resolve().parents[1]/"scripts/sl101-wayland-producer-frame-gate.py"
spec=importlib.util.spec_from_file_location("sl101_frame_gate",path)
gate=importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)

class TestFrameGate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        raw=bytearray(4096*720)
        screen=bytearray(1280*800*3)
        for y in range(720):
            for x in range(1024):
                rgb=((255,0,0),(0,255,0),(0,0,255),(255,255,255))[
                    (x>=512)+2*(y>=360)]
                p=y*4096+x*4
                raw[p:p+4]=bytes((rgb[2],rgb[1],rgb[0],255))
                q=((y+68)*1280+x+128)*3
                screen[q:q+3]=bytes(rgb)
        cls.raw=bytes(raw)
        cls.screen=bytes(screen)
        cls.meta=dict(origin="WPE_FDO_EGL_EXPORT",snapshot_stage="pre_attach_owned_copy",
                      sync_method="verified_egl_fence",sync_complete=True,
                      coherency_verified=True,modifier_verified=True,layout_verified=True,
                      modifier=0,fourcc=0x34325258,planes=1,width=1024,height=720,
                      x=128,y=68,scale=1,transform=0,viewport=[1024,720],
                      frame_id=7,screenshot_frame_id=7,marker="frame0007",
                      screenshot_marker="frame0007",marker_visually_verified=True,
                      export_seq=1,copy_seq=2,attach_seq=3,commit_seq=4,release_seq=5,
                      copy_ns=10,attach_ns=20,capture_ns=30,release_ns=40,
                      pitch=4096,offset=0,
                      producer_sha256=hashlib.sha256(raw).hexdigest(),
                      screen_sha256=hashlib.sha256(screen).hexdigest())
    def reject(self,**updates):
        with self.assertRaises(gate.GateError):
            gate.compare(dict(self.meta,**updates),self.raw,self.screen)
    def test_clean_still_conditional(self):
        out=gate.compare(self.meta,self.raw,self.screen)
        self.assertEqual(out["compositor_vs_copy_errors"],0)
        self.assertEqual(out["producer_interior_errors"],0)
        self.assertFalse(out["actual_producer_pixels_verified"])
    def test_magenta(self):
        s=bytearray(self.screen)
        s[((68+50)*1280+128+50)*3:((68+50)*1280+128+50)*3+3]=bytes((255,0,255))
        m=dict(self.meta,screen_sha256=hashlib.sha256(s).hexdigest())
        self.assertEqual(gate.compare(m,self.raw,bytes(s))["compositor_magenta_errors"],1)
    def test_unsignaled(self): self.reject(sync_complete=False)
    def test_unknown_sync(self): self.reject(sync_method="assumed")
    def test_modifier_tiled(self): self.reject(modifier=0x100000000000001)
    def test_unknown_modifier(self): self.reject(modifier=None)
    def test_unverified_layout(self): self.reject(layout_verified=False)
    def test_wrong_fourcc(self): self.reject(fourcc=0x3231564e)
    def test_multiplane(self): self.reject(planes=2)
    def test_lag(self): self.reject(screenshot_frame_id=6)
    def test_marker(self): self.reject(screenshot_marker="frame0006")
    def test_release_reentry(self): self.reject(release_seq=2)
    def test_captured_after_release(self): self.reject(capture_ns=41)
    def test_non64_pitch_overrun(self): self.reject(pitch=4100)
    def test_short_allocation(self):
        with self.assertRaises(gate.GateError): gate.compare(self.meta,self.raw[:-1],self.screen)
    def test_bad_capture(self): self.reject(marker_visually_verified=False)
    def test_bad_viewport(self): self.reject(viewport=[1280,800])
    def test_incoherent(self): self.reject(coherency_verified=False)

if __name__=="__main__":
    unittest.main()
