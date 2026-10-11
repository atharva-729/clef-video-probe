# Clef Video Probe: summary

**Can a vision model watch a broadcast and tell us, frame by frame, what is happening, well enough to drive something a viewer sees live?** For what is printed or laid out on screen, yes. For what is physically happening in the picture, not yet.

## What was tested

We took a 5½-minute clip of the James Webb Space Telescope launch broadcast and sampled one frame every 5 seconds (66 frames). Each frame went to Clef, Cloudflare's vision decision model, with 19 fixed multiple-choice questions. Clef returns a probability for every option rather than free text. We scored its answers against hand labels, turned changes in its answers into detected events, and built a replay page that plays the clip beside Clef's answers.

## Headline numbers

| | Result |
|---|---|
| Screen layout (7 questions) | 97% correct |
| Reading on-screen numbers and the clock (4 questions) | 100% correct, one miss in 261 answers |
| State of the rocket (6 questions) | 72% correct |
| Editorial judgement (2 questions) | 87% correct, but only about 6 points above always giving the commonest answer |
| Events detected | 4 of 5, with 1 false alarm |
| Cost | $0.046 for the clip: under 1 cent per minute of video, about $0.50 per hour |
| Speed | about 1.5 seconds per frame |

## Three things it does well

1. **It reads the screen.** Altitude, speed and distance, shown in small French-formatted figures, were placed in the right range on every frame but one. Which panels, charts, maps and insets were on screen was right every time.
2. **Its confidence can be trusted at the top end.** Answers given with 90% confidence or more were 99% correct, and they make up 59% of all answers. Below 60% confidence it was right less than half the time. That gives a usable rule: act on the confident answers and send the rest to a person.
3. **It is cheap and precise enough in time.** At one frame per second, ignition, fairing jettison and crossing 100 km were each detected in the exact second they happened, for about 4 cents per minute of video.

## Three limitations

1. **It misjudges physical state.** Clef said the side boosters had separated 73 seconds before they did, with high confidence, on every frame of the animated view. Whether the engine was firing was right 62% of the time. Rewording the questions, sampling more often and giving it its previous answers did not fix the booster error.
2. **Results depend heavily on question wording.** One reworded question dropped from 83% to 50% correct and then rose to 88% after a second rewording. Each new use needs its questions tuned against labelled frames before it can be trusted.
3. **Editorial judgement is not proven.** "Is this a highlight?" and "is it safe to cut to an ad?" barely beat the commonest answer, and the cheaper Clef-Flash model was right on only 29% of ad-break frames.

This is one clip of one broadcast with one person's labels, so every figure here is an indication, not a benchmark.

## Where it could make money

| Use | What these results say |
|---|---|
| Live sports overlays and second screen | Reading a scoreboard or on-screen graphic is the proven strength, so automatic score and stat extraction looks feasible. Detecting the action itself (a wicket, a boundary) is the same kind of task as the booster question and should be assumed weak until tested. |
| Publisher video archives | Classifying what kind of shot is on screen works, which supports automatic chaptering and "find every clip showing…" search. Automatic highlight picking and ad-break placement are not ready. |
| Travel content to place facts | Not tested. The questions are closer to the layout group that worked than to the physical-state group that did not, so it is worth a small trial on owned footage. |
| Content compliance | The confidence result fits this well: accept the 59% of answers given at high confidence automatically and review the rest by hand. |

## Recommended next step

Run the same pipeline on a clip the company owns, in the domain of most commercial interest, with questions limited to what is printed or laid out on screen. The launch footage includes partner graphics and should not be shown to an external client until usage terms are confirmed.

Details: [accuracy.md](accuracy.md) (per-question results and event detection) and [comparisons.md](comparisons.md) (Clef-Flash, denser sampling, context). The demo is in `replay/`.
