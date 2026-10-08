"""Phase 1: trim the clip and build timestamp-labelled contact sheets.

  python src/prepare_clip.py trim <source> --start 0 --duration 330
  python src/prepare_clip.py sheet <video> <out.jpg> --every 15
"""
import argparse
import subprocess
import tempfile
from pathlib import Path

import yaml
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent


def duration_s(video):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(video)],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


def trim(source, start, duration, out):
    """Cut [start, start + duration] and re-encode to H.264/AAC so it plays in a browser."""
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(source), "-ss", str(start), "-t", str(duration),
         "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(out)],
        check=True,
    )


def contact_sheet(video, out, every, cols=5, tile_width=384):
    """One tile every `every` seconds, each labelled mm:ss."""
    times = list(range(0, int(duration_s(video)), every))
    font = ImageFont.load_default(size=20)
    tiles = []
    with tempfile.TemporaryDirectory() as tmp:
        for t in times:
            frame = Path(tmp) / f"{t:05d}.jpg"
            subprocess.run(
                ["ffmpeg", "-y", "-loglevel", "error", "-ss", str(t), "-i", str(video),
                 "-frames:v", "1", "-vf", f"scale={tile_width}:-2", "-q:v", "3", str(frame)],
                check=True,
            )
            tile = Image.open(frame).convert("RGB")
            draw = ImageDraw.Draw(tile)
            label = f"{t // 60:02d}:{t % 60:02d}"
            box = draw.textbbox((6, 4), label, font=font)
            draw.rectangle((box[0] - 4, box[1] - 3, box[2] + 4, box[3] + 3), fill="black")
            draw.text((6, 4), label, fill="white", font=font)
            tiles.append(tile)
    w, h = tiles[0].size
    rows = -(-len(tiles) // cols)
    sheet = Image.new("RGB", (cols * w, rows * h), "black")
    for i, tile in enumerate(tiles):
        sheet.paste(tile, ((i % cols) * w, (i // cols) * h))
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out, "JPEG", quality=85)
    return len(tiles)


if __name__ == "__main__":
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("trim")
    p.add_argument("source")
    p.add_argument("--start", type=float, default=0)
    p.add_argument("--duration", type=float, default=cfg["clip"]["duration_s"])
    p = sub.add_parser("sheet")
    p.add_argument("video")
    p.add_argument("out")
    p.add_argument("--every", type=int, default=15)
    args = ap.parse_args()

    if args.cmd == "trim":
        trim(args.source, args.start, args.duration, ROOT / cfg["clip"]["path"])
        print(f"wrote {cfg['clip']['path']}")
    else:
        n = contact_sheet(Path(args.video), Path(args.out), args.every)
        print(f"wrote {args.out} ({n} tiles)")
