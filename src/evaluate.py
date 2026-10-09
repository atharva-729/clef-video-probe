"""Phase 4: score Clef's recorded answers against the hand labels.

  python src/evaluate.py runs/<run_id>      # default: the newest run

Writes runs/<run_id>/metrics.json, reports/accuracy.md and two PNG charts in reports/.
Free to re-run: it reads only files.
"""
import argparse
import csv
import json
import re
import statistics
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from clef_client import load_schema  # noqa: E402
from make_label_sheet import NUMERIC  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
GROUPS = {
    "A. Layout": ["main_view", "telemetry_panel_visible", "trajectory_chart_visible", "ground_track_map_visible",
                  "control_room_inset_visible", "people_visible", "onscreen_text_language"],
    "B. Numbers": ["clock_state", "altitude_km", "speed_kms", "distance_km"],
    "C. Vehicle": ["vehicle_location", "side_boosters_attached", "fairing_attached", "engine_firing",
                   "payload_separated", "flight_phase"],
    "D. Editorial": ["highlight_worthy", "ad_break_safe"],
}
CONF_BINS = [(0.0, 0.5), (0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.0001)]


def bucket(raw, options):
    """Raw number -> bucket option. Lower edge inclusive, upper exclusive; French commas normalised."""
    raw = raw.strip().lower()
    if raw == "none":
        return "none"
    x = float(raw.replace(",", "."))
    for o in options:
        if o == "none":
            continue
        if o.endswith("+"):
            if x >= float(o[:-1]):
                return o
        else:
            lo, hi = (float(p) for p in o.split("-"))
            if lo <= x < hi:
                return o
    return None


def macro_f1(truth, pred):
    f1s = []
    for c in set(truth):
        tp = sum(1 for t, p in zip(truth, pred) if t == c and p == c)
        fp = sum(1 for t, p in zip(truth, pred) if t != c and p == c)
        fn = sum(1 for t, p in zip(truth, pred) if t == c and p != c)
        f1s.append(2 * tp / (2 * tp + fp + fn) if tp else 0.0)
    return sum(f1s) / len(f1s)


def load_pairs(run_dir, schema):
    """Return {qid: [(frame, label, answer, confidence), ...]} with unsure ('?') labels dropped."""
    labels = {r["frame"]: r for r in csv.DictReader((ROOT / "data/labels/labels.csv").open(encoding="utf-8", newline=""))}
    answers = [json.loads(line) for line in (run_dir / "answers.jsonl").read_text(encoding="utf-8").splitlines() if line]
    pairs = defaultdict(list)
    for row in answers:
        lab = labels.get(row["frame"])
        if lab is None:
            continue
        for q in schema["questions"]:
            qid = q["id"]
            a = row["answers"].get(qid)
            raw = lab[NUMERIC.get(qid, qid)].strip()
            if a is None or raw in ("", "?"):
                continue
            truth = bucket(raw, q["options"]) if qid in NUMERIC else raw
            if truth is None:
                continue
            pairs[qid].append((row["frame"], truth, a["answer"], a["confidence"]))
    return pairs


def question_metrics(qid, rows, options):
    truth = [r[1] for r in rows]
    pred = [r[2] for r in rows]
    n = len(rows)
    acc = sum(t == p for t, p in zip(truth, pred)) / n
    baseline = Counter(truth).most_common(1)[0][1] / n
    m = {"n": n, "accuracy": acc, "majority_baseline": baseline, "macro_f1": macro_f1(truth, pred),
         "mean_confidence": sum(r[3] for r in rows) / n}
    if qid in NUMERIC:
        order = [o for o in options if o != "none"]
        near = sum(1 for t, p in zip(truth, pred)
                   if t in order and p in order and abs(order.index(t) - order.index(p)) == 1)
        m["near_miss_rate"] = near / n
    return m


def confusion(rows, options):
    cm = {t: Counter() for t in options}
    for _, t, p, _ in rows:
        cm[t][p] += 1
    used = [o for o in options if any(cm[o].values()) or any(cm[t][o] for t in options)]
    return used, cm


