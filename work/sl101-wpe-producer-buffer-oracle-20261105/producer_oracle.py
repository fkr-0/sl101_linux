#!/usr/bin/env python3
"""Host-only fail-closed validator for an independently snapshotted Cog producer buffer.

This is NOT a DMA-BUF mapper. Byte readback must be supplied by a separately
verified, synchronized mapper while the producer allocation remains owned.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json

DRM_FORMAT_MOD_LINEAR = 0
DRM_FORMAT_XRGB8888 = 0x34325258
DRM_FORMAT_ARGB8888 = 0x34325241
MAX_SIZE = 512 * 1024 * 1024


class Reject(ValueError):
    pass


@dataclass(frozen=True)
class Plane:
    offset: int
    pitch: int


@dataclass(frozen=True)
class Frame:
    frame_id: int
    width: int
    height: int
    fourcc: int
    modifier: int | None
    planes: tuple[Plane, ...]
    allocated_bytes: int
    export_seq: int
    attach_seq: int
    release_seq: int | None = None
    fence_wait_succeeded: bool = False
    snapshot_before_release: bool = False


def validate(frame: Frame) -> int:
    if frame.frame_id < 0 or frame.export_seq < 0 or frame.attach_seq <= frame.export_seq:
        raise Reject("invalid_frame_sequence")
    if frame.release_seq is not None and frame.release_seq <= frame.attach_seq:
        raise Reject("stale_release")
    if frame.release_seq is not None and frame.release_seq <= frame.export_seq:
        raise Reject("stale_release")
    if frame.modifier != DRM_FORMAT_MOD_LINEAR:
        raise Reject("unsupported_or_unknown_modifier")
    if frame.fourcc not in (DRM_FORMAT_XRGB8888, DRM_FORMAT_ARGB8888):
        raise Reject("unsupported_fourcc")
    if len(frame.planes) != 1:
        raise Reject("unsupported_plane_count")
    if frame.width <= 0 or frame.height <= 0 or frame.width > 16384 or frame.height > 16384:
        raise Reject("invalid_dimensions")
    if not (0 < frame.allocated_bytes <= MAX_SIZE):
        raise Reject("invalid_allocation")
    p = frame.planes[0]
    if p.offset < 0 or p.pitch <= 0 or p.pitch % 4 or p.pitch < 4 * frame.width:
        raise Reject("mismatched_pitch")
    end = p.offset + (frame.height - 1) * p.pitch + frame.width * 4
    if end > frame.allocated_bytes:
        raise Reject("plane_exceeds_allocation")
    if not frame.fence_wait_succeeded:
        raise Reject("unsynchronized_readback")
    if not frame.snapshot_before_release:
        raise Reject("snapshot_not_proven_before_release")
    return end


def verify_snapshot(frame: Frame, snapshot: bytes) -> dict:
    """Check an owned immutable copy, never interpret arbitrary DMA-BUF storage.

    A hash identifies this copy only; it does not establish that the mapper
    captured actual producer pixels or establish visual correctness.
    """
    validate(frame)
    if len(snapshot) != frame.allocated_bytes:
        raise Reject("snapshot_length_mismatch")
    return {
        "frame_id": frame.frame_id,
        "width": frame.width,
        "height": frame.height,
        "fourcc": f"0x{frame.fourcc:08x}",
        "modifier": frame.modifier,
        "planes": [{"offset": p.offset, "pitch": p.pitch} for p in frame.planes],
        "export_seq": frame.export_seq,
        "attach_seq": frame.attach_seq,
        "release_seq": frame.release_seq,
        "sha256": hashlib.sha256(snapshot).hexdigest(),
        "stage": "host_supplied_snapshot",
        "producer_buffer_verified": False,
        "pixel_correctness_verified": False,
    }


if __name__ == "__main__":
    print(json.dumps({"status": "library_only", "producer_buffer_verified": False}))
