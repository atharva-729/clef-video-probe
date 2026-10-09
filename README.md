# Clef Video Probe

**Can a vision decision model watch a broadcast and tell us, frame by frame, what is happening, accurately enough to drive something a viewer sees live?**

This repo answers that for one 5½-minute clip of the **James Webb Space Telescope launch broadcast (NASA/ESA, 25 Dec 2021)**, using **Cloudflare's Clef** decision model. We:

1. sample frames from the clip,
2. ask Clef a fixed set of multiple-choice questions about each frame,
3. score its answers against hand-made labels,
4. turn changes in its answers into **detected events** (liftoff, booster separation, fairing jettison, …),
5. save everything once (**record**) and play it back in sync with the video (**replay**). The demo looks live, but tokens are spent only once.

> **For Claude Code:** this README is also your work plan. Work through the phases **in order**. At the end of every phase, **stop at the checkpoint**, print the checkpoint report, and **wait for the maintainer to reply "go"** before starting the next phase. Read [Rules for Claude Code](#rules-for-claude-code) before doing anything.

---

## Contents

- [Why this exists](#why-this-exists)
- [The source video](#the-source-video)
- [How it works](#how-it-works)
- [Repo layout](#repo-layout)
- [The question schema](#the-question-schema)
- [Logic: buckets, scoring, events](#logic-buckets-scoring-events)
- [Phases](#phases)
- [Rules for Claude Code](#rules-for-claude-code)
- [Business angle](#business-angle)
- [Credits and licensing](#credits-and-licensing)

---

## Why this exists

Text-based fan-reaction analysis is already being worked on elsewhere. The open question is **images**: given only what is on screen, can a model extract information useful enough to show in real time, independent of any social-media signal?

A launch broadcast is a good first test because one frame contains a lot of checkable information: telemetry numbers (altitude, distance, speed), a trajectory chart, a ground-track map, a control-room inset, and either live camera footage or an animation of the vehicle. The **pipeline is domain-agnostic**: swap the question schema and the same code works on a cricket broadcast, a travel vlog, or a publisher's video archive.

### What "done" looks like

1. **A replay page:** the video plays with a side panel showing Clef's current answers and a log of auto-detected events.
2. **An accuracy report:** per-question accuracy against hand labels, event detection hit rate and timing error, cost, and latency.
3. **A short pitch summary:** what works, what doesn't, and where it could make money.

---

## The source video

| | |
|---|---|
| Title | Complete Webb Telescope Launch Broadcast |
| Publisher | NASA Goddard Space Flight Center, Scientific Visualization Studio |
| Page | https://svs.gsfc.nasa.gov/14060 (API: https://svs.gsfc.nasa.gov/api/14060) |
| Clean-feed version (no graphics, not used) | https://svs.gsfc.nasa.gov/14061 |
| Recommended download | `14060_Webb_Full_Launch_Broadcast_<part>.webmhd.webm` (1080×606, lightest) |

The broadcast comes in three parts; liftoff is expected in **Part 2**. The video file is **downloaded manually by the maintainer** and placed at `data/raw/`. It is never committed.

**Clip window:** 5:30 (330 s), starting 61 s before T0 (the mission clock reaching zero, at 61 s into the clip). It includes ignition, liftoff, side-booster separation (≈ T+2:20) and fairing jettison (≈ T+3:10). Take true event times from the video itself.

---

## How it works

```
video ──ffmpeg──▶ frames (every 5 s) ──▶ Clef (frame + questions) ──▶ answers.jsonl  (RECORD, cached)
                        │                                                    │
                        └──▶ labels.csv (human) ──────▶ evaluate ◀───────────┤
                                                                            ▼
                                                     events.json ──▶ replay page (video + live panel)
```

**Clef in one paragraph.** Clef is a 27B multimodal *decision* model (post-trained from Qwen3.8-27B). It does not write prose. You give it a **state** (text, optionally images or video frames) and a **schema of typed questions** with allowed options, and it returns a **probability for every option of every question** in one forward pass. It is available on Cloudflare Workers AI (`@cf/cloudflare/clef`), on OpenRouter (`cloudflare/clef`, via the **Decisions API**, *not* the chat-completions endpoint), and as Apache-2.0 weights. A smaller **Clef-Flash** (9B) variant exists. Pricing at the time of writing: Clef $0.24 / M input tokens, Clef-Flash $0.09 / M, output $0.

---

## Repo layout

```
clef-video-probe/
├── README.md                ← this file
├── .env.example             ← OPENROUTER_API_KEY=, BUDGET_USD=2.00
├── .gitignore               ← data/raw, runs/, .env, __pycache__
├── requirements.txt
├── config.yaml              ← clip window, sample interval, model id, thresholds
├── schema/
│   └── questions.yaml       ← THE question schema (versioned)
├── docs/
│   ├── api_notes.md         ← Phase 0: confirmed request/response shape
│   └── SOURCE.md            ← exact source file, timestamps, attribution
├── data/
│   ├── raw/                 ← original download (git-ignored)
│   ├── clip/clip.mp4        ← 5:30 trimmed clip (committed)
│   ├── frames/              ← sampled JPGs (committed)
│   └── labels/labels.csv    ← hand labels (committed)
├── src/
│   ├── clef_client.py       ← one function: ask(frame, state, schema) → answers
│   ├── prepare_clip.py      ← trim + sample frames + contact sheet
│   ├── make_label_sheet.py  ← labels.csv template
│   ├── run_clef.py          ← RECORD: dry-run cost estimate, cached calls
│   ├── evaluate.py          ← accuracy, near-miss, calibration, baselines
│   ├── detect_events.py     ← smoothing + transition rules → events.json
│   └── build_replay.py      ← writes replay/index.html + replay/timeline.json
├── runs/<run_id>/           ← raw responses, answers.jsonl, metrics (git-ignored)
├── reports/                 ← committed summaries (markdown + small charts)
└── replay/                  ← the demo page
```

Python 3.11, `ffmpeg` on PATH. Keep dependencies minimal: `httpx`, `pyyaml`, `pandas`, `python-dotenv`, `pillow`.

---

## The question schema

All questions are **single-choice**. Every question includes an escape option (`none`, `cant_tell`, or `not_visible`) so Clef is never forced to guess. Store this verbatim in `schema/questions.yaml`; bump `version` on any change.

```yaml
version: 2
state: >
  This image is a single frame from a live TV broadcast of a rocket launch
  (Ariane 5 carrying the James Webb Space Telescope). On-screen text may be in
  French and numbers may use a comma as the decimal separator (e.g. "2,92").
  The main area may show live camera footage, a computer animation of the
  rocket, a control room, a studio presenter, or a map. Smaller insets may
  appear along the bottom. The telescope stays attached to the rocket's upper
  stage after the nose fairing is jettisoned; it separates much later, so
  seeing the telescope after fairing jettison does not mean it has separated.
  Answer only from what is visible in this frame.

questions:

  # ── A. Layout: what is on screen ─────────────────────────────────────────
  - id: main_view
    question: What does the main (largest) area of the screen show?
    options: [live_camera_rocket, animation_rocket, control_room, studio_presenter, map_or_chart, title_or_graphic_card, other]

  - id: telemetry_panel_visible
    question: Is a panel showing numeric flight data (e.g. altitude, speed, distance) visible?
    options: [yes, no]

  - id: trajectory_chart_visible
    question: Is a chart plotting the rocket's trajectory (altitude vs distance) visible?
    options: [yes, no]

  - id: ground_track_map_visible
    question: Is a world map showing the rocket's ground track or tracking stations visible?
    options: [yes, no]

  - id: control_room_inset_visible
    question: Is a smaller inset showing people in a control room visible?
    options: [yes, no]

  - id: people_visible
    question: Are any real people visible anywhere on screen?
    options: [yes, no]

  - id: onscreen_text_language
    question: What language is most of the on-screen text in?
    options: [french, english, mixed, no_text]

  # ── B. Reading numbers (bucketed, see "Logic") ────────────────────────────
  - id: clock_state
    question: Is a mission clock shown, and is it counting down or up?
    options: [t_minus, t_plus, hold, not_visible]

  - id: altitude_km
    question: What altitude is displayed on screen, in kilometres?
    options: [none, "0-10", "10-50", "50-100", "100-200", "200-500", "500-1000", "1000+"]

  - id: speed_kms
    question: What speed/velocity ("vitesse") is displayed on screen, in km/s?
    options: [none, "0-1", "1-2", "2-4", "4-7", "7-9", "9+"]

  - id: distance_km
    question: What distance is displayed on screen, in kilometres?
    options: [none, "0-100", "100-500", "500-1000", "1000-3000", "3000+"]

  # ── C. Vehicle state ─────────────────────────────────────────────────────
  - id: vehicle_location
    question: Where is the rocket in this frame?
    options: [on_pad, in_flight, not_visible]

  - id: side_boosters_attached
    question: Are the rocket's two side boosters still attached?
    options: [attached, separated, cant_tell]

  - id: fairing_attached
    question: Is the nose fairing still covering the payload?
    options: [attached, jettisoned, cant_tell]

  - id: engine_firing
    question: Is an engine plume or flame visible?
    options: [yes, no, cant_tell]

  - id: payload_separated
    question: Has the telescope separated from the rocket and is it flying free?
    options: [yes, no, cant_tell]

  - id: flight_phase
    question: Which phase of the flight does this frame show?
    options: [pre_launch, liftoff, ascent_with_boosters, ascent_after_booster_sep, ascent_after_fairing_jettison, upper_stage_coast_or_burn, payload_separation, post_separation, cant_tell]

  # ── D. Editorial: what a publisher would act on ──────────────────────────
  - id: highlight_worthy
    question: Is this frame part of a key moment worth clipping as a highlight (liftoff, a separation, a reaction shot)?
    options: [yes, no]

  - id: ad_break_safe
    question: Would cutting away to an ad here miss nothing important (e.g. talking heads, routine cruise)?
    options: [yes, no]
```

**Why these groups.** A tests layout understanding (easy). B tests reading small, sometimes French, numbers (hard, and directly useful). C tests visual understanding of the vehicle (hardest, and what event detection relies on). D is the business question. Expect accuracy to drop from A to C; that gradient is itself a result.

---

## Logic: buckets, scoring, events

### 1. Numbers become buckets

Clef chooses from options; it cannot output "177". So numeric fields are bucketed (edges in the schema). **The labeller writes the raw number they read** (e.g. `177`, `2.92`), and `evaluate.py` converts it to a bucket. This avoids human bucketing mistakes. Bucket rules:

- lower edge inclusive, upper exclusive: `100-200` means 100 ≤ x < 200
- French commas are normalised (`2,92` → `2.92`) before bucketing
- if the number isn't on screen, the true answer is `none`

### 2. Turning probabilities into an answer

For each question per frame: `answer = argmax(probabilities)`, `confidence = max(probabilities)`. Keep the full probability vector in `answers.jsonl`; it's needed for calibration and the replay panel.

### 3. Scoring (evaluate.py)

| Metric | Definition |
|---|---|
| Accuracy | share of frames where the answer equals the label; frames labelled `?` (labeller unsure) are excluded |
| Macro-F1 | per question, averaged over options that appear in the labels |
| Near-miss rate | numeric questions only: answer is off by exactly one bucket (usually a value near a boundary) |
| Majority baseline | accuracy if you always answered that question's most common label; **a question only "works" if Clef clearly beats this** |
| Calibration | bin answers by confidence (0.5–0.6, …, 0.9–1.0) and compare mean confidence with actual accuracy |
| Confusion matrix | for `main_view` and `flight_phase` |
| Cost and latency | tokens, USD, median and p95 seconds per call |

### 4. Event detection (detect_events.py)

Single frames are noisy, so answers are **smoothed** before looking for changes:

- an answer is **trusted** if `confidence ≥ 0.6` (config: `min_conf`)
- a **state change** is accepted only when the new trusted value holds for **2 consecutive frames** (config: `persist_frames`)
- `cant_tell`, `not_visible` and untrusted answers carry **no information**: they never start or end a state, they are skipped (this matters because the camera often cuts away from the rocket)
- the event time is the timestamp of the **first** frame of the new stable state

| Event | Fires when |
|---|---|
| `ignition` | `clock_state` t_minus → t_plus (mission clock reaches zero, main engine lights; T0 = 61 s in the clip) |
| `liftoff` | `vehicle_location` on_pad → in_flight (the rocket leaves the pad, a few seconds after ignition) |
| `booster_separation` | `side_boosters_attached` attached → separated |
| `fairing_jettison` | `fairing_attached` attached → jettisoned |
| `payload_separation` | `payload_separated` no → yes |
| `crossed_100km` | `altitude_km` first stable value ≥ `100-200` |
| `scene_change` | `main_view` changes (shown in the replay, not scored) |

**Event scoring:** a detected event is a **hit** if it falls within ±2 sampling intervals (±10 s at 5 s sampling) of the labelled true time. Report hits, misses, false positives, and the timing error for each hit. True event times are written by the maintainer in `data/labels/events_truth.csv` (`event,timestamp_s`).

### 5. Record and replay

- **Cache key** = SHA-256 of (frame bytes + schema version + state text + model id). If `runs/cache/<key>.json` exists, **never call the API**.
- Every raw request and response is saved under `runs/<run_id>/raw/`. The run's `answers.jsonl` has one row per frame: `{frame, t_seconds, answers: {qid: {answer, confidence, probs}}}`.
- The replay page reads only files, never the API.

---

## Phases

Each phase lists **Goal → Tasks → Outputs → Checkpoint**. At the checkpoint, Claude Code prints the report described and **stops**.

### Phase 0: Setup and API check

**Goal:** a working Clef call on one image, with the real request and response shape written down.

**Tasks**
1. Create the repo skeleton, `.gitignore`, `.env.example`, `requirements.txt`, `config.yaml`, and `schema/questions.yaml` (copy it from this README).
2. **Read the docs before writing the client.** Read the OpenRouter page for `cloudflare/clef` and its Decisions API docs, plus the Clef model card on Hugging Face (`Cloudflare/clef`). Confirm: endpoint URL, auth header, how the image is passed (base64 vs URL, size limits), how questions and options are encoded, what the response looks like, and how token usage is reported. **Do not guess the API shape.** If the docs are unclear, stop and say so.
3. Write `src/clef_client.py` with a single `ask(image_path, state, questions) -> dict` function plus a converter from our YAML to Clef's question format.
4. Call it **once** on the sample frame `docs/sample_frame.png` (the maintainer will provide the screenshot showing *Altitude 177 km / Distance 413 km / Vitesse 2,92 km/s*) with the full schema.

**Outputs:** `docs/api_notes.md`, `src/clef_client.py`, `runs/phase0/response.json`

**Checkpoint report:** the raw response; a table of question → answer → confidence → *expected* answer for the sample frame (expected: main_view `animation_rocket`, telemetry `yes`, trajectory `yes`, ground track `yes`, control-room inset `yes`, people `yes`, language `french`, altitude `100-200`, speed `2-4`, distance `100-500`, vehicle `in_flight`, boosters `separated`, fairing `jettisoned`, engine `yes`, payload_separated `no`); tokens used and cost for this one call; and any problem with the schema (options rejected, length limits, etc.).

> *Maintainer checks:* does Clef get the obvious ones right? Is the per-frame cost what we expected? Any reason to change the schema before labelling?

---

### Phase 1: Prepare the clip

**Goal:** a 5:30 clip with known timestamps and documented provenance.

**Tasks**
1. The maintainer puts the downloaded broadcast part in `data/raw/`.
2. Use `ffprobe` to report duration and resolution. To help find liftoff, extract a frame every 30 s across the whole file into a **contact sheet** (`docs/overview_contact_sheet.jpg`), with each tile labelled by timestamp.
3. Once the maintainer confirms the timestamps, trim the 5:30 window to `data/clip/clip.mp4` (re-encode to H.264 so it plays in a browser).
4. Write `docs/SOURCE.md`: source URL, exact filename, the clip's start and end in the original, and attribution text.

**Outputs:** `data/clip/clip.mp4`, `docs/SOURCE.md`, `docs/overview_contact_sheet.jpg`

**Checkpoint report:** source file metadata, chosen window, clip duration, and a contact sheet of the clip itself (one tile every 15 s).

> *Maintainer checks:* does the window cover liftoff, booster separation and fairing jettison? Are the telemetry graphics on screen for a good part of it? If not, shift the window.

---

### Phase 2: Frames and labelling kit

**Goal:** frames to send to Clef, plus everything the maintainer needs to label them quickly.

**Tasks**
1. Sample one frame every 5 s (`config.sample_interval_s`) → `data/frames/f_0000_t000.0.jpg` … (66 frames for the 330 s clip). Name each file by index and timestamp.
2. Write `data/labels/labels.csv`, one row per frame: `frame, t_seconds` plus one column per question. For numeric questions, use raw-number columns (`altitude_raw, speed_raw, distance_raw`). Pre-fill nothing.
3. Write `data/labels/LABELLING.md`: the allowed values for each column, the rules (`?` = unsure; write raw numbers as shown; `none` if not on screen), and how each question should be interpreted.
4. Write `data/labels/events_truth.csv` with headers only.
5. Build `data/labels/label_helper.html`: a static page showing each frame large, with its index and timestamp, and left/right arrow keys to step through. It's view-only; the labels go in the CSV.

**Outputs:** frames, `labels.csv`, `events_truth.csv`, `LABELLING.md`, `label_helper.html`

**Checkpoint report:** frame count, a thumbnail grid, and the path to each labelling file. **Then wait.** The maintainer labels all frames (about an hour) and fills in `events_truth.csv` before replying "go".

> *Maintainer checks:* Are any questions ambiguous in practice? If so, change the schema **now** (bump `version`), before any tokens are spent on the full run.

---

### Phase 3: Run Clef (RECORD)

**Goal:** Clef's answers for every frame, cached, within budget.

**Tasks**
1. `run_clef.py --dry-run`: count frames, estimate tokens per call from Phase 0's usage, and print the projected cost. **Refuse to run if the projection exceeds `BUDGET_USD`.**
2. Real run: go through the frames in order, check the cache first, retry with backoff on 429/5xx (max 3 tries), save the raw response for each frame, and write `runs/<run_id>/answers.jsonl` and `runs/<run_id>/run_meta.json` (model, schema version, time taken, total tokens and cost).
3. Validate: every frame has an answer for every question; flag any missing or malformed ones.

**Outputs:** `runs/<run_id>/…`

**Checkpoint report:** run id, frames processed, cache hits, failures, total cost, median and p95 latency. Then a **spot check**: five frames (first, last, and three at random), each showing the frame path, Clef's answers, and the labels side by side.

> *Maintainer checks:* is anything obviously broken (all answers identical, probabilities flat, frames out of order)?

---

### Phase 4: Evaluate

**Goal:** an honest accuracy report.

**Tasks**
1. `evaluate.py`: compute the metrics from [Scoring](#3-scoring-evaluatepy) for each question and each group (A–D).
2. Write `reports/accuracy.md` containing: a summary table (question, accuracy, majority baseline, macro-F1, near-miss rate for numeric questions); confusion matrices for `main_view` and `flight_phase`; a calibration table; the **10 worst frames** (most wrong answers) with paths; and cost and latency.
3. Small charts, saved to `reports/` as PNGs: accuracy vs baseline per question, and calibration.

**Outputs:** `reports/accuracy.md`, charts, `runs/<run_id>/metrics.json`

**Checkpoint report:** the summary table, plus a three-line verdict: which group works, which doesn't, and why (from looking at the worst frames).

> *Maintainer checks:* do the failures make sense? Is the model wrong, or is the label or the question ambiguous? Fix labels if needed and re-run Phase 4 (free, because everything is cached).

---

### Phase 5: Event detection

**Goal:** events detected from Clef's answers alone, scored against the true times.

**Tasks**
1. `detect_events.py`: apply the smoothing and transition rules from [Event detection](#4-event-detection-detect_eventspy); write `runs/<run_id>/events.json` (`event, t_seconds, frame, evidence`, where *evidence* lists the questions and confidences that triggered it).
2. Score against `events_truth.csv` and append an *Event detection* section to `reports/accuracy.md`.
3. Show sensitivity: re-run with `min_conf ∈ {0.5, 0.6, 0.7}` × `persist_frames ∈ {1, 2, 3}` and report hits and false positives in a small table. No new API calls are needed.

**Outputs:** `events.json`, updated report

**Checkpoint report:** detected vs true events with timing errors, and the sensitivity table with a recommended setting.

> *Maintainer checks:* are the events believable? Pick the thresholds to use in the demo.

---

### Phase 6: Replay page (the demo)

**Goal:** a self-contained page that looks like live AI analysis.

**Tasks**
1. `build_replay.py` writes `replay/timeline.json` (per frame: t, answers, confidences; plus events) and `replay/index.html`.
2. Page layout: **video on the left** (`../data/clip/clip.mp4`, or a path set in config); **panel on the right**, updated on the video's `timeupdate` using the latest frame where `t ≤ currentTime`:
   - **Now:** main view, flight phase, altitude/speed/distance buckets, booster/fairing/engine state, each with a small confidence bar
   - **Events:** a log that grows as the video passes each detected event (e.g. "🚀 Liftoff · 00:30"); clicking an event seeks the video
   - **Toggle "show ground truth":** highlights answers that disagree with the labels in red. This keeps the demo honest.
   - A footer showing the model, schema version, run id, cost of the run, and attribution
3. A timeline strip under the video with event markers.
4. Plain HTML/CSS/JS, no build step, works from `python -m http.server`.

**Outputs:** `replay/`

**Checkpoint report:** how to open it, a screenshot, and a list of any known sync issues.

> *Maintainer checks:* watch it end to end. Does it feel live? Is it obvious what Clef is "seeing"?

---

### Phase 7 (optional): Comparisons

Only if the maintainer asks. Each item has its own checkpoint.

- **Clef-Flash:** the same frames and schema on `cloudflare/clef-flash`; compare accuracy, cost and latency. This answers "could this run live?"
- **Denser sampling:** 1 frame per second over the 60 s around each event, to measure how quickly events are detected.
- **Context ablation:** add the previous frame's trusted answers to `state`, and compare accuracy and event timing. Watch for the model just copying the previous answer.
- **Another domain:** swap in a cricket or travel schema on a clip the maintainer owns, to show the pipeline transfers.

---

### Phase 8: Pitch summary

**Goal:** material the maintainer can present.

**Tasks:** write `reports/summary.md`: one paragraph on what was tested; the headline numbers (best and worst question groups, event hit rate, cost per minute of video); three things it does well; three limitations; and the [business angle](#business-angle) applied to the actual results. Keep it to one page.

**Checkpoint report:** the summary.

---

## Rules for Claude Code

1. **Phases in order; stop at every checkpoint** and wait for "go". Don't start the next phase early, even partly.
2. **Never guess the Clef API.** Confirm everything from the docs in Phase 0 and write it down in `docs/api_notes.md`. If something is unclear, ask.
3. **Spend tokens only through `run_clef.py`**, always cache-first, always after a dry run, and never above `BUDGET_USD`. Phase 0's single call is the only exception.
4. **Never commit** `runs/`, `data/raw/` or `.env`. The 5:30 clip, its frames, labels, reports, the schema and code are committed (maintainer decision, 2026-10-09).
5. **Don't change the schema silently.** Propose changes at a checkpoint, bump `version`, and note why in the commit message.
6. **Don't edit labels.** If a label looks wrong, list it in the checkpoint report for the maintainer to decide.
7. **Report honestly.** Always show the majority baseline next to accuracy, and include failures and the worst frames. A demo that only shows successes is not useful.
8. **Keep it simple.** Small scripts, no frameworks, no databases. If something feels over-engineered, it probably is.

---

## Business angle

The rocket is a test case. What we're really testing is **video → structured facts and event markers, cheaply and in near real time.** Where that's worth money:

| Use | Same pipeline, different schema |
|---|---|
| **Live sports overlays / second screen** | score, overs, wicket or boundary detected, replay showing → automatic graphics and alerts, with no human operator |
| **Publisher video archives** | auto-chapters, "find every clip where…", highlight reels, ad-break placement (`highlight_worthy`, `ad_break_safe` above) |
| **Travel content → place facts** | beach / city / crowded / night / food visible → structured place attributes, the visual counterpart of a Reddit text-mining pipeline |
| **Content compliance** | check frames against a policy (brand-safe, on-brand, legible) at scale, with calibrated confidence |

Clef's strengths for this: answers are typed and structured (no parsing free text), every answer comes with a probability, output tokens are free, and there's a smaller, faster variant for live use.

---

## Credits and licensing

- **Video:** *Complete Webb Telescope Launch Broadcast*, NASA Goddard Space Flight Center Scientific Visualization Studio (https://svs.gsfc.nasa.gov/14060). NASA-produced media is generally not subject to copyright in the US. Follow NASA's media usage guidelines and **do not use NASA (or ESA/CNES) logos in a way that implies endorsement.**
- **Note:** this broadcast was a joint NASA/ESA production and includes on-screen graphics from partners (e.g. the CNES telemetry panel). It's fine for internal R&D. **Before showing it to an external client, confirm the usage terms** for partner material, or switch to footage the company owns.
- **Model:** Cloudflare Clef / Clef-Flash (Apache-2.0 weights), accessed via OpenRouter or Workers AI.
- **The 5:30 clip and its frames are committed to this repo at the maintainer's request (2026-10-09)**, including partner graphics. The full broadcast is not. Provenance is in `docs/SOURCE.md`; the usage-terms caveat above still applies to any external showing.