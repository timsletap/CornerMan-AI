# Labeling guide

How to label a clip for the eval set. The output is one file per clip,
`eval/labels/<clip_id>.json`, in the format of FRD section 6.5. Everything the app claims
about accuracy is scored against these files, so consistency matters more than speed: when
two rules here seem to conflict, pick the one that makes you label the same punch the same
way next week.

## What you label

Label **one fighter per clip**. Write down which one in `fighter.track_hint` (for example
"left of frame at t=0, red gloves") so the eval run picks the same person.

For that fighter you label:

- every punch (`strikes`), with its time, hand, type, and target
- every technique error tied to a punch (`errors`)
- spans you deliberately left unlabeled (`notes`)
- clip-level `tags` and the fighter's `stance`

Kicks, knees, elbows, feints that stop short, and the opponent's strikes are not labeled.

## Hands and stance

`hand` is the fighter's own anatomical hand: `left` or `right`. It is never "the hand on
the left side of the screen". When the fighter faces the camera their left hand is on the
right of the frame.

`stance` is which foot and hand are in front for most of the clip:

- `orthodox`: left foot and left hand lead
- `southpaw`: right foot and right hand lead

If the fighter switches stance for part of the clip, label the stance they hold longest,
and mark the switched span as skipped (see "Ambiguous strikes").

## Strike types

Work down this list and stop at the first rule that fits.

| Type | Definition | How to tell it apart |
|---|---|---|
| `body_shot` | Any punch whose target is below the chest line (ribs, solar plexus, liver, stomach). | Decided by the target, not the arm path. A hook to the ribs and a straight to the stomach are both `body_shot`. Always paired with target `body`. |
| `uppercut` | The fist rises vertically toward the chin or face, palm turned toward the puncher. | The wrist travels mostly upward and finishes above where it started. The elbow stays bent and points down. |
| `hook` | The fist travels in a lateral arc with the elbow bent, roughly 90 degrees. | The wrist moves across the body, not away from it. The elbow lifts to about shoulder height and never straightens. |
| `jab` | A straight punch thrown with the **lead** hand. | Arm extends straight from the guard. Orthodox: `left` hand. Southpaw: `right` hand. |
| `cross` | A straight punch thrown with the **rear** hand. | Arm extends straight, with hip and shoulder rotation. Orthodox: `right` hand. Southpaw: `left` hand. |

Jab versus cross is decided **only** by lead or rear hand, never by how far the arm
extends or how hard the punch looks. A lazy rear straight is still a `cross`; a stiff
power jab is still a `jab`.

Overhands count as `cross` when thrown with the rear hand and `hook` when thrown with the
lead hand.

## Target

- `head`: aimed at the chin, face, or side of the head
- `body`: aimed below the chest line

Label where the punch was aimed, whether or not it landed. On the bag, pads, or in shadow
boxing, judge by height relative to the fighter's own chest. `body_shot` always has target
`body`; the other four types have target `head`.

## Timestamp rule

`t_ms` is the **frame of full extension**: the frame where the fist is furthest along its
path, just before it starts coming back.

- Straight punches: the frame where the arm is straightest.
- Hooks and uppercuts: the frame of contact, or where the fist would make contact if
  nothing is hit.
- If two neighboring frames look equally extended, take the earlier one.

Step frame by frame to find it. Scoring uses a ±150 ms window, which is only about four
frames at 30 fps, so a label placed at the start of the punch will count as a miss.

## Errors

Each error belongs to one punch. Give it the same `t_ms` as that punch.

### `dropped_guard`

The **off hand** (the hand that is not punching) leaves the chin line at any point during
the punch: it drops below the jaw, or drifts out wide enough to leave the chin open.

- `hand` is the hand that dropped, which is the off hand, not the punching hand.
- Watch the whole punch from start to return, not only the extension frame. A guard that
  dips mid-punch and recovers still counts.
- A hand that was already low before the punch started and stays low also counts.

### `chicken_wing`

The **punching arm's** elbow flares out to the side **before the punch starts**, giving the
punch away. The elbow lifts away from the ribs first, then the fist goes.

- `hand` is the punching hand.
- Only flare that happens before the fist starts moving toward the target counts. An elbow
  that rises during a hook is part of the punch and is not an error.
- Do not label it on hooks unless the elbow visibly lifts and pauses before the punch.

