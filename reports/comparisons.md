# Comparisons (Phase 7)

Run on 2026-10-11 against the main run `run_003` (Clef, schema v4, 66 frames, one every 5 s). All runs use the same schema, the same hand labels and the same event rules (`min_conf` 0.6, `persist_frames` 2, hit tolerance ±10 s). Total cost of the three extra runs: $0.19.

| Run | What changed | Frames | Cost |
|---|---|---|---|
| `run_003` | nothing (the main run) | 66 | $0.046 |
| `run_004_flash` | model is Clef-Flash | 66 | $0.007 |
| `run_005_context` | previous frame's trusted answers added to the state text | 66 | $0.047 |
| `run_006_dense` | one frame per second in the 60 s around each true event | 189 | $0.131 |

The fourth Phase 7 item, another domain, was not run: it needs a clip the maintainer owns.

## 1. Clef-Flash

Clef-Flash costs about a sixth as much and is clearly worse overall, but it was no faster through OpenRouter.

| | Clef | Clef-Flash |
|---|---|---|
| Overall accuracy | 88.6% | 80.9% |
| A. Layout | 97% | 89% |
| B. Numbers | 100% | 96% |
| C. Vehicle | 72% | 71% |
| D. Editorial | 87% | 51% |
| Events hit / missed / false positives | 4 / 1 / 1 | 3 / 2 / 2 |
| Cost for the clip | $0.046 | $0.007 |
| Latency, median / p95 | 1.3 s / 1.7 s | 1.8 s / 2.3 s |

Per question, where the two differ by more than a few points:

| Question | Majority baseline | Clef | Clef-Flash |
|---|---|---|---|
| onscreen_text_language | 61% | 100% | 48% |
| speed_kms | 40% | 100% | 86% |
| side_boosters_attached | 52% | 55% | 70% |
| fairing_attached | 71% | 83% | 70% |
| payload_separated | 77% | 88% | 71% |
| highlight_worthy | 89% | 95% | 73% |
| ad_break_safe | 73% | 79% | 29% |

- Flash still reads the layout and the altitude and distance figures correctly (100% on six of the layout and number questions).
- Flash falls below the majority baseline on text language, fairing, payload and both editorial questions.
- Flash is better on the boosters (70% against 55%) and detects booster separation at 205 s, 2 s after the true time, which Clef misses. In exchange it calls the fairing jettisoned 73 s early and detects liftoff 15 s late, outside the tolerance.
- Flash's answers at 0.9 confidence or higher are still 100% correct (629 of 1,251 answers).
- Latency was measured in separate runs through OpenRouter's Cloudflare provider on one afternoon. Clef's own median ranged from 1.3 s to 1.8 s across the five runs that day, so the Flash figure is within that range: no speed advantage showed up here.

## 2. Denser sampling

At one frame per second, three of the four events Clef detects are timed to the second.

| Event | True time (s) | Detected at 5 s sampling | Detected at 1 s sampling |
|---|---|---|---|
| ignition | 61 | 70 (+9) | 61 (0) |
| liftoff | 65 | 75 (+10) | 74 (+9) |
| booster_separation | 203 | 130 (miss) | miss |
| fairing_jettison | 268 | 270 (+2) | 268 (0) |
| crossed_100km | 235 | 235 (0) | 235 (0) |

- The delay at 5 s sampling is mostly the sampling interval, not the model.
- Liftoff stays 9 s late: Clef answers `on_pad` on every frame up to 72 s, so it does not see the rocket leave the pad until it is well clear.
- Booster separation is still missed. Clef answers `separated` at about 0.9 confidence on every frame from 173 s, 30 s before the boosters fall away.
- With `persist_frames` 2 (2 s at this rate) a spurious fairing jettison fires at 203 s. Raising it to 3 or more removes that without moving any other event, tested up to 10.
- Cost at this rate is $0.042 per minute of video, against $0.008 at 5 s sampling.

## 3. Previous-frame context

Telling Clef what it answered for the previous frame did not help.

| | No context | With context |
|---|---|---|
| Overall accuracy | 88.6% | 87.5% |
| C. Vehicle | 72% | 70% |
| D. Editorial | 87% | 83% |
| Accuracy on answers whose label changed from the previous frame | 76% (69 of 91) | 70% (64 of 91) |
| Accuracy on answers whose label stayed the same | 89.6% | 88.7% |
| Answers identical to the previous frame's | 90.4% | 91.3% |
| Events hit / missed / false positives | 4 / 1 / 1 | 4 / 1 / 2 |

- Accuracy drops most where the true answer has just changed, which is the sign of copying the previous answer, though the effect is small on 91 cases.
- It did not fix the early booster separation (fired at 125 s) and it added a second, false ignition at 165 s.
- Mean confidence rose from 0.85 to 0.88 without accuracy rising, so the model is slightly more overconfident with context.
- It uses 4% more input tokens.

## How to reproduce

```
python src/run_clef.py --flash --run-id run_004_flash
python src/run_clef.py --context --run-id run_005_context
python src/sample_dense.py
python src/run_clef.py --frames-dir data/frames_dense --run-id run_006_dense
python src/evaluate.py runs/<run_id>        # writes runs/<run_id>/metrics.json, and overwrites reports/accuracy.md
```

After scoring a comparison run, restore the main report with `python src/evaluate.py runs/run_003` followed by `python src/detect_events.py runs/run_003`.
