import os
import json
from typing import List, Dict, Any

from moviepy import VideoFileClip, concatenate_videoclips


def build_timeline(shot_descriptions: List[Any], working_dir: str) -> Dict[str, Any]:
    entries: List[Dict[str, Any]] = []
    for sd in shot_descriptions:
        path = os.path.join(working_dir, "shots", f"{sd.idx}", "video.mp4")
        if not os.path.exists(path):
            # skip missing; the caller should ensure generation
            continue
        # Read duration to fill out/out points
        try:
            with VideoFileClip(path) as clip:
                duration = clip.duration
        except Exception:
            duration = None
        entries.append({
            "shot_idx": sd.idx,
            "path": path,
            "in": 0.0,
            "out": duration,
            "transition_in": getattr(sd, "transition_in", "cut"),
            "transition_out": getattr(sd, "transition_out", "cut"),
            "beat": getattr(sd, "beat", "moderate"),
            "duration_sec_estimate": getattr(sd, "duration_sec_estimate", None),
        })
    return {"entries": entries}


def write_timeline_edl(timeline: Dict[str, Any], path: str) -> None:
    lines = ["TITLE: ViMax Timeline", "FCM: NON-DROP FRAME"]
    for i, e in enumerate(timeline.get("entries", []), start=1):
        trans = e.get("transition_out", "cut")
        shot = e.get("shot_idx")
        dur = e.get("out") or 0
        lines.append(f"{i:003}  SHOT {shot}  {trans.upper()}  DUR {dur:.2f}s  PATH {e.get('path')}")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def render_timeline(timeline: Dict[str, Any], output_path: str) -> None:
    entries = timeline.get("entries", [])
    if not entries:
        raise ValueError("Empty timeline entries")

    # load clips
    clips: List[VideoFileClip] = []
    for e in entries:
        clip = VideoFileClip(e["path"])  # closed by write_videofile on the result
        clips.append(clip)

    # Note: to avoid dependency on moviepy.editor.CompositeVideoClip, we fall back to
    # simple concatenation here. Any requested dissolve transitions are logged but treated as cut.
    if any((e.get("transition_in") == "dissolve" or e.get("transition_out") == "dissolve") for e in entries):
        print("[timeline] dissolve requested but not supported in current build; falling back to cut.")

    final = concatenate_videoclips(clips, method="chain")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    final.write_videofile(output_path, codec="libx264", preset="medium")