## Ambiguous strikes

If you cannot decide what a punch was, or whether it was a punch at all, **do not guess**.
Skip it and record the span in `notes`:

```json
"notes": [
  {"start_ms": 3400, "end_ms": 4200, "reason": "clinch, strikes ambiguous"}
]
```

Skip a span when:

- the fighter is occluded by the opponent, the referee, or the frame edge
- the fighters are clinched or the exchange is too tangled to separate punches
- the camera cuts, whips, or loses focus
- the fighter has switched stance
- you have replayed it three times and still are not sure

A skipped span should cover the whole doubtful stretch, with at least a few frames of
margin on each side. Label everything outside it normally.

## Tags

Tags describe the clip, not individual punches. Use one from each group where it applies.

**Activity** (exactly one)

- `bag`: heavy bag or other stationary bag
- `pads`: focus mitts or Thai pads held by a partner
- `shadow`: shadow boxing, no target
- `sparring`: live exchange with an opponent, including fights

**Distance** (exactly one)

- `near`: the fighter's body, head to hips, fills more than half the frame height
- `far`: it fills less than half

**Camera angle** (exactly one)

- `side`: camera roughly square to the fighter's side; both shoulders overlap
- `three_quarter`: between side and front; both shoulders visible, one clearly nearer
- `head_on`: fighter faces the camera or has their back to it

Judge angle by where the fighter spends most of the clip.

**Setting** (exactly one)

- `indoor`: gym, ring, or cage under artificial light
- `outdoor`: outside in daylight

## Labeling in CVAT

### Set up the task

1. In CVAT, create a task named exactly as the clip file, for example
   `spar_2026_10_22_a.mp4`. The converter uses the task name as the `clip_id`.
2. In the label constructor choose **Raw** and paste the contents of
   [`eval/cvat_labels.json`](cvat_labels.json). This creates four labels: `strike`,
   `error`, `skip_start`, `skip_end`.
3. Upload the clip. Leave **frame step** at 1 and do not set a start or stop frame, so
   CVAT frame numbers match the source video.

### Annotate

Use **shape** mode (not track mode) with the points tool, one point per event.

- **Strike:** go to the frame of full extension, place one `strike` point on the punching
  fist, and set `hand`, `type`, `target`.
- **Error:** on the same frame as its punch, place one `error` point and set `hand` and
  `type`.
- **Skipped span:** place a `skip_start` point on the first skipped frame and type the
  `reason`; place a `skip_end` point on the last skipped frame.

Where you click in the frame does not matter. Only the frame number and attributes are
read.

### Export and convert

1. **Menu > Export task dataset**, format **CVAT for images 1.1**, without images.
2. Unzip to get `annotations.xml`.
3. Convert, passing the clip-level fields CVAT does not store:

```bash
python -m eval.cvat_to_labels to-labels annotations.xml \
    --fps 30 --stance orthodox --tags sparring,far,side,indoor \
    --track-hint "left of frame at t=0, red gloves"
```

This writes `eval/labels/<clip_id>.json`. Get the clip's fps from
`ffprobe -v 0 -select_streams v:0 -show_entries stream=r_frame_rate -of csv=p=0 clip.mp4`.

4. Validate, then add the clip to `eval/splits.yaml` with an anonymous fighter id:

```bash
python -m eval.schema validate eval/labels/ --clips-dir eval/clips
python -m eval.schema validate-splits eval/splits.yaml --labels-dir eval/labels
```

The same fighter must never appear in both `dev` and `test`.

### Correcting existing labels

To fix a label file, send it back to CVAT instead of editing times by hand:

```bash
python -m eval.cvat_to_labels to-cvat eval/labels/<clip_id>.json --out annotations.xml
```

Upload `annotations.xml` to the task with **Menu > Upload annotations**, format **CVAT
1.1**, fix what needs fixing, export again, and bump `--label-version`.

## Before you commit

- [ ] Every punch by the labeled fighter is either labeled or inside a skipped span
- [ ] `t_ms` values sit on the frame of full extension
- [ ] `hand` is anatomical, and jab or cross follows lead or rear hand for the stance
- [ ] One activity, one distance, one angle, and one setting tag
- [ ] Both validate commands print `ok`

Label files and clips stay out of git (see `.gitignore`); only the samples in
`eval/labels/samples/` are committed.
