#!/usr/bin/env python3
"""Fail-closed OFFLINE oracle for pre-copied, caller-asserted frames; never maps DMA-BUF."""
import argparse
import hashlib
import json
from pathlib import Path

class GateError(ValueError):
    pass

def require(value, reason):
    if not value:
        raise GateError(reason)

def compare(meta, producer, screen):
    """Returns only conditional differences: a JSON manifest cannot prove producer origin."""
    m = meta
    require(m.get("origin") == "WPE_FDO_EGL_EXPORT", "missing_origin")
    require(m.get("snapshot_stage") == "pre_attach_owned_copy", "not_pre_attach")
    require(m.get("sync_method") in ("verified_egl_fence", "verified_gl_finish",
                                    "verified_drm_syncpt"), "unverified_sync_method")
    require(m.get("sync_complete") is True and m.get("coherency_verified") is True,
            "unsynchronized_or_incoherent")
    require(m.get("modifier_verified") is True and m.get("layout_verified") is True,
            "unverified_layout")
    require(m.get("modifier") == 0, "unknown_or_nonlinear_modifier")
    require(m.get("fourcc") in (0x34325258, 0x34325241), "unsupported_fourcc")
    require(m.get("planes") == 1, "unsupported_planes")
    require((m.get("width"),m.get("height")) == (1024,720), "incorrect_dimensions")
    require((m.get("x"),m.get("y"),m.get("scale"),m.get("transform"),
             m.get("viewport")) == (128,68,1,0,[1024,720]), "unmatched_geometry")
    require(m.get("frame_id") == m.get("screenshot_frame_id")
            and isinstance(m.get("marker"),str) and len(m["marker"]) >= 8
            and m.get("marker") == m.get("screenshot_marker")
            and m.get("marker_visually_verified") is True, "frame_identity_unproven")
    seq = [m.get(k) for k in ("export_seq","copy_seq","attach_seq","commit_seq","release_seq")]
    require(all(type(x) is int for x in seq) and seq == sorted(set(seq)),
            "stale_or_reentrant_release")
    ts = [m.get(k) for k in ("copy_ns","attach_ns","capture_ns","release_ns")]
    require(all(type(x) is int for x in ts) and ts == sorted(ts), "timestamp_mismatch")
    pitch, offset = m.get("pitch"), m.get("offset")
    require(type(pitch) is int and 4096 <= pitch <= 64*1024*1024
            and pitch%4==0 and type(offset) is int and offset>=0, "bad_pitch_or_offset")
    require(offset+719*pitch+4096 <= len(producer) <= 64*1024*1024,
            "short_or_oversized_allocation")
    require(len(screen) == 1280*800*3, "bad_screen_length")
    require(hashlib.sha256(producer).hexdigest() == m.get("producer_sha256")
            and hashlib.sha256(screen).hexdigest() == m.get("screen_sha256"),
            "immutable_copy_hash_mismatch")
    mismatches=magenta=quadrant_bad=0
    contours=dict(top=0,bottom=0,left=0,right=0,interior=0)
    for y in range(720):
        for x in range(1024):
            p=offset+y*pitch+x*4
            b,g,r=producer[p:p+3]
            rgb=(r,g,b)  # little-endian DRM XRGB8888 / ARGB8888 bytes
            q=((y+68)*1280+x+128)*3
            actual=tuple(screen[q:q+3])
            if actual!=rgb:
                mismatches+=1
                magenta+=(actual==(255,0,255))
                zone=("top" if y<20 else "bottom" if y>=700 else
                      "left" if x<20 else "right" if x>=1004 else "interior")
                contours[zone]+=1
            # Border and per-frame visual marker intentionally excluded.
            if 30<=x<994 and 30<=y<690 and abs(x-512)>16 and abs(y-360)>16:
                expect=((255,0,0),(0,255,0),(0,0,255),(255,255,255))[
                    (x>=512)+2*(y>=360)]
                quadrant_bad+=(rgb!=expect)
    return dict(status="CONDITIONAL_UNVERIFIED_ORIGIN",
                hardware_attribution="INCONCLUSIVE",
                actual_producer_pixels_verified=False, frame_id=m["frame_id"],
                producer_interior_errors=quadrant_bad,
                compositor_vs_copy_errors=mismatches,
                compositor_magenta_errors=magenta, contours=contours)

def main():
    p=argparse.ArgumentParser()
    for arg in ("metadata","producer-raw","screen-rgb"):
        p.add_argument("--"+arg,required=True,type=Path)
    a=p.parse_args()
    try:
        result=compare(json.loads(a.metadata.read_text()),
                       a.producer_raw.read_bytes(),a.screen_rgb.read_bytes())
    except (GateError,OSError,TypeError,ValueError) as exc:
        result=dict(status="BLOCKED",reason=str(exc),
                    hardware_attribution="INCONCLUSIVE")
    print(json.dumps(result,sort_keys=True))
    return int(result["status"]=="BLOCKED")

if __name__=="__main__":
    raise SystemExit(main())
