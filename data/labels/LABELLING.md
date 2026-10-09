# Labelling guide

Schema version 2. One row per frame in `labels.csv`; open `label_helper.html` to see the frames.

## Rules

- Answer **only from what is visible in the frame**, the same as Clef.
- `?` means you are unsure. Those cells are excluded from scoring.
- Numeric columns (`altitude_raw`, `speed_raw`, `distance_raw`): write the number as shown on screen. A French comma is fine (`2,92`). Write `none` if the number is not on screen. Do not bucket it; `evaluate.py` does that.
- Every other column takes one of the values below, spelled exactly.
- `notes` is free text and is not scored.
- Do not edit the `frame` or `t_seconds` columns.

## Columns

### `main_view`

What does the main (largest) area of the screen show?

Values: `live_camera_rocket`, `animation_rocket`, `control_room`, `studio_presenter`, `map_or_chart`, `title_or_graphic_card`, `other`

The largest area of the screen. A live shot of the pad or rocket is `live_camera_rocket`; the CGI rocket is `animation_rocket`.

### `telemetry_panel_visible`

Is a panel showing numeric flight data (e.g. altitude, speed, distance) visible?

Values: `True`, `False`

### `trajectory_chart_visible`

Is a chart plotting the rocket's trajectory (altitude vs distance) visible?

Values: `True`, `False`

### `ground_track_map_visible`

Is a world map showing the rocket's ground track or tracking stations visible?

Values: `True`, `False`

### `control_room_inset_visible`

Is a smaller inset showing people in a control room visible?

Values: `True`, `False`

### `people_visible`

Are any real people visible anywhere on screen?

Values: `True`, `False`

### `onscreen_text_language`

What language is most of the on-screen text in?

Values: `french`, `english`, `mixed`, `no_text`

### `clock_state`

Is a mission clock shown, and is it counting down or up?

Values: `t_minus`, `t_plus`, `hold`, `not_visible`

The small mission clock. `t_minus` = counting down, `t_plus` = counting up, `not_visible` = no clock on screen.

### `altitude_raw`

What altitude is displayed on screen, in kilometres?

Values: a raw number, or `none`

Write the number as shown (`177`, not a bucket). `none` if no altitude is on screen.

### `speed_raw`

What speed/velocity ("vitesse") is displayed on screen, in km/s?

Values: a raw number, or `none`

Write the number as shown (`2,92` or `2.92`). `none` if no speed is on screen.

### `distance_raw`

What distance is displayed on screen, in kilometres?

Values: a raw number, or `none`

Write the number as shown. `none` if no distance is on screen.

### `vehicle_location`

Where is the rocket in this frame?

Values: `on_pad`, `in_flight`, `not_visible`

`on_pad` until the rocket has visibly left the pad. `not_visible` if the rocket is not shown.

### `side_boosters_attached`

Are the rocket's two side boosters still attached?

Values: `attached`, `separated`, `cant_tell`

`attached` from the pad until separation. `cant_tell` if the rocket is not shown clearly.

### `fairing_attached`

Is the nose fairing still covering the payload?

Values: `attached`, `jettisoned`, `cant_tell`

`attached` until the fairing halves are gone. `cant_tell` if the rocket is not shown clearly.

### `engine_firing`

Is an engine plume or flame visible?

Values: `True`, `False`, `cant_tell`

### `payload_separated`

Has the telescope separated from the rocket and is it flying free?

Values: `True`, `False`, `cant_tell`

`yes` only once the telescope has left the upper stage. Seeing the telescope earlier does not count.

### `flight_phase`

Which phase of the flight does this frame show?

Values: `pre_launch`, `liftoff`, `ascent_with_boosters`, `ascent_after_booster_sep`, `ascent_after_fairing_jettison`, `upper_stage_coast_or_burn`, `payload_separation`, `post_separation`, `cant_tell`

Pick the phase the broadcast is in, using the mission clock or the state of boosters and fairing.

### `highlight_worthy`

Is this frame part of a key moment worth clipping as a highlight (liftoff, a separation, a reaction shot)?

Values: `True`, `False`

`yes` for liftoff, separations and similar key moments; `no` for routine shots.

### `ad_break_safe`

Would cutting away to an ad here miss nothing important (e.g. talking heads, routine cruise)?

Values: `True`, `False`

`yes` if cutting away here would miss nothing important.

## Event times (`events_truth.csv`)

Columns: `event,timestamp_s`. Use seconds from the start of the clip, to the nearest second, and leave a row out if the event does not happen in the clip.

| Event | What to mark |
|---|---|
| `ignition` | the mission clock reaches zero and the main engine lights (about 61 s) |
| `liftoff` | the rocket visibly leaves the pad |
| `booster_separation` | the side boosters fall away |
| `fairing_jettison` | the fairing halves fall away |
| `payload_separation` | the telescope separates from the upper stage |
| `crossed_100km` | the displayed altitude first reaches 100 km |

Frames are 5 s apart, so events are scored with a tolerance of two frames.
