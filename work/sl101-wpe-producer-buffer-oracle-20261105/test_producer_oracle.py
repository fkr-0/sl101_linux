#!/usr/bin/env python3
"""Deterministic host fixtures; no device or GPU access."""
from dataclasses import replace
import unittest

from producer_oracle import (
    DRM_FORMAT_XRGB8888, Frame, Plane, Reject, verify_snapshot
)


def fixture() -> Frame:
    return Frame(
        frame_id=19, width=8, height=4, fourcc=DRM_FORMAT_XRGB8888,
        modifier=0, planes=(Plane(0, 32),), allocated_bytes=128,
        export_seq=100, attach_seq=101, release_seq=104,
        fence_wait_succeeded=True, snapshot_before_release=True,
    )


class GateTests(unittest.TestCase):
    def assert_reject(self, frame, reason):
        with self.assertRaisesRegex(Reject, f"^{reason}$"):
            verify_snapshot(frame, bytes(frame.allocated_bytes))

    def test_correct_linear(self):
        out = verify_snapshot(fixture(), bytes(128))
        self.assertEqual((out["frame_id"], out["planes"][0]["pitch"]), (19, 32))
        self.assertFalse(out["producer_buffer_verified"])
        self.assertFalse(out["pixel_correctness_verified"])

    def test_mismatched_pitch(self):
        self.assert_reject(replace(fixture(), planes=(Plane(0, 28),)), "mismatched_pitch")

    def test_stale_release(self):
        self.assert_reject(replace(fixture(), release_seq=100), "stale_release")

    def test_multiplane(self):
        self.assert_reject(replace(fixture(), planes=(Plane(0, 32), Plane(128, 16))),
                           "unsupported_plane_count")

    def test_unsupported_modifier(self):
        self.assert_reject(replace(fixture(), modifier=0x100000000000001),
                           "unsupported_or_unknown_modifier")

    def test_unknown_modifier(self):
        self.assert_reject(replace(fixture(), modifier=None), "unsupported_or_unknown_modifier")

    def test_unsynchronized(self):
        self.assert_reject(replace(fixture(), fence_wait_succeeded=False),
                           "unsynchronized_readback")

    def test_recycled(self):
        self.assert_reject(replace(fixture(), snapshot_before_release=False),
                           "snapshot_not_proven_before_release")

    def test_short_allocation(self):
        self.assert_reject(replace(fixture(), allocated_bytes=127), "plane_exceeds_allocation")


if __name__ == "__main__":
    unittest.main(verbosity=2)
