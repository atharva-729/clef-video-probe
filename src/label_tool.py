"""Local labelling interface. Standard library only.

  python src/label_tool.py            # then open http://localhost:8765

Reads and writes data/labels/labels.csv and data/labels/events_truth.csv directly
(autosaves on every change). Frames and the clip are served from data/.
"""
import csv
import json
import os
import re
import sys
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from clef_client import load_schema  # noqa: E402
from make_label_sheet import HINTS, NUMERIC  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CFG = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
SCHEMA = load_schema()
LABELS = ROOT / "data" / "labels" / "labels.csv"
EVENTS_CSV = ROOT / "data" / "labels" / "events_truth.csv"
FRAMES = ROOT / "data" / "frames"
CLIP = ROOT / CFG["clip"]["path"]
EVENTS = ["ignition", "liftoff", "booster_separation", "fairing_jettison", "payload_separation", "crossed_100km"]
GROUPS = [
    ("A. Layout", ["main_view", "telemetry_panel_visible", "trajectory_chart_visible", "ground_track_map_visible",
                   "control_room_inset_visible", "people_visible", "onscreen_text_language"]),
    ("B. Numbers", ["clock_state", "altitude_km", "speed_kms", "distance_km"]),
    ("C. Vehicle", ["vehicle_location", "side_boosters_attached", "fairing_attached", "engine_firing",
                    "payload_separated", "flight_phase"]),
    ("D. Editorial", ["highlight_worthy", "ad_break_safe"]),
]


def atomic_write(path, rows):
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
        csv.writer(fh).writerows(rows)
    os.replace(tmp, path)


def read_csv(path):
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.reader(fh))


def build_state():
    rows = read_csv(LABELS)
    header = rows[0]
    questions = []
    by_id = {q["id"]: q for q in SCHEMA["questions"]}
    for title, ids in GROUPS:
        for qid in ids:
            q = by_id[qid]
            col = NUMERIC.get(qid, qid)
            questions.append({
                "group": title, "id": qid, "col": col, "text": q["question"],
                "options": None if qid in NUMERIC else q["options"], "hint": HINTS.get(qid, ""),
            })
    events = {r[0]: r[1] for r in read_csv(EVENTS_CSV)[1:] if len(r) >= 2}
    return {
        "version": SCHEMA["version"],
        "questions": questions,
        "frames": [dict(zip(header, r)) for r in rows[1:]],
        "events": EVENTS,
        "event_times": events,
        "has_clip": CLIP.exists(),
    }


def save_frame(frame, values):
    rows = read_csv(LABELS)
    header = rows[0]
    for r in rows[1:]:
        if r[0] == frame:
            for col, val in values.items():
                if col in header and col not in ("frame", "t_seconds"):
                    r[header.index(col)] = str(val)
            atomic_write(LABELS, rows)
            return
    raise KeyError(frame)


def save_events(times):
    rows = [["event", "timestamp_s"]] + [[e, str(times[e])] for e in EVENTS if str(times.get(e, "")).strip() != ""]
    atomic_write(EVENTS_CSV, rows)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send_bytes(self, body, ctype, status=200, extra=None):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, obj, status=200):
        self.send_bytes(json.dumps(obj).encode(), "application/json", status)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/":
            self.send_bytes(PAGE.encode(), "text/html; charset=utf-8")
        elif path == "/api/state":
            self.send_json(build_state())
        elif re.fullmatch(r"/frames/f_[\w.]+\.jpg", path):
            f = FRAMES / path.split("/")[-1]
            if f.exists():
                self.send_bytes(f.read_bytes(), "image/jpeg")
            else:
                self.send_bytes(b"", "text/plain", 404)
        elif path == "/clip.mp4" and CLIP.exists():
            self.send_clip()
        else:
            self.send_bytes(b"not found", "text/plain", 404)

    def send_clip(self):
        size = CLIP.stat().st_size
        start, end = 0, size - 1
        m = re.match(r"bytes=(\d*)-(\d*)", self.headers.get("Range", ""))
        status = 200
        if m:
            status = 206
            if m.group(1):
                start = int(m.group(1))
            if m.group(2):
                end = min(int(m.group(2)), size - 1)
            if not m.group(1) and m.group(2):
                start, end = max(0, size - int(m.group(2))), size - 1
        with CLIP.open("rb") as fh:
            fh.seek(start)
            body = fh.read(end - start + 1)
        extra = {"Accept-Ranges": "bytes"}
        if status == 206:
            extra["Content-Range"] = f"bytes {start}-{end}/{size}"
        try:
            self.send_bytes(body, "video/mp4", status, extra)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        try:
            if self.path == "/api/label":
                save_frame(body["frame"], body["values"])
            elif self.path == "/api/events":
                save_events(body["times"])
            else:
                return self.send_json({"error": "not found"}, 404)
        except (KeyError, ValueError) as e:
            return self.send_json({"error": str(e)}, 400)
        self.send_json({"ok": True})


PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Clef labelling</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{--bg:#111418;--panel:#1b2027;--line:#2c343f;--fg:#e6e9ee;--mut:#8b95a3;--acc:#4da3ff;--ok:#3ecf8e;--warn:#f5a524}
*{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--fg);font:14px system-ui,sans-serif}
#app{display:grid;grid-template-columns:minmax(0,1.15fr) minmax(380px,1fr);height:100vh}
#left{display:flex;flex-direction:column;padding:10px;gap:8px;min-width:0}
#right{overflow-y:auto;padding:10px 14px;border-left:1px solid var(--line);background:var(--panel)}
#imgwrap{flex:1;min-height:0;display:flex;align-items:center;justify-content:center;background:#000;border-radius:6px}
#img{max-width:100%;max-height:100%;object-fit:contain}
#top{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
#title{font-size:18px;font-weight:600} #prog{color:var(--mut)}
button{background:#2a323d;color:var(--fg);border:1px solid var(--line);border-radius:6px;padding:5px 10px;cursor:pointer;font:inherit}
button:hover{border-color:var(--acc)}
#strip{display:flex;gap:2px;flex-wrap:wrap}
.cell{width:18px;height:14px;border-radius:2px;background:#2a323d;cursor:pointer;border:1px solid transparent}
.cell.part{background:#7a5a1a}.cell.done{background:#1f7a52}.cell.cur{border-color:#fff}
h3{margin:14px 0 6px;font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--acc)}
.q{padding:7px 0;border-bottom:1px solid var(--line)}
.qt{margin-bottom:5px} .qid{color:var(--mut);font-size:11px;margin-left:6px}
.hint{color:var(--mut);font-size:12px;margin-top:3px}
.opts{display:flex;flex-wrap:wrap;gap:4px}
.opt{padding:3px 8px;border-radius:12px;font-size:13px}
.opt.sel{background:var(--acc);border-color:var(--acc);color:#001a33;font-weight:600}
.opt.unsure.sel{background:var(--warn);border-color:var(--warn)}
input[type=text],input[type=number]{background:#0e1114;color:var(--fg);border:1px solid var(--line);border-radius:6px;padding:5px 8px;font:inherit;width:110px}
textarea{width:100%;background:#0e1114;color:var(--fg);border:1px solid var(--line);border-radius:6px;padding:6px;font:inherit}
.evrow{display:flex;gap:8px;align-items:center;margin:4px 0}.evrow label{width:150px}
video{width:100%;max-height:200px;background:#000;border-radius:6px}
#saved{color:var(--ok);font-size:12px;min-width:60px}
.k{background:#2a323d;border-radius:4px;padding:0 5px;font-size:12px}
</style></head><body>
<div id="app">
 <div id="left">
  <div id="top">
   <span id="title"></span><span id="prog"></span><span id="saved"></span>
   <button id="prev">&larr; Prev</button><button id="next">Next &rarr;</button>
   <button id="copy" title="key: C">Fill blanks from previous frame (C)</button>
   <button id="nextblank" title="key: N">Next unfinished (N)</button>
  </div>
  <div id="imgwrap"><img id="img" alt="frame"></div>
  <div id="strip"></div>
  <div><small style="color:var(--mut)"><span class="k">&larr;</span> <span class="k">&rarr;</span> step &middot;
   <span class="k">C</span> fill blanks from previous &middot; <span class="k">N</span> next unfinished &middot;
   every click saves to labels.csv &middot; click a selected option again to clear it</small></div>
 </div>
 <div id="right">
  <div id="qs"></div>
  <h3>Notes</h3><textarea id="notes" rows="2"></textarea>
  <h3>Event times (seconds from clip start)</h3>
  <div id="events"></div>
  <div style="margin:6px 0"><button id="vidbtn">Show clip player</button></div>
  <video id="vid" controls style="display:none"></video>
 </div>
</div>
<script>
let S, idx = 0;
const $ = id => document.getElementById(id);
const post = (u, b) => fetch(u, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(b)})
  .then(r => { if (!r.ok) throw new Error(r.status); $('saved').textContent = 'saved'; setTimeout(() => $('saved').textContent = '', 1200); })
  .catch(() => { $('saved').style.color = 'red'; $('saved').textContent = 'SAVE FAILED'; });
const cols = () => S.questions.map(q => q.col);
const filled = f => cols().filter(c => (f[c] || '').trim() !== '').length;

function setVal(col, val) {
  const f = S.frames[idx];
  f[col] = val;
  post('/api/label', {frame: f.frame, values: {[col]: val}});
  renderStrip();
}

function renderQs() {
  const f = S.frames[idx];
  let html = '', group = '';
  for (const q of S.questions) {
    if (q.group !== group) { group = q.group; html += `<h3>${group}</h3>`; }
    html += `<div class="q"><div class="qt">${q.text}<span class="qid">${q.col}</span></div>`;
    if (q.options) {
      html += '<div class="opts">' + [...q.options, '?'].map(o =>
        `<button class="opt${o === '?' ? ' unsure' : ''}${f[q.col] === o ? ' sel' : ''}" data-c="${q.col}" data-v="${o}">${o}</button>`).join('') + '</div>';
    } else {
      html += `<div class="opts"><input type="text" data-num="${q.col}" value="${f[q.col] || ''}" placeholder="number">
        <button class="opt${f[q.col] === 'none' ? ' sel' : ''}" data-c="${q.col}" data-v="none">none</button>
        <button class="opt unsure${f[q.col] === '?' ? ' sel' : ''}" data-c="${q.col}" data-v="?">?</button></div>`;
    }
    if (q.hint) html += `<div class="hint">${q.hint}</div>`;
    html += '</div>';
  }
  $('qs').innerHTML = html;
  $('qs').querySelectorAll('button.opt').forEach(b => b.onclick = () => {
    const c = b.dataset.c, v = b.dataset.v;
    setVal(c, S.frames[idx][c] === v ? '' : v);
    renderQs();
  });
  $('qs').querySelectorAll('input[data-num]').forEach(inp => {
    inp.onchange = () => { setVal(inp.dataset.num, inp.value.trim()); renderQs(); };
    inp.onkeydown = e => { if (e.key === 'Enter') inp.blur(); e.stopPropagation(); };
  });
  $('notes').value = f.notes || '';
}

function renderStrip() {
  const n = cols().length;
  $('strip').innerHTML = S.frames.map((f, i) => {
    const k = filled(f);
    return `<div class="cell ${k === n ? 'done' : k ? 'part' : ''} ${i === idx ? 'cur' : ''}" data-i="${i}" title="${f.t_seconds}s: ${k}/${n}"></div>`;
  }).join('');
  $('strip').querySelectorAll('.cell').forEach(c => c.onclick = () => go(+c.dataset.i));
  const done = S.frames.filter(f => filled(f) === n).length;
  $('prog').textContent = `${done}/${S.frames.length} frames complete`;
}

function go(i) {
  idx = Math.max(0, Math.min(S.frames.length - 1, i));
  const f = S.frames[idx], t = +f.t_seconds;
  $('img').src = '/frames/' + f.frame;
  $('title').textContent = `#${idx}  ${String(Math.floor(t / 60)).padStart(2, '0')}:${String(t % 60).padStart(2, '0')}  (${t} s)`;
  if ($('vid').style.display !== 'none') $('vid').currentTime = t;
  location.hash = idx;
  renderQs(); renderStrip();
}

function fillFromPrev() {
  if (idx === 0) return;
  const f = S.frames[idx], p = S.frames[idx - 1], values = {};
  for (const c of cols()) if (!(f[c] || '').trim() && (p[c] || '').trim()) { values[c] = p[c]; f[c] = p[c]; }
  if (Object.keys(values).length) post('/api/label', {frame: f.frame, values});
  renderQs(); renderStrip();
}

function nextBlank() {
  const n = cols().length;
  for (let k = 1; k <= S.frames.length; k++) {
    const i = (idx + k) % S.frames.length;
    if (filled(S.frames[i]) < n) return go(i);
  }
}

function renderEvents() {
  $('events').innerHTML = S.events.map(e => `<div class="evrow"><label>${e}</label>
    <input type="number" step="1" data-ev="${e}" value="${S.event_times[e] ?? ''}">
    <button data-set="${e}">= current frame</button></div>`).join('');
  const save = () => post('/api/events', {times: S.event_times});
  $('events').querySelectorAll('input').forEach(i => i.onchange = () => { S.event_times[i.dataset.ev] = i.value; save(); });
  $('events').querySelectorAll('button').forEach(b => b.onclick = () => {
    S.event_times[b.dataset.set] = S.frames[idx].t_seconds; save(); renderEvents();
  });
  $('events').querySelectorAll('input').forEach(i => i.onkeydown = e => e.stopPropagation());
}

$('prev').onclick = () => go(idx - 1);
$('next').onclick = () => go(idx + 1);
$('copy').onclick = fillFromPrev;
$('nextblank').onclick = nextBlank;
$('notes').onkeydown = e => e.stopPropagation();
$('notes').onchange = () => setVal('notes', $('notes').value);
$('vidbtn').onclick = () => {
  const v = $('vid');
  if (v.style.display === 'none') { v.src = '/clip.mp4'; v.style.display = 'block'; v.onloadedmetadata = () => v.currentTime = +S.frames[idx].t_seconds; $('vidbtn').textContent = 'Hide clip player'; }
  else { v.pause(); v.style.display = 'none'; $('vidbtn').textContent = 'Show clip player'; }
};
addEventListener('keydown', e => {
  if (e.key === 'ArrowRight') go(idx + 1);
  else if (e.key === 'ArrowLeft') go(idx - 1);
  else if (e.key === 'c' || e.key === 'C') fillFromPrev();
  else if (e.key === 'n' || e.key === 'N') nextBlank();
});

fetch('/api/state').then(r => r.json()).then(s => {
  S = s;
  if (!S.has_clip) $('vidbtn').style.display = 'none';
  renderEvents();
  go(Number(location.hash.slice(1)) || 0);
});
</script></body></html>
"""

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    print(f"Labelling tool: http://localhost:{port}  (Ctrl+C to stop)")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
