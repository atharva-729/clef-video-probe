# Clef Video Probe

**Can a vision decision model watch a broadcast and tell us, frame by frame, what is happening, accurately enough to drive something a viewer sees live?**

We tested that on one 5½-minute clip of the **James Webb Space Telescope launch broadcast (NASA/ESA, 25 Dec 2021)** using **Cloudflare's Clef**. The short answer: it reads what is printed or laid out on screen almost perfectly, and it is unreliable about what is physically happening in the picture.

- **Story page with the clip embedded:** https://atharva-729.github.io/clef-video-probe/ (source: [index.html](index.html))
- **One-page summary:** [reports/summary.md](reports/summary.md)
- **Full numbers:** [reports/accuracy.md](reports/accuracy.md) and [reports/comparisons.md](reports/comparisons.md)

This README explains what we set out to do, how the pipeline works, what happened at each step, and where the work departed from the plan. The original phase-by-phase plan this README used to contain is in the git history (commit `02369c3`).

## Contents

- [Results at a glance](#results-at-a-glance)
- [What we were trying to find out](#what-we-were-trying-to-find-out)
- [How the pipeline works](#how-the-pipeline-works)
- [What happened, step by step](#what-happened-step-by-step)
- [Results in detail](#results-in-detail)
- [Where it departed from the plan](#where-it-departed-from-the-plan)
- [Running it yourself](#running-it-yourself)
- [Repo layout](#repo-layout)
- [Limits of this test](#limits-of-this-test)
- [Credits and licensing](#credits-and-licensing)

---

## Results at a glance

66 frames (one every 5 s), 19 multiple-choice questions per frame, 1,251 answers scored against hand labels. Final run: `run_003`, question schema version 4.

| Question group | Accuracy | What it covers |
|---|---|---|
| A. Layout | 97% | which kind of picture, which panels, charts, maps and insets are on screen |
| B. Numbers | 99.6% (260 of 261) | mission clock state; altitude, speed and distance read off the telemetry panel |
| C. Vehicle | 72% | where the rocket is, boosters, fairing, engine flame, payload, flight phase |
| D. Editorial | 87% | "is this a highlight?", "is it safe to cut to an ad?" (only about 6 points above baseline) |

| | |
|---|---|
| Events detected from the answers | 4 of 5, with 1 false alarm (booster separation fired 73 s early) |
| Confidence | answers given at 90% or more were 99% correct, and were 59% of all answers; below 60% they were right 42% of the time |
| Cost | $0.046 per pass over the clip, about $0.008 per minute or $0.50 per hour of video |
| Speed | about 1.5 s per frame through OpenRouter |
| Whole project | six runs, 519 model calls, $0.32 |

---

## What we were trying to find out

Text-based analysis of fan reaction is being worked on elsewhere. The open question here is **images**: given only what is on screen, can a model extract information useful enough to show in real time?

A launch broadcast is a good first test because one frame holds a lot of checkable information: telemetry numbers, a trajectory chart, a ground-track map, a control-room inset, and either live footage or an animation of the vehicle. Some of that is printed on the screen and some of it has to be understood. The pipeline itself is domain-agnostic: swap the question list and the same code runs on a cricket broadcast or a video archive.

The target outputs were a replay page that looks like live analysis, an honest accuracy report, and a short summary of where this could be useful commercially.

### Clef in one paragraph

Clef is a 27B multimodal *decision* model (post-trained from Qwen3.8-27B). It does not write prose. You give it a **state** (text, optionally images) and a **schema of typed questions** with allowed options, and it returns a **probability for every option of every question** in one forward pass. Output tokens are free; you pay for input. We called `cloudflare/clef` through the OpenRouter **Decisions API** (not the chat-completions endpoint) at $0.24 per million input tokens. A smaller Clef-Flash exists; OpenRouter listed it at $0.038 per million when we ran it.

---

## How the pipeline works

```
clip ──ffmpeg──▶ frames (every 5 s) ──▶ Clef (frame + 19 questions) ──▶ answers.jsonl   (record once, cached)
                       │                                                     │
                       └──▶ labels.csv (human) ─────▶ evaluate.py ◀──────────┤
                                                                             ▼
                                              detect_events.py ──▶ events.json ──▶ replay page and story page
```

### The questions

All 19 questions are single-choice, and each has an escape option (`none`, `cant_tell` or `not_visible`) so the model is never forced to guess. The exact wording lives in [schema/questions.yaml](schema/questions.yaml). A state paragraph sent with every frame explains that this is a rocket-launch broadcast, that text may be in French with decimal commas, and that the telescope stays attached after the fairing comes off.

| Group | Questions |
|---|---|
| A. Layout | `main_view`, `telemetry_panel_visible`, `trajectory_chart_visible`, `ground_track_map_visible`, `control_room_inset_visible`, `people_visible`, `onscreen_text_language` |
| B. Numbers | `clock_state`, `altitude_km`, `speed_kms`, `distance_km` |
| C. Vehicle | `vehicle_location`, `side_boosters_attached`, `fairing_attached`, `engine_firing`, `payload_separated`, `flight_phase` |
| D. Editorial | `highlight_worthy`, `ad_break_safe` |

### Numbers become buckets

Clef picks from options; it cannot output "177". So numeric questions offer ranges such as `100-200`. The labeller writes the raw number shown on screen, and `evaluate.py` converts it to a bucket (lower edge inclusive, upper exclusive, French commas normalised). This keeps bucketing mistakes out of the labels.

### From probabilities to an answer

`answer = argmax(probabilities)` and `confidence = max(probabilities)`. The API also returns its own `confidence` field, which is a different, undocumented number (for example 0.82 where the top probability was 0.92); we do not use it.

### Scoring

For each question: accuracy, macro-F1, and the **majority baseline**, which is the accuracy you would get by always giving that question's most common label. A question only "works" if Clef clearly beats its baseline. Cells the labeller marked `?` are excluded. Numeric questions also get a near-miss rate (off by exactly one bucket). Calibration compares stated confidence with actual accuracy in bins.

### Event detection

Single frames are noisy, so answers are smoothed before looking for changes:

- an answer is **trusted** if its confidence is at least 0.6;
- a state changes only when a new trusted value holds for **2 consecutive frames**;
- escape answers and untrusted answers carry no information: they neither start nor break a streak;
- the event time is the first frame of the new state.

| Event | Fires when |
|---|---|
| `ignition` | `engine_firing` no → yes |
| `liftoff` | `vehicle_location` on_pad → in_flight |
| `booster_separation` | `side_boosters_attached` attached → separated |
| `fairing_jettison` | `fairing_attached` attached → jettisoned |
| `payload_separation` | `payload_separated` no → yes (does not happen in this clip) |
| `crossed_100km` | `altitude_km` first stable value of `100-200` or higher |
| `scene_change` | `main_view` changes (shown in the replay, not scored) |

A detection counts as a hit if it is within ±10 s of the hand-timed true time.

### Record once, replay forever

Every response is cached under `runs/cache/`, keyed by SHA-256 of the frame bytes, schema version, state text and model id. A cache hit never calls the API. `run_clef.py` always prints a projected cost first and refuses to run above `BUDGET_USD`. The replay and story pages read only files.

---

## What happened, step by step

### 1. API check

We read the OpenRouter and Cloudflare docs before writing any client code and recorded the confirmed request and response shape in [docs/api_notes.md](docs/api_notes.md). One call on a sample frame used 2,995 input tokens, cost $0.0007 and took 2.2 s.

Things that were not obvious from the docs:

- The image goes inside the `state` array as a base64 data URL. A top-level `images` field, which the Workers AI native API uses, is rejected.
- Workers AI estimates tokens from the base64 length *before* reading the image and returns HTTP 413 past 65,536, so frames must be under roughly 190 KB. The client re-encodes to JPEG under 150 KB.
- OpenRouter lists two providers for Clef with different context sizes. We pinned Cloudflare with no fallback so every frame is answered by the same deployment.
- PyYAML reads bare `yes` and `no` options as booleans; the loader maps them back to strings.

On that sample frame Clef leaned towards "payload separation" as soon as the telescope was visible. That led to schema version 2, which adds a sentence to the state saying the telescope stays attached after fairing jettison. This was done before any labelling.

### 2. Clip and frames

The source is Part 2 of the *Complete Webb Telescope Launch Broadcast*. We cut 330 s starting 61 s before T0 and sampled a frame every 5 s, giving 66 frames in `data/frames/`. Provenance is in [docs/SOURCE.md](docs/SOURCE.md).

What the clip shows:

| Clip time | On screen |
|---|---|
| 0:00 | Control room |
| 0:05–1:00 | Live camera of the pad, countdown clock in the corner until 0:50 |
| 1:01, 1:05 | Ignition, then liftoff |
| 1:15–2:00 | The rocket climbing into cloud, then empty cloud |
| 2:05–4:40 | Computer animation with the telemetry panel, trajectory chart, map and control-room inset |
| 3:23 | Side boosters separate |
| 3:55 | Altitude passes 100 km |
| 4:28 | Fairing jettison |
| 4:45–5:30 | Globe view, then an onboard view of the telescope with a small rocket animation in an inset |

### 3. Labels

Labels were first drafted by Claude (Sonnet) from the frames and then reviewed and corrected by the maintainer, using a small local tool that saves every click straight to `data/labels/labels.csv`. `flight_phase` was labelled from the frame alone, with no inference from timing, so the label uses the same information Clef gets. True event times are in `data/labels/events_truth.csv`.

### 4. First full run (schema v2)

66 frames, no failures, $0.042. Layout and numbers were already near perfect. The vehicle group was 67%, with two problems standing out:

- **Boosters called "separated" far too early.** From the first animated frame at 2:05, Clef answers `separated` at around 90% confidence, on 16 frames in a row, while the boosters are plainly drawn on the rocket.
- **The last nine frames were the nine worst.** On the globe and telescope close-ups, labelled "not visible" and "can't tell", Clef answered "in flight, boosters separated, fairing jettisoned".

### 5. The inset trap (schema v3, then v4)

The second problem turned out to be ours. In those late frames a small inset in the bottom-right corner shows an animation of the rocket with no boosters and no fairing. Clef's answers matched the inset. Nothing in the questions said whether "the rocket" meant the main picture or anywhere on screen.

- **v3** reworded the six vehicle questions to begin "Looking only at the main (largest) area of the screen, not the small insets along the bottom", each with an instruction on when to use the escape option. The inset problem went away. But the new escape instruction for `payload_separated` ("answer cant_tell if the main area does not show whether it is still attached") was too permissive: Clef started answering `cant_tell` on frames with the whole rocket in view, and that question fell from 83% to 50%.
- **v4** narrowed that one instruction to "answer cant_tell only if the main area does not show the rocket at all". The question recovered to 88%.

| | v2 | v3 | v4 |
|---|---|---|---|
| C. Vehicle (pooled) | 67% | 65% | 72% |
| `vehicle_location` | 86% | 94% | 94% |
| `side_boosters_attached` | 52% | 55% | 55% |
| `fairing_attached` | 77% | 85% | 83% |
| `engine_firing` | 53% | 62% | 62% |
| `payload_separated` | 83% | 50% | 88% |
| `flight_phase` | 52% | 45% | 50% |

Fairing and flight phase moved by a frame or two between v3 and v4 although their wording did not change, so differences of that size are noise. The early booster separation did not move across any version: that one is a model error.

### 6. Event detection

The first attempt hit 3 of 5 events. Ignition was detected at 2:10 instead of 1:01, because the rule watched the mission clock go from counting down to counting up, and the broadcast takes the clock off screen from 0:50 to 2:10. Clef read the clock correctly on every frame; the rule was wrong for this footage. Changing ignition to fire on `engine_firing` no → yes fixed it.

| Event | True time | Detected | Result |
|---|---|---|---|
| ignition | 61 s | 70 s | hit, +9 s |
| liftoff | 65 s | 75 s | hit, +10 s |
| booster_separation | 203 s | 130 s | miss, and a false alarm |
| fairing_jettison | 268 s | 270 s | hit, +2 s |
| crossed_100km | 235 s | 235 s | hit, exact |

Varying the confidence threshold (0.5 to 0.7) and persistence (1 to 3 frames) changed almost nothing: the booster answers are confident and persistent, so no threshold removes them.

### 7. Replay page and story page

[replay/](replay/) is the plain demo: video on the left, Clef's current answers with confidence bars on the right, an event log that grows as the video plays, and a toggle that turns answers red where they disagree with the labels.

[index.html](index.html) is the public write-up, published with GitHub Pages. It embeds the clip with a narrated walk-through, shows every answer as a 19 × 66 grid, and tells the rest of this README as a story.

The clip on the story page carries an overlay drawn from `replay/timeline.json`. It shows:
- **The main picture:** always on screen.
- **The panels Clef says are visible:** each one outlined.
- **The clock:** boxed while it is on screen.
- **The flight figures:** a tick per figure, with a red box on a misread.
- **A vehicle card:** sits outside the picture, under the clip on the page and in a column to its right in fullscreen. Each answer is faded while it is right and unchanged, bright for 10 s after it changes, and red when wrong.

The editorial answers and the notes sit in a strip under the clip. Positions are written in the clip's own 1080×606 pixels, so the overlay scales with the player. The page has its own controls, so fullscreen (button, double-click or F) takes the clip, the overlay and the strip together.

### 8. Three follow-up comparisons

Details are in [reports/comparisons.md](reports/comparisons.md).

| Experiment | Result |
|---|---|
| **Clef-Flash** (smaller model) | A sixth of the cost ($0.007 for the clip) and 8 points worse overall (80.9% against 88.6%). Editorial questions fell to 51%. It was no faster through OpenRouter. It does get the boosters right more often and detects booster separation 2 s after the true time, but then calls the fairing gone 73 s early. |
| **One frame per second** around each event | Ignition, fairing jettison and the 100 km crossing are each detected in the exact second. Liftoff stays 9 s late and booster separation is still missed. Costs $0.042 per minute of video against $0.008. |
| **Previous-frame context** (the last frame's trusted answers added to the state) | No gain: 87.5% against 88.6%, slightly worse on frames where the truth had just changed (70% against 76%), and one extra false alarm. |

A fourth planned comparison, the same pipeline on a different kind of footage, was not run because it needs a clip the company owns.

---

## Results in detail

Final run (`run_003`, schema v4). "Baseline" is the accuracy of always giving the most common label.

| Question | Accuracy | Baseline |
|---|---|---|
| main_view | 80% | 48% |
| telemetry_panel_visible | 100% | 61% |
| trajectory_chart_visible | 100% | 61% |
| ground_track_map_visible | 100% | 61% |
| control_room_inset_visible | 100% | 50% |
| people_visible | 100% | 52% |
| onscreen_text_language | 100% | 61% |
| clock_state | 100% | 52% |
| altitude_km | 100% | 40% |
| speed_kms | 100% | 40% |
| distance_km | 98% | 40% |
| vehicle_location | 94% | 58% |
| side_boosters_attached | 55% | 52% |
| fairing_attached | 83% | 71% |
| engine_firing | 62% | 58% |
| payload_separated | 88% | 77% |
| flight_phase | 50% | 33% |
| highlight_worthy | 95% | 89% |
| ad_break_safe | 79% | 73% |

What the errors look like:

- **`main_view`:** the misses are the empty-cloud frames and the globe and telescope close-ups, where no option fits well. Confidence drops to 26–45% on the cloud frames, so the model signals its own doubt.
- **`side_boosters_attached`:** 17 frames labelled `attached` are answered `separated`, and 10 more are answered `cant_tell`.
- **`engine_firing`:** 15 frames labelled `yes` are answered `no`, many of them in the animation after booster separation where the plume is faint.
- **`flight_phase`:** inherits the booster error. 18 frames of "ascent with boosters" are answered "ascent after booster separation".
- **`ad_break_safe`:** leans towards `yes`.

Calibration is the most useful finding for building anything on top of this:

| Stated confidence | Answers | Correct |
|---|---|---|
| under 50% | 77 | 42% |
| 50–60% | 64 | 42% |
| 60–70% | 75 | 67% |
| 70–80% | 104 | 88% |
| 80–90% | 198 | 91% |
| 90–100% | 733 | 99% |

---

## Where it departed from the plan

- **The clip is 5:30, not 5:00,** and starts 61 s before T0 rather than 30 s, to include more of the pad and countdown.
- **"T0" and "liftoff" are different moments.** The clock reaches zero and the engine lights at 61 s; the rocket leaves the pad at about 65 s. They became two separate events.
- **The schema changed three times** (v2 before labelling, v3 and v4 after the first run), each with a full re-run. The plan assumed it would be fixed before any tokens were spent.
- **The ignition rule was replaced** after the clock turned out to be off screen at T0.
- **The model run moved machines.** The first attempt failed on a work laptop because its web filter (Netskope) blocks openrouter.ai. The clip and frames were committed so the work could continue on another machine. The client also loads the operating system's certificate store (`truststore`) to work behind TLS-inspecting proxies.
- **The clip is not in the repo's working tree any more.** The 61 MB `data/clip/clip.mp4` was committed for the machine switch and later un-tracked again. A 14 MB web copy at `site/clip.mp4` is committed for the story page. The full-quality clip is still in the git history.
- **A labelling tool was added.** The plan called for a view-only frame viewer and hand-editing a CSV. `src/label_tool.py` is a small local web app that writes the CSV as you click.
- **Clef-Flash cost less than expected** ($0.038 per million input tokens on OpenRouter, not the $0.09 we had noted) and showed no speed advantage.
- **Python's built-in web server cannot serve byte ranges,** so a browser cannot seek in a video served by it. Both pages download the whole clip first when opened from localhost.
- **`run_clef.py` gained three options** for the comparisons: `--flash`, `--frames-dir` and `--context`.

Loose ends: `data/labels/LABELLING.md` and `data/labels/label_helper.html` are the original labelling kit and still quote the v2 question wording.

---

## Running it yourself

Requires Python 3.11 or newer and `ffmpeg` on PATH.

```
pip install -r requirements.txt
cp .env.example .env            # then fill in OPENROUTER_API_KEY; BUDGET_USD defaults to 2.00
```

The model answers are cached in `runs/`, which is git-ignored, so a fresh clone has to record them again (about $0.05):

```
python src/run_clef.py --dry-run                  # prints the projected cost, calls nothing
python src/run_clef.py --run-id run_003           # 66 frames, about 2 minutes
python src/evaluate.py runs/run_003               # writes reports/accuracy.md and charts
python src/detect_events.py runs/run_003          # adds the Event detection section to the report
python src/build_replay.py runs/run_003           # writes replay/
python -m http.server 8000                        # then open http://localhost:8000/
```

Always pass the run directory. Without it these scripts use the most recent run, which may be a comparison run. `evaluate.py` rewrites `reports/accuracy.md` from scratch, so run `detect_events.py` after it.

To change labels: `python src/label_tool.py`, open http://localhost:8765, then re-run `evaluate.py` and `detect_events.py`. That costs nothing.

The comparison runs are listed at the end of [reports/comparisons.md](reports/comparisons.md). The replay page needs `data/clip/clip.mp4`, which is not in the repo; the story page uses `site/clip.mp4`, which is.

---

## Repo layout

```
clef-video-probe/
├── index.html               ← story page (GitHub Pages serves this from the repo root)
├── site/                    ← 14 MB web copy of the clip and its poster image
├── replay/                  ← plain replay demo: index.html + timeline.json
├── reports/                 ← summary.md, accuracy.md, comparisons.md, charts
├── schema/questions.yaml    ← the 19 questions (version 4)
├── config.yaml              ← clip window, sampling interval, models, event thresholds
├── data/
│   ├── frames/              ← 66 sampled frames (committed)
│   ├── labels/              ← labels.csv, events_truth.csv, labelling notes
│   ├── clip/, raw/          ← source video (git-ignored)
│   └── frames_dense/        ← one-per-second frames for the comparison (git-ignored; rebuild with sample_dense.py)
├── docs/                    ← api_notes.md, SOURCE.md, STATUS.md, contact sheets, screenshot
├── src/
│   ├── clef_client.py       ← ask(frame, state, questions) → raw response
│   ├── prepare_clip.py      ← trim the clip, build contact sheets
│   ├── make_label_sheet.py  ← sample frames, write the labelling kit
│   ├── label_tool.py        ← local labelling app
│   ├── run_clef.py          ← record: dry-run cost estimate, cached calls
│   ├── evaluate.py          ← accuracy, baselines, calibration, worst frames
│   ├── detect_events.py     ← smoothing and transition rules, scoring, sensitivity
│   ├── build_replay.py      ← writes replay/
│   └── sample_dense.py      ← one frame per second around each event
└── runs/                    ← raw responses, cache, answers and metrics per run (git-ignored)
```

---

## Limits of this test

This is one clip of one broadcast, labelled by one person, with labels first drafted by another model. 66 frames means a single frame is worth 1.5 percentage points on any question. Latency was measured on one afternoon through one provider. Treat every number here as an indication, not a benchmark.

The sensible next test is the same pipeline on footage the company owns, in the domain of most commercial interest, with questions limited to what is printed or laid out on screen.

---

## Credits and licensing

- **Video:** *Complete Webb Telescope Launch Broadcast*, NASA Goddard Space Flight Center Scientific Visualization Studio (https://svs.gsfc.nasa.gov/14060). NASA-produced media is generally not subject to copyright in the US. Follow NASA's media usage guidelines and do not use NASA, ESA or CNES logos in a way that implies endorsement.
- **Partner material:** the broadcast was a joint NASA/ESA production and includes on-screen graphics from partners such as the CNES telemetry panel. A short excerpt and sampled frames are included here for research. Confirm usage terms before using them in client-facing or commercial material, or switch to footage the company owns.
- **Model:** Cloudflare Clef and Clef-Flash (Apache-2.0 weights), accessed through OpenRouter.
