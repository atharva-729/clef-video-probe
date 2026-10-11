"""Phase 5: turn Clef's per-frame answers into events and score them. No API calls.

  python src/detect_events.py [runs/<run_id>]     # default: the latest run

An answer is trusted if its confidence is at least `min_conf` and it is not an escape option.
A state changes only when a new trusted value holds for `persist_frames` frames in a row;
untrusted and escape answers are skipped, they neither start nor break a streak. The event
time is the first frame of the new state. Writes runs/<run_id>/events.json and the
"Event detection" section of reports/accuracy.md (run evaluate.py first; it rewrites the report).
"""
import argparse
import csv
import json
from pathlib import Path

from clef_client import load_config, load_schema
from evaluate import md_table

ROOT = Path(__file__).resolve().parent.parent
NO_INFO = {"cant_tell", "not_visible", "none"}
TRANSITIONS = {  # event: (question, from, to)
    "ignition": ("engine_firing", "no", "yes"),  # not clock_state: the clock is off screen at T0 in this clip
    "liftoff": ("vehicle_location", "on_pad", "in_flight"),
    "booster_separation": ("side_boosters_attached", "attached", "separated"),
    "fairing_jettison": ("fairing_attached", "attached", "jettisoned"),
    "payload_separation": ("payload_separated", "no", "yes"),
}
SCORED = [*TRANSITIONS, "crossed_100km"]
SECTION = "## Event detection"


def stable_changes(rows, qid, min_conf, persist):
    """Yield (old, new, first_row, confidences) each time the smoothed state of `qid` changes."""
    state, cand, streak = None, None, []
    for row in rows:
        a = row["answers"].get(qid)
        if a is None or a["confidence"] < min_conf or a["answer"] in NO_INFO:
            continue
        if a["answer"] == state:
            cand, streak = None, []
            continue
        if a["answer"] != cand:
            cand, streak = a["answer"], []
        streak.append((row, a["confidence"]))
        if len(streak) >= persist:
            yield state, cand, streak[0][0], [round(c, 3) for _, c in streak]
            state, cand, streak = cand, None, []


def detect(rows, schema, min_conf, persist):
    events = []

    def add(name, qid, old, new, row, confs):
        events.append({"event": name, "t_seconds": row["t_seconds"], "frame": row["frame"],
                       "evidence": {"question": qid, "from": old, "to": new, "confidences": confs}})

    for name, (qid, old, new) in TRANSITIONS.items():
        for was, now, row, confs in stable_changes(rows, qid, min_conf, persist):
            if (was, now) == (old, new):
                add(name, qid, was, now, row, confs)
    buckets = next(q["options"] for q in schema["questions"] if q["id"] == "altitude_km")
    for was, now, row, confs in stable_changes(rows, "altitude_km", min_conf, persist):
        if buckets.index(now) >= buckets.index("100-200"):
            add("crossed_100km", "altitude_km", was, now, row, confs)
            break
    for was, now, row, confs in stable_changes(rows, "main_view", min_conf, persist):
        if was is not None:
            add("scene_change", "main_view", was, now, row, confs)
    return sorted(events, key=lambda e: e["t_seconds"])


def score(events, truth, tolerance_s):
    """Per scored event: the detection nearest the true time is a hit if within tolerance; the rest are false positives."""
    out = []
    for name in SCORED:
        times = [e["t_seconds"] for e in events if e["event"] == name]
        true_t = truth.get(name)
        hit = None
        if true_t is not None and times:
            nearest = min(times, key=lambda t: abs(t - true_t))
            if abs(nearest - true_t) <= tolerance_s:
                hit = nearest
        out.append({"event": name, "true_t": true_t, "detected": times, "hit_t": hit,
                    "error_s": hit - true_t if hit is not None else None,
                    "missed": true_t is not None and hit is None,
                    "false_positives": len(times) - (hit is not None)})
    return out


