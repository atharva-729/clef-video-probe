"""Phase 7: sample one frame per second over the 60 s around each true event.

  python src/sample_dense.py

Reads data/labels/events_truth.csv and writes data/frames_dense/f_d<sec>_t<sec>.0.jpg.
Then: python src/run_clef.py --frames-dir data/frames_dense --run-id <id>
"""
import csv
from pathlib import Path

from clef_client import load_config
from make_label_sheet import ffmpeg_frame

ROOT = Path(__file__).resolve().parent.parent
HALF_WINDOW_S = 30


def main():
    cfg = load_config()
    with (ROOT / "data/labels/events_truth.csv").open(encoding="utf-8", newline="") as fh:
        times = [float(r["timestamp_s"]) for r in csv.DictReader(fh) if r["timestamp_s"].strip()]
    seconds = sorted({s for t in times for s in range(int(t) - HALF_WINDOW_S, int(t) + HALF_WINDOW_S)
                      if 0 <= s < cfg["clip"]["duration_s"]})
    out = ROOT / "data" / "frames_dense"
    out.mkdir(parents=True, exist_ok=True)
    for s in seconds:
        ffmpeg_frame(ROOT / cfg["clip"]["path"], s, out / f"f_d{s:03d}_t{s:03d}.0.jpg")
    print(f"sampled {len(seconds)} frames into data/frames_dense ({seconds[0]} s to {seconds[-1]} s)")


if __name__ == "__main__":
    main()