def md_table(header, rows):
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def pct(x):
    return f"{100 * x:.0f}%"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("run_dir", nargs="?")
    args = ap.parse_args()
    runs = sorted(p for p in (ROOT / "runs").glob("run_*") if (p / "answers.jsonl").exists())
    run_dir = Path(args.run_dir) if args.run_dir else (runs[-1] if runs else None)
    if run_dir is None:
        raise SystemExit("no run with answers.jsonl found under runs/")
    schema = load_schema()
    options = {q["id"]: q["options"] for q in schema["questions"]}
    pairs = load_pairs(run_dir, schema)
    meta = json.loads((run_dir / "run_meta.json").read_text(encoding="utf-8"))

    per_q = {qid: question_metrics(qid, rows, options[qid]) for qid, rows in pairs.items()}
    group_acc = {}
    for g, ids in GROUPS.items():
        cells = [r for qid in ids for r in pairs.get(qid, [])]
        group_acc[g] = sum(r[1] == r[2] for r in cells) / len(cells) if cells else None

    cells = [r for rows in pairs.values() for r in rows]
    calib = []
    for lo, hi in CONF_BINS:
        b = [r for r in cells if lo <= r[3] < hi]
        calib.append({"bin": f"{lo:.1f}-{min(hi, 1.0):.1f}", "n": len(b),
                      "mean_confidence": sum(r[3] for r in b) / len(b) if b else None,
                      "accuracy": sum(r[1] == r[2] for r in b) / len(b) if b else None})

    wrong = Counter()
    wrong_qs = defaultdict(list)
    for qid, rows in pairs.items():
        for frame, t, p, _ in rows:
            if t != p:
                wrong[frame] += 1
                wrong_qs[frame].append(f"{qid} (label {t}, Clef {p})")
    worst = wrong.most_common(10)

    latencies = []
    for f in (run_dir / "raw").glob("*.json"):
        lat = json.loads(f.read_text(encoding="utf-8")).get("_meta", {}).get("latency_s")
        if lat:
            latencies.append(lat)
    costs = [json.loads(f.read_text(encoding="utf-8")).get("usage", {}) for f in (run_dir / "raw").glob("*.json")]
    total_cost = sum(c.get("cost", 0) or 0 for c in costs)
    total_tokens = sum(c.get("input_tokens", 0) or 0 for c in costs)

    metrics = {"run_id": meta["run_id"], "schema_version": meta["schema_version"], "per_question": per_q,
               "group_accuracy": group_acc, "calibration": calib, "worst_frames": worst,
               "cost_usd_all_frames": total_cost, "input_tokens_all_frames": total_tokens,
               "latency_median_s": statistics.median(latencies) if latencies else None,
               "latency_p95_s": sorted(latencies)[max(0, int(len(latencies) * 0.95) - 1)] if latencies else None}
    (run_dir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    reports = ROOT / "reports"
    reports.mkdir(exist_ok=True)
    qids = [q for ids in GROUPS.values() for q in ids if q in per_q]

    # charts
    fig, ax = plt.subplots(figsize=(10, 5))
    xs = range(len(qids))
    ax.bar([x - 0.2 for x in xs], [per_q[q]["accuracy"] for q in qids], 0.4, label="Clef accuracy")
    ax.bar([x + 0.2 for x in xs], [per_q[q]["majority_baseline"] for q in qids], 0.4, label="majority baseline", color="#bbb")
    ax.set_xticks(list(xs))
    ax.set_xticklabels(qids, rotation=70, ha="right")
    ax.set_ylim(0, 1.05)
    ax.legend()
    ax.set_title("Accuracy vs majority baseline")
    fig.tight_layout()
    fig.savefig(reports / "accuracy_vs_baseline.png", dpi=110)
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(5, 5))
    pts = [(c["mean_confidence"], c["accuracy"]) for c in calib if c["n"]]
    ax.plot([0, 1], [0, 1], "--", color="#999")
    ax.plot([p[0] for p in pts], [p[1] for p in pts], "o-")
    ax.set_xlabel("mean confidence")
    ax.set_ylabel("accuracy")
    ax.set_title("Calibration")
    fig.tight_layout()
    fig.savefig(reports / "calibration.png", dpi=110)
    plt.close(fig)

    # report
    L = [f"# Accuracy report: {meta['run_id']}", "",
         f"Model `{meta['model']}`, schema v{meta['schema_version']}, {meta['frames']} frames, {len(cells)} scored answers.", "",
         "**About the labels.** The labels were first drafted by Claude (Sonnet) from the frames and then reviewed and "
         "corrected by the maintainer. Frames or cells labelled `?` are excluded. `flight_phase` is labelled from the "
         "frame alone (no timing inference), the same information Clef gets.", "",
         "## Summary", "",
         md_table(["Question", "n", "Accuracy", "Majority baseline", "Macro-F1", "Near-miss"],
                  [[q, per_q[q]["n"], pct(per_q[q]["accuracy"]), pct(per_q[q]["majority_baseline"]),
                    f"{per_q[q]['macro_f1']:.2f}", pct(per_q[q]["near_miss_rate"]) if "near_miss_rate" in per_q[q] else ""]
                   for q in qids]),
         "", "A question only \"works\" if Clef clearly beats its majority baseline.", "",
         "## By group", "",
         md_table(["Group", "Accuracy (pooled)"], [[g, pct(a) if a is not None else "n/a"] for g, a in group_acc.items()]),
         "", "![accuracy vs baseline](accuracy_vs_baseline.png)", ""]
    for qid in ("main_view", "flight_phase"):
        if qid in pairs:
            used, cm = confusion(pairs[qid], options[qid])
            L += [f"## Confusion matrix: {qid}", "", "Rows = label, columns = Clef.", "",
                  md_table(["label \\ Clef"] + used, [[t] + [cm[t][p] or "" for p in used] for t in used]), ""]
    L += ["## Calibration", "",
          md_table(["Confidence bin", "n", "Mean confidence", "Accuracy"],
                   [[c["bin"], c["n"], f"{c['mean_confidence']:.2f}" if c["n"] else "", pct(c["accuracy"]) if c["n"] else ""]
                    for c in calib]),
          "", "![calibration](calibration.png)", "", "## 10 worst frames", "",
          md_table(["Frame", "Wrong answers", "Which"],
                   [[f"data/frames/{f}", n, "; ".join(wrong_qs[f][:4]) + (" ..." if len(wrong_qs[f]) > 4 else "")]
                    for f, n in worst]),
          "", "## Cost and latency", "",
          f"- Input tokens, all frames: {total_tokens:,}", f"- Cost, all frames: ${total_cost:.4f}"
          + (f" (${total_cost / meta['frames'] * 12:.4f} per minute of video at 5 s sampling)" if meta["frames"] else ""),
          f"- Latency: median {metrics['latency_median_s']} s, p95 {metrics['latency_p95_s']} s "
          "(measured on frames called in this or an earlier run)", ""]
    (reports / "accuracy.md").write_text("\n".join(L), encoding="utf-8")
    print(f"wrote reports/accuracy.md, charts and {run_dir.name}/metrics.json")
    print(md_table(["Group", "Acc"], [[g, pct(a) if a is not None else "n/a"] for g, a in group_acc.items()]))


if __name__ == "__main__":
    main()