def totals(scored):
    return (sum(s["hit_t"] is not None for s in scored), sum(s["missed"] for s in scored),
            sum(s["false_positives"] for s in scored))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_dir", nargs="?")
    args = ap.parse_args()
    runs = sorted(p for p in (ROOT / "runs").glob("run_*") if (p / "answers.jsonl").exists())
    run_dir = Path(args.run_dir) if args.run_dir else (runs[-1] if runs else None)
    if run_dir is None:
        raise SystemExit("no run with answers.jsonl found under runs/")
    cfg = load_config()
    schema = load_schema()
    min_conf, persist = cfg["events"]["min_conf"], cfg["events"]["persist_frames"]
    tolerance = cfg["events"]["hit_tolerance_intervals"] * cfg["sample_interval_s"]
    rows = [json.loads(line) for line in (run_dir / "answers.jsonl").read_text(encoding="utf-8").splitlines() if line]
    rows.sort(key=lambda r: r["t_seconds"])
    with (ROOT / "data/labels/events_truth.csv").open(encoding="utf-8", newline="") as fh:
        truth = {r["event"]: float(r["timestamp_s"]) for r in csv.DictReader(fh) if r["timestamp_s"].strip()}

    events = detect(rows, schema, min_conf, persist)
    scored = score(events, truth, tolerance)
    hits, misses, fps = totals(scored)
    grid = {(c, p): totals(score(detect(rows, schema, c, p), truth, tolerance))
            for c in (0.5, 0.6, 0.7) for p in (1, 2, 3)}
    best = min(grid, key=lambda k: (-grid[k][0], grid[k][2], k != (min_conf, persist)))

    (run_dir / "events.json").write_text(json.dumps({
        "run_id": run_dir.name, "min_conf": min_conf, "persist_frames": persist, "tolerance_s": tolerance,
        "events": events, "scoring": scored,
        "sensitivity": [{"min_conf": c, "persist_frames": p, "hits": h, "misses": m, "false_positives": f}
                        for (c, p), (h, m, f) in grid.items()],
    }, indent=2), encoding="utf-8")

    def outcome(s):
        if s["hit_t"] is not None:
            return "hit"
        if s["missed"]:
            return "miss"
        return "false positive" if s["detected"] else "correctly absent"

    L = [SECTION, "",
         f"Settings: `min_conf` {min_conf}, `persist_frames` {persist}, hit tolerance ±{tolerance:g} s. "
         f"**{hits} of {len(truth)} true events hit, {misses} missed, {fps} false positives.**", "",
         md_table(["Event", "True time (s)", "Detected at (s)", "Outcome", "Timing error (s)", "False positives"],
                  [[s["event"], f"{s['true_t']:g}" if s["true_t"] is not None else "not in clip",
                    ", ".join(f"{t:g}" for t in s["detected"]) or "none", outcome(s),
                    f"{s['error_s']:+g}" if s["error_s"] is not None else "", s["false_positives"]] for s in scored]),
         "", "The event time is the first sampled frame of the new state, so a detection is late by up to one "
         "sampling interval, plus any frames skipped because the question had no trusted answer.", "",
         f"`scene_change` (not scored) fired {sum(e['event'] == 'scene_change' for e in events)} times.", "",
         "### Sensitivity", "", "Each cell is hits / misses / false positives over the scored events.", "",
         md_table(["min_conf \\ persist_frames", "1", "2", "3"],
                  [[c] + ["{} / {} / {}".format(*grid[(c, p)]) for p in (1, 2, 3)] for c in (0.5, 0.6, 0.7)]),
         "", f"Most hits with fewest false positives: `min_conf` {best[0]}, `persist_frames` {best[1]}.", ""]
    report = ROOT / "reports" / "accuracy.md"
    text = report.read_text(encoding="utf-8") if report.exists() else ""
    report.write_text(text.split(SECTION)[0].rstrip("\n") + "\n\n" + "\n".join(L), encoding="utf-8")
    print("\n".join(L))
    print(f"wrote {run_dir.name}/events.json and the Event detection section of reports/accuracy.md")


if __name__ == "__main__":
    main()
