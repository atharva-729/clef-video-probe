"""Phase 2: sample frames and write the labelling kit.

  python src/make_label_sheet.py

Writes data/frames/*.jpg, data/labels/{labels.csv,events_truth.csv,LABELLING.md,label_helper.html}
and docs/frames_thumbnails.jpg. Existing labels.csv / events_truth.csv are never overwritten.
"""
import csv
import json
import subprocess
import sys
from pathlib import Path

import yaml
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from clef_client import load_schema  # noqa: E402
NUMERIC = {"altitude_km": "altitude_raw", "speed_kms": "speed_raw", "distance_km": "distance_raw"}

# How to read each question when labelling. Anything not listed uses the schema wording alone.
HINTS = {
    "main_view": "The largest area of the screen. A live shot of the pad or rocket is `live_camera_rocket`; the CGI rocket is `animation_rocket`.",
    "clock_state": "The small mission clock. `t_minus` = counting down, `t_plus` = counting up, `not_visible` = no clock on screen.",
    "altitude_km": "Write the number as shown (`177`, not a bucket). `none` if no altitude is on screen.",
    "speed_kms": "Write the number as shown (`2,92` or `2.92`). `none` if no speed is on screen.",
    "distance_km": "Write the number as shown. `none` if no distance is on screen.",
    "vehicle_location": "`on_pad` until the rocket has visibly left the pad. `not_visible` if the rocket is not shown.",
    "side_boosters_attached": "`attached` from the pad until separation. `cant_tell` if the rocket is not shown clearly.",
    "fairing_attached": "`attached` until the fairing halves are gone. `cant_tell` if the rocket is not shown clearly.",
    "payload_separated": "`yes` only once the telescope has left the upper stage. Seeing the telescope earlier does not count.",
    "flight_phase": "Pick the phase the broadcast is in, using the mission clock or the state of boosters and fairing.",
    "highlight_worthy": "`yes` for liftoff, separations and similar key moments; `no` for routine shots.",
    "ad_break_safe": "`yes` if cutting away here would miss nothing important.",
}


def ffmpeg_frame(video, t, out):
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-ss", str(t), "-i", str(video),
         "-frames:v", "1", "-q:v", "2", str(out)],
        check=True,
    )


def write_if_missing(path, text):
    if path.exists():
        print(f"kept existing {path.relative_to(ROOT)}")
        return
    path.write_text(text, encoding="utf-8", newline="")


def labelling_md(schema, interval):
    lines = [
        "# Labelling guide",
        "",
        f"Schema version {schema['version']}. One row per frame in `labels.csv`; open `label_helper.html` to see the frames.",
        "",
        "## Rules",
        "",
        "- Answer **only from what is visible in the frame**, the same as Clef.",
        "- `?` means you are unsure. Those cells are excluded from scoring.",
        "- Numeric columns (`altitude_raw`, `speed_raw`, `distance_raw`): write the number as shown on screen. A French comma is fine (`2,92`). Write `none` if the number is not on screen. Do not bucket it; `evaluate.py` does that.",
        "- Every other column takes one of the values below, spelled exactly.",
        "- `notes` is free text and is not scored.",
        "- Do not edit the `frame` or `t_seconds` columns.",
        "",
        "## Columns",
        "",
    ]
    for q in schema["questions"]:
        qid = q["id"]
        if qid in NUMERIC:
            col, vals = NUMERIC[qid], "a raw number, or `none`"
        else:
            col, vals = qid, ", ".join(f"`{o}`" for o in q["options"])
        lines += [f"### `{col}`", "", q["question"], "", f"Values: {vals}", ""]
        if qid in HINTS:
            lines += [HINTS[qid], ""]
    lines += [
        "## Event times (`events_truth.csv`)",
        "",
        "Columns: `event,timestamp_s`. Use seconds from the start of the clip, to the nearest second, and leave a row out if the event does not happen in the clip.",
        "",
        "| Event | What to mark |",
        "|---|---|",
        "| `ignition` | the mission clock reaches zero and the main engine lights (about 61 s) |",
        "| `liftoff` | the rocket visibly leaves the pad |",
        "| `booster_separation` | the side boosters fall away |",
        "| `fairing_jettison` | the fairing halves fall away |",
        "| `payload_separation` | the telescope separates from the upper stage |",
        "| `crossed_100km` | the displayed altitude first reaches 100 km |",
        "",
        f"Frames are {interval} s apart, so events are scored with a tolerance of two frames.",
    ]
    return "\n".join(lines) + "\n"


