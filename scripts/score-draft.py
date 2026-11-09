#!/usr/bin/env python3
"""Score a photo-read room against measured ground truth.

    scripts/score-draft.py --scene <inspect-full.json | from_photo-result.json> \
        --truth fixtures/photos/ground-truth.json --room room-02 [--pre-size W D]

`--scene` accepts a roomsmith_inspect (detail full) result, a roomsmith_from_photo
result, or a bare scene. `--pre-size` gives the model's room size BEFORE calibration
when the scene has already been calibrated (read it from the from_photo result).
Prints per-dimension error, which walls hold the door/window, and the objects with
their mounts. Ground truth never reaches the model; this is for us.
"""
import argparse
import json
from pathlib import Path


def load_scene(path: Path) -> tuple[dict, dict]:
    d = json.loads(path.read_text())
    if "scene" in d and isinstance(d["scene"], dict) and "room" in d["scene"]:
        return d["scene"], d
    if "room" in d and "objects" in d and "walls" in d.get("room", {}):
        return d, d
    raise SystemExit("not a scene, inspect(full) or from_photo result")


def pct(est: float, real: float) -> str:
    return f"{est:.2f} vs {real:.2f} m  ({(est - real) / real * 100:+.1f} %)"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scene", required=True, type=Path)
    ap.add_argument("--truth", default=Path(__file__).resolve().parents[1] / "fixtures" / "photos" / "ground-truth.json", type=Path)
    ap.add_argument("--room", required=True)
    ap.add_argument("--pre-size", nargs=2, type=float, metavar=("W", "D"), help="model's width/depth before calibration")
    a = ap.parse_args()
    scene, raw = load_scene(a.scene)
    truth = json.loads(a.truth.read_text())[a.room]

    xs = [v["x"] for v in scene["room"]["vertices"]]
    zs = [v["z"] for v in scene["room"]["vertices"]]
    w, d = max(xs) - min(xs), max(zs) - min(zs)
    tw, td = truth["floor_m"]
    cal = (scene.get("calibration") or {}).get("status")
    print(f"== {a.room}: {truth.get('notes', '')}")
    print(f"calibration: {cal}")
    if a.pre_size:
        print(f"model width : {pct(a.pre_size[0], tw)}")
        print(f"model depth : {pct(a.pre_size[1], td)}")
    label = "after calibration" if cal == "calibrated" else "model"
    print(f"{label} width : {pct(w, tw)}")
    print(f"{label} depth : {pct(d, td)}")
    print(f"ceiling     : {scene['room']['height_m']:.2f} m" + (f"  ({pct(scene['room']['height_m'], truth['height_m'])})" if truth.get("height_m") else ""))

    walls = {wl["id"]: wl for wl in scene["room"]["walls"]}
    labels = {"w1": "back", "w2": "right", "w3": "front", "w4": "left"}
    print("openings:")
    for o in scene["room"]["openings"]:
        line = f"  {o['kind']:7} on {o['wall_id']} ({labels.get(o['wall_id'], '?')}) {o['width_m']:.2f} x {o['height_m']:.2f} m, offset {o['offset_m']:.2f}, sill {o['sill_m']:.2f}"
        if o["kind"] == "door" and truth.get("door_height_m"):
            line += f"   height {pct(o['height_m'], truth['door_height_m'])}"
        if o["kind"] == "door" and truth.get("door_width_m"):
            line += f"   width {pct(o['width_m'], truth['door_width_m'])}"
        print(line)
    print("objects:")
    for o in scene["objects"]:
        dims = " x ".join(f"{v:.2f}" for v in o["dimensions_m"])
        print(f"  {o['name'][:34]:34} {o['category']:13} {dims:>20} m  mount={o.get('mount', 'floor'):8} y={o['position_m'][1]:.2f}")
    issues = raw.get("issues") or []
    print(f"issues: {len([i for i in issues if i.get('severity') != 'info'])} warning(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
