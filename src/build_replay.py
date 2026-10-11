"""Phase 6: build the replay page from a recorded run. No API calls.

  python src/build_replay.py [runs/<run_id>]     # default: the latest run
  python -m http.server 8000                     # from the repo root
  open http://localhost:8000/replay/

Writes replay/timeline.json (per frame: time, answers, confidences, labels; plus events) and
replay/index.html. Run detect_events.py first; the page reads only these files.
"""
import argparse
import csv
import json
import os
from pathlib import Path

from clef_client import load_config, load_schema
from evaluate import bucket
from make_label_sheet import NUMERIC

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "replay"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_dir", nargs="?")
    args = ap.parse_args()
    runs = sorted(p for p in (ROOT / "runs").glob("run_*") if (p / "events.json").exists())
    run_dir = Path(args.run_dir) if args.run_dir else (runs[-1] if runs else None)
    if run_dir is None or not (run_dir / "events.json").exists():
        raise SystemExit("no run with events.json found (run src/detect_events.py first)")
    cfg = load_config()
    schema = load_schema()
    meta = json.loads((run_dir / "run_meta.json").read_text(encoding="utf-8"))
    ev = json.loads((run_dir / "events.json").read_text(encoding="utf-8"))
    cost = sum(json.loads(f.read_text(encoding="utf-8")).get("usage", {}).get("cost", 0) or 0
               for f in (run_dir / "raw").glob("*.json"))
    with (ROOT / "data/labels/labels.csv").open(encoding="utf-8", newline="") as fh:
        labels = {r["frame"]: r for r in csv.DictReader(fh)}
    with (ROOT / "data/labels/events_truth.csv").open(encoding="utf-8", newline="") as fh:
        truth_events = {r["event"]: float(r["timestamp_s"]) for r in csv.DictReader(fh) if r["timestamp_s"].strip()}

    frames = []
    for line in (run_dir / "answers.jsonl").read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        row = json.loads(line)
        lab = labels.get(row["frame"], {})
        truth = {}
        for q in schema["questions"]:
            raw = (lab.get(NUMERIC.get(q["id"], q["id"])) or "").strip()
            if raw in ("", "?"):
                continue
            t = bucket(raw, q["options"]) if q["id"] in NUMERIC else raw
            if t is not None:
                truth[q["id"]] = t
        frames.append({"t": row["t_seconds"], "frame": row["frame"], "truth": truth,
                       "answers": {qid: {"a": a["answer"], "c": round(a["confidence"], 3)}
                                   for qid, a in row["answers"].items()}})
    frames.sort(key=lambda f: f["t"])

    timeline = {
        "meta": {"run_id": meta["run_id"], "model": meta["model"], "schema_version": meta["schema_version"],
                 "cost_usd": round(cost, 4), "frames": len(frames), "sample_interval_s": cfg["sample_interval_s"],
                 "duration_s": cfg["clip"]["duration_s"], "min_conf": ev["min_conf"],
                 "persist_frames": ev["persist_frames"],
                 "video": os.path.relpath(ROOT / cfg["clip"]["path"], OUT).replace("\\", "/")},
        "frames": frames,
        "events": [{"event": e["event"], "t": e["t_seconds"], "evidence": e["evidence"]} for e in ev["events"]],
        "truth_events": truth_events,
    }
    OUT.mkdir(exist_ok=True)
    (OUT / "timeline.json").write_text(json.dumps(timeline), encoding="utf-8")
    (OUT / "index.html").write_text(PAGE, encoding="utf-8")
    print(f"wrote replay/index.html and replay/timeline.json from {run_dir.name} "
          f"({len(frames)} frames, {len(timeline['events'])} events)")


PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Clef replay</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{--bg:#111418;--panel:#1b2027;--line:#2c343f;--fg:#e6e9ee;--mut:#8b95a3;--acc:#4da3ff;--ok:#3ecf8e;--warn:#f5a524;--bad:#ff5c5c}
*{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--fg);font:14px system-ui,sans-serif}
#app{display:grid;grid-template-columns:minmax(0,1.6fr) minmax(330px,1fr);gap:14px;padding:14px;max-width:1500px;margin:0 auto}
@media(max-width:900px){#app{grid-template-columns:1fr}}
video{width:100%;aspect-ratio:1080/606;background:#000;border-radius:6px;display:block}
#strip{position:relative;height:34px;margin-top:8px;background:var(--panel);border:1px solid var(--line);border-radius:6px;cursor:pointer}
#head{position:absolute;top:0;bottom:0;width:2px;background:#fff;pointer-events:none}
.mk{position:absolute;top:3px;bottom:3px;width:4px;margin-left:-2px;border-radius:2px;background:var(--acc)}
.mk.scene{background:var(--mut);top:12px;bottom:12px}
.mk.true{background:none;border:1px dashed var(--ok);display:none}
body.truth .mk.true{display:block}
#legend{color:var(--mut);font-size:12px;margin-top:6px}
#side{background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:12px 14px;min-width:0}
h3{margin:14px 0 8px;font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--acc)}
h3:first-child{margin-top:0}
#live{float:right;color:var(--mut);font-size:12px;text-transform:none;letter-spacing:0}
.row{display:grid;grid-template-columns:118px 1fr 44px;gap:8px;align-items:center;padding:5px 6px;border-radius:4px}
.row .k{color:var(--mut)} .row .v{font-weight:600;overflow-wrap:anywhere}
.row .c{text-align:right;color:var(--mut);font-variant-numeric:tabular-nums}
.bar{grid-column:1/-1;height:3px;background:#2a323d;border-radius:2px}
.bar i{display:block;height:100%;border-radius:2px;background:var(--ok)}
.row.low .v{color:var(--mut);font-weight:400} .row.low .bar i{background:var(--warn)}
.lab{display:none;font-weight:400;font-size:12px}
body.truth .row.wrong{background:rgba(255,92,92,.14)} body.truth .row.wrong .v{color:var(--bad)}
body.truth .row.wrong .lab{display:block;color:var(--fg)}
#log{min-height:70px} .ev{padding:6px 8px;border-radius:4px;cursor:pointer;display:flex;gap:8px}
.ev:hover{background:#2a323d} .ev .t{margin-left:auto;color:var(--mut);font-variant-numeric:tabular-nums}
.ev small{color:var(--mut)} .empty{color:var(--mut);padding:6px 8px}
label{cursor:pointer;user-select:none} #foot{color:var(--mut);font-size:12px;margin-top:14px;line-height:1.5}
#msg{color:var(--mut);font-size:12px;margin-top:6px}
</style></head><body>
<div id="app">
 <div>
  <video id="vid" controls playsinline></video>
  <div id="strip"><div id="head"></div></div>
  <div id="legend">Blue: detected event &middot; grey: scene change &middot; dashed green (with ground truth on): true event time.
   Click the strip or an event to jump.</div>
  <div id="msg">Loading clip&hellip;</div>
 </div>
 <div id="side">
  <h3>Now <span id="live"></span></h3>
  <div id="now"></div>
  <h3>Events</h3>
  <div id="log"></div>
  <h3>Ground truth</h3>
  <label><input type="checkbox" id="truth"> Show ground truth (answers that disagree with the hand labels turn red)</label>
  <div id="score" style="color:var(--mut);margin-top:4px"></div>
  <div id="foot"></div>
 </div>
</div>
<script>
const $ = id => document.getElementById(id);
const NOW = [['main_view', 'Main view', ''], ['flight_phase', 'Flight phase', ''], ['altitude_km', 'Altitude', ' km'],
  ['speed_kms', 'Speed', ' km/s'], ['distance_km', 'Distance', ' km'], ['side_boosters_attached', 'Side boosters', ''],
  ['fairing_attached', 'Fairing', ''], ['engine_firing', 'Engine flame', '']];
const EVENTS = {ignition: ['🔥', 'Ignition'], liftoff: ['🚀', 'Liftoff'], booster_separation: ['💥', 'Booster separation'],
  fairing_jettison: ['🛰️', 'Fairing jettison'], payload_separation: ['🔭', 'Payload separation'],
  crossed_100km: ['🌌', 'Crossed 100 km'], scene_change: ['🎬', 'Scene change']};
const clock = t => `${String(Math.floor(t / 60)).padStart(2, '0')}:${String(Math.floor(t % 60)).padStart(2, '0')}`;
const nice = (v, unit) => /\d/.test(v) ? v + unit : v.replace(/_/g, ' ');
let T, shown = -1, logged = -1;
const v = $('vid');

function frameAt(t) {
  let i = -1;
  while (i + 1 < T.frames.length && T.frames[i + 1].t <= t) i++;
  return i;
}

function renderNow(i) {
  const f = T.frames[i];
  $('live').textContent = f ? `frame at ${clock(f.t)}` : '';
  if (!f) { $('now').innerHTML = '<div class="empty">Waiting for the first frame.</div>'; $('score').textContent = ''; return; }
  let wrong = 0, scored = 0;
  $('now').innerHTML = NOW.map(([q, name, unit]) => {
    const a = f.answers[q], lab = f.truth[q];
    const bad = lab !== undefined && lab !== a.a;
    if (lab !== undefined) { scored++; wrong += bad; }
    return `<div class="row${a.c < T.meta.min_conf ? ' low' : ''}${bad ? ' wrong' : ''}"><span class="k">${name}</span>
      <span class="v">${nice(a.a, unit)}<span class="lab">label: ${bad ? nice(lab, unit) : ''}</span></span>
      <span class="c">${Math.round(a.c * 100)}%</span><div class="bar"><i style="width:${a.c * 100}%"></i></div></div>`;
  }).join('');
  $('score').textContent = `This frame: ${scored - wrong} of ${scored} shown answers match the labels.`;
}

function renderLog(t) {
  const n = T.events.filter(e => e.t <= t).length;
  if (n === logged) return;
  logged = n;
  $('log').innerHTML = n ? T.events.filter(e => e.t <= t).reverse().map(e => {
    const [icon, name] = EVENTS[e.event] || ['•', e.event];
    return `<div class="ev" data-t="${e.t}"><span>${icon}</span><span>${name}<br>
      <small>${e.evidence.question}: ${e.evidence.from} &rarr; ${e.evidence.to}</small></span><span class="t">${clock(e.t)}</span></div>`;
  }).join('') : '<div class="empty">No events detected yet.</div>';
  $('log').querySelectorAll('.ev').forEach(d => d.onclick = () => { v.currentTime = +d.dataset.t; });
}

function tick() {
  const t = v.currentTime || 0;
  $('head').style.left = `${Math.min(100, t / T.meta.duration_s * 100)}%`;
  const i = frameAt(t);
  if (i !== shown) { shown = i; renderNow(i); }
  renderLog(t);
}

function setup() {
  const m = T.meta, pos = t => `left:${t / m.duration_s * 100}%`;
  $('strip').insertAdjacentHTML('beforeend',
    T.events.map(e => `<div class="mk${e.event === 'scene_change' ? ' scene' : ''}" style="${pos(e.t)}" title="${(EVENTS[e.event] || [0, e.event])[1]} ${clock(e.t)}"></div>`).join('') +
    Object.entries(T.truth_events).map(([e, t]) => `<div class="mk true" style="${pos(t)}" title="true ${e} ${clock(t)}"></div>`).join(''));
  $('strip').onclick = e => { const r = $('strip').getBoundingClientRect(); v.currentTime = (e.clientX - r.left) / r.width * m.duration_s; };
  $('truth').onchange = () => document.body.classList.toggle('truth', $('truth').checked);
  $('foot').innerHTML = `Model <b>${m.model}</b> &middot; schema v${m.schema_version} &middot; run ${m.run_id} &middot;
    ${m.frames} frames, one every ${m.sample_interval_s} s &middot; cost of this run $${m.cost_usd.toFixed(3)}<br>
    Recorded once and replayed from files; no model is called while this page plays. An answer below ${Math.round(m.min_conf * 100)}%
    confidence is shown dimmed and cannot trigger an event.<br>
    Video: Complete Webb Telescope Launch Broadcast, NASA Goddard Space Flight Center Scientific Visualization Studio
    (svs.gsfc.nasa.gov/14060). Not endorsed by NASA, ESA or CNES.`;
  const want = new URLSearchParams(location.hash.slice(1));
  if (want.get('truth')) { $('truth').checked = true; document.body.classList.add('truth'); }
  v.addEventListener('loadedmetadata', () => { $('msg').textContent = ''; if (want.get('t')) v.currentTime = +want.get('t'); });
  ['timeupdate', 'seeking', 'seeked'].forEach(n => v.addEventListener(n, tick));
  // python -m http.server cannot serve byte ranges, so load the whole clip first; otherwise seeking fails.
  fetch(m.video).then(r => { if (!r.ok) throw new Error(r.status); return r.blob(); })
    .then(b => { v.src = URL.createObjectURL(b); })
    .catch(() => { v.src = m.video; $('msg').textContent = 'Could not preload the clip; seeking may not work.'; });
  tick();
}

fetch('timeline.json').then(r => r.json()).then(t => { T = t; setup(); })
  .catch(() => { $('msg').textContent = 'Could not load timeline.json. Serve the repo root with: python -m http.server'; });
</script></body></html>
"""

if __name__ == "__main__":
    main()