def helper_html(frames):
    data = json.dumps(frames)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Label helper</title>
<style>
body{{margin:0;background:#111;color:#eee;font:16px system-ui,sans-serif;text-align:center}}
#bar{{padding:10px;font-size:20px}} img{{max-width:96vw;max-height:84vh}}
small{{color:#999}}
</style></head><body>
<div id="bar"></div>
<img id="img" alt="frame">
<div><small>Left / right arrow keys step through the frames. View only; labels go in labels.csv.</small></div>
<script>
const frames = {data};
let i = Number(location.hash.slice(1)) || 0;
function show() {{
  i = Math.max(0, Math.min(frames.length - 1, i));
  const f = frames[i];
  const m = Math.floor(f.t / 60), s = f.t - m * 60;
  document.getElementById('bar').textContent =
    `#${{i}} of ${{frames.length - 1}}  |  t = ${{f.t}} s (${{String(m).padStart(2,'0')}}:${{String(s).padStart(2,'0')}})  |  ${{f.name}}`;
  document.getElementById('img').src = '../frames/' + f.name;
  location.hash = i;
}}
addEventListener('keydown', e => {{
  if (e.key === 'ArrowRight') {{ i++; show(); }}
  if (e.key === 'ArrowLeft') {{ i--; show(); }}
}});
show();
</script></body></html>
"""


def thumbnail_grid(frames_dir, frames, out, cols=11, tile_width=160):
    font = ImageFont.load_default(size=14)
    tiles = []
    for f in frames:
        tile = Image.open(frames_dir / f["name"]).convert("RGB")
        tile = tile.resize((tile_width, round(tile.height * tile_width / tile.width)))
        draw = ImageDraw.Draw(tile)
        draw.rectangle((0, 0, 70, 18), fill="black")
        draw.text((3, 1), f"{f['t']}s", fill="white", font=font)
        tiles.append(tile)
    w, h = tiles[0].size
    rows = -(-len(tiles) // cols)
    sheet = Image.new("RGB", (cols * w, rows * h), "black")
    for i, tile in enumerate(tiles):
        sheet.paste(tile, ((i % cols) * w, (i // cols) * h))
    sheet.save(out, "JPEG", quality=85)


def main():
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    schema = load_schema()
    interval = cfg["sample_interval_s"]
    video = ROOT / cfg["clip"]["path"]
    frames_dir = ROOT / "data" / "frames"
    labels_dir = ROOT / "data" / "labels"
    frames_dir.mkdir(parents=True, exist_ok=True)
    labels_dir.mkdir(parents=True, exist_ok=True)

    times = list(range(0, int(cfg["clip"]["duration_s"]), interval))
    frames = []
    for i, t in enumerate(times):
        name = f"f_{i:04d}_t{t:05.1f}.jpg"
        ffmpeg_frame(video, t, frames_dir / name)
        frames.append({"name": name, "t": t})
    print(f"sampled {len(frames)} frames")

    cols = ["frame", "t_seconds"] + [NUMERIC.get(q["id"], q["id"]) for q in schema["questions"]] + ["notes"]
    rows = [[f["name"], f["t"]] + [""] * (len(cols) - 2) for f in frames]
    labels_path = labels_dir / "labels.csv"
    if labels_path.exists():
        print("kept existing data/labels/labels.csv")
    else:
        with labels_path.open("w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(cols)
            w.writerows(rows)

    write_if_missing(labels_dir / "events_truth.csv", "event,timestamp_s\n")
    (labels_dir / "LABELLING.md").write_text(labelling_md(schema, interval), encoding="utf-8")
    (labels_dir / "label_helper.html").write_text(helper_html(frames), encoding="utf-8")
    thumbnail_grid(frames_dir, frames, ROOT / "docs" / "frames_thumbnails.jpg")
    print("wrote labelling kit and docs/frames_thumbnails.jpg")


if __name__ == "__main__":
    main()
