# Status

Last updated 2026-10-11. The README describes the project and what happened; this file records where things stand. The original work plan is the README at commit `02369c3`.

**All phases are done except the "another domain" item of Phase 7, which needs a clip the maintainer owns. Phase 7 is in [reports/comparisons.md](../reports/comparisons.md) (`run_004_flash`, `run_005_context`, `run_006_dense`) and Phase 8 in [reports/summary.md](../reports/summary.md). `run_003` is the main run: pass `runs/run_003` to `evaluate.py`, `detect_events.py` and `build_replay.py`, because their default is the latest run, which is now a comparison run.**

**GitHub Pages story page: `index.html` in the repo root, built by hand on 2026-10-11. It reads `replay/timeline.json`, `data/frames/` and `site/clip.mp4` (a 14 MB web copy of the clip, made because `data/clip/clip.mp4` is git-ignored). To publish, set Pages to serve the `main` branch from the root (Settings, Pages).**

**Phase 5 (`src/detect_events.py` on `run_003`) hits 4 of 5 true events with 1 false positive, after the ignition rule was changed from the mission clock to `engine_firing`; see the Event detection section of the report. Phase 6 (`src/build_replay.py`) wrote `replay/`: run `python -m http.server 8000` in the repo root and open http://localhost:8000/replay/.**

**Phases 0 to 4: Phase 3 ran on 2026-10-11 as `run_001`: 66 of 66 frames answered, no failures, $0.042, median latency 1.5 s (p95 2.3 s). Phase 4 wrote [reports/accuracy.md](../reports/accuracy.md) the same day. The schema then went to version 3 (the six vehicle questions now say to judge the main area only, not the insets) and was re-run as `run_002` ($0.046). Version 3 fixed the inset problem but made `payload_separated` worse (83% to 50%), so version 4 narrowed that question's `cant_tell` instruction and was re-run as `run_003` ($0.046). The report now describes `run_003`: vehicle group 72%, up from 67% on version 2. Phase 5 (event detection) is next; `src/detect_events.py` is not written yet.**

**`runs/` is git-ignored, so `run_001` and its cache exist only on the machine that ran it. Another machine has to re-run Phase 3 (about $0.04) or copy `runs/` across.**

## Setting up a new machine

1. Clone the repo.
2. `data/frames/` is committed. `data/clip/clip.mp4` is git-ignored: copy it across, or take it from commit `02369c3`, and check it against the SHA-256 in [SOURCE.md](SOURCE.md). The raw 10-minute cut in `data/raw/` is not needed.
3. Create `.env` from `.env.example` and fill in `OPENROUTER_API_KEY`.
4. Install Python 3.11 and `pip install -r requirements.txt`, and put `ffmpeg` on PATH.

## Decisions that differ from the README

- **Clip length:** the clip is 5:30 (330 s), not 5:00, and starts 61 s before T0, not 30 s. At 5 s sampling that is 66 frames. The values are in `config.yaml`.
- **Provider:** Clef is pinned to the Cloudflare provider on OpenRouter with no fallback. See [api_notes.md](api_notes.md).
- **Confidence:** we use the top probability, as the README says, not the API's own `confidence` field.

## Open questions for the maintainer

- **T0 versus liftoff.** The mission clock reaches zero at 61 s into the clip, when the main engine ignites. The rocket is still on the pad at 66 s and leaves it a few seconds later. `events_truth.csv` needs one agreed time for `liftoff`.
- **Telescope visible after fairing jettison.** On the Phase 0 sample frame Clef leaned towards `payload_separation` for `flight_phase` and was close to a coin flip on `payload_separated`. A sentence in the schema's `state` saying the telescope stays attached after fairing jettison might help. That would be schema version 2 and should be decided before labelling.

## What the clip contains

From [clip_contact_sheet.jpg](clip_contact_sheet.jpg) (one tile every 15 s):

| Clip time | On screen |
|---|---|
| 00:00–02:00 | Control room, then live camera of the pad, ignition and climb into cloud. No telemetry panel. A small mission clock sits in the top-right corner. |
| 02:15–04:30 | Animation of the rocket with the telemetry panel, trajectory chart, map and control-room inset. |
| 03:15–03:30 | Side boosters gone between these two tiles (about T+2:14 to T+2:29). |
| 04:15–04:30 | Fairing gone between these two tiles (about T+3:14 to T+3:29). |
| 04:45–05:30 | Globe view, then onboard-style views of the telescope, with the telemetry panel still visible. |
