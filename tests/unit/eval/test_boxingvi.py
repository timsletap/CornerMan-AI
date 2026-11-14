"""BoxingVI conversion: messy sheets in, project labels out."""

import math

from eval.public_sets.boxingvi import Punch, parse_rows, to_labels, window

NAN = math.nan


def test_parse_rows_handles_every_published_layout() -> None:
    rows = [
        ["Start_Frame", NAN, "Ending_Frame", NAN, "Class", NAN],  # header
        [3314, NAN, 3323, NAN, "Jab", 9.0],  # blank columns between the numbers
        [6675.0, 6688.0, "Cross", NAN, NAN, 6675.0, 6688.0],  # floats, extra columns after
        [4444, 4457.0, " lead hook ", NAN, -13.0],  # padded, lower case
        [157, 171, "Rear Uppercut", 14.0],
        [NAN, NAN, NAN, 803.0],  # trailing junk row
        [20, 10, "Jab"],  # end before start: dropped
        [5, "Jab"],  # one number only: dropped
    ]

    assert parse_rows(rows) == [
        Punch(157, 171, "uppercut", lead=False),
        Punch(3314, 3323, "jab", lead=True),
        Punch(4444, 4457, "hook", lead=True),
        Punch(6675, 6688, "cross", lead=False),
    ]


def test_window_keeps_the_first_seconds_of_annotated_footage() -> None:
    punches = [Punch(100, 110, "jab", True), Punch(400, 410, "cross", False)]
    assert window(punches, fps=30.0, max_seconds=None) == punches
    assert window(punches, fps=30.0, max_seconds=5.0) == punches[:1]  # 100 + 150 frames
    assert window([], fps=30.0, max_seconds=5.0) == []


def test_labels_use_the_punch_midpoint_relative_to_the_excerpt() -> None:
    punches = [Punch(100, 110, "jab", True), Punch(130, 142, "cross", False)]

    labels = to_labels("clip", punches, fps=25.0, stance="orthodox", first_frame=100, pad_frames=50)

    # The excerpt starts at frame 50; frame 105 is 55 frames in = 2200 ms at 25 fps.
    assert [(s.t_ms, s.hand, s.type) for s in labels.strikes] == [
        (2200, "left", "jab"),
        (3440, "right", "cross"),
    ]
    assert labels.notes == []
    assert labels.labeler == "boxingvi"


def test_southpaw_swaps_hands_and_long_gaps_are_skipped() -> None:
    # 400 frames at 25 fps = 16 s between the punches: unlabeled, not "nothing happened".
    punches = [Punch(100, 110, "jab", True), Punch(510, 520, "hook", False)]

    labels = to_labels("clip", punches, fps=25.0, stance="southpaw", first_frame=100, pad_frames=0)

    assert [s.hand for s in labels.strikes] == ["right", "left"]
    (gap,) = labels.notes
    # One second of margin either side of the labeled punches.
    assert (gap.start_ms, gap.end_ms) == (1400, 15400)


def test_overlapping_punches_come_out_sorted() -> None:
    punches = [Punch(100, 140, "hook", True), Punch(105, 111, "jab", True)]

    labels = to_labels("clip", punches, fps=30.0, stance="orthodox", first_frame=100, pad_frames=0)

    times = [s.t_ms for s in labels.strikes]
    assert times == sorted(times)
