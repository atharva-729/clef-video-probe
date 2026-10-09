# Source video

| | |
|---|---|
| Title | Complete Webb Telescope Launch Broadcast |
| Publisher | NASA Goddard Space Flight Center, Scientific Visualization Studio |
| Page | https://svs.gsfc.nasa.gov/14060 |
| Original file | `14060_Webb_Full_Launch_Broadcast_2.webmhd.webm` (Part 2 of 3, 1080×606) |

## What is in this project

The 5:30 clip is committed to the repo. The 10-minute raw cut is git-ignored and not needed.

| File | What it is |
|---|---|
| `data/raw/14060_Webb_Full_Launch_Broadcast_2.webmhd.mkv` | A 10-minute cut of Part 2 made by the maintainer (599.3 s, VP8/Vorbis, 1080×606). The full Part 2 download was not kept. |
| `data/clip/clip.mp4` | The first 5:30 of that cut, re-encoded to H.264/AAC (330.0 s, 1080×606, 61.8 MB). This is the clip every later phase uses. |

SHA-256 of `data/clip/clip.mp4`: `4c25a279fba2ade8691dcb0c6b80d79529a4b561a3cea2c373126904c560c8b1`

## Clip window

- The clip runs from **T−1:01 to T+4:29** on the broadcast's mission clock. The clock overlay reads `-00:01:01` on the first frame, so T0 is at **61 s** into the clip.
- The clip's offset inside the full Part 2 file was not recorded. To recreate the clip from a fresh download, find the frame where the clock reads `-00:01:01` and cut 330 s from there.
- Recreate `clip.mp4` from the 10-minute cut with `python src/prepare_clip.py trim data/raw/14060_Webb_Full_Launch_Broadcast_2.webmhd.mkv --start 0 --duration 330`.

## Attribution

Video: *Complete Webb Telescope Launch Broadcast*, NASA Goddard Space Flight Center Scientific Visualization Studio, https://svs.gsfc.nasa.gov/14060.

The broadcast is a joint NASA/ESA production and includes partner graphics (for example the CNES telemetry panel). It is used here for internal R&D. Confirm the usage terms for partner material before showing it to an external client, and do not use NASA, ESA or CNES logos in a way that implies endorsement.
