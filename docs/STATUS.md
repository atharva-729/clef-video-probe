# Status

Last updated 2026-10-09. The README is the work plan; this file records where it stands.

**Phase 3 (Clef run) is pending: it failed on the work laptop because Netskope blocks openrouter.ai. Run `python src/run_clef.py --run-id run_001` on an unfiltered machine, then `python src/evaluate.py`.**

**Phases 0, 1 and 2 are done (labels reviewed by the maintainer). Phase 3 is next, then Phase 4: `src/evaluate.py` is written and tested on synthetic data only.**

## Setting up a new machine

1. Clone the repo.
2. `data/clip/clip.mp4` and `data/frames/` are committed, so the clone has them. Check the clip against the SHA-256 in [SOURCE.md](SOURCE.md). The raw 10-minute cut in `data/raw/` is not needed.
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
