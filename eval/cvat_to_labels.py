"""Convert between CVAT XML exports and the label format in FRD section 6.5 (EVAL-02).

Usage:
    python -m eval.cvat_to_labels to-labels annotations.xml --fps 30 --stance orthodox \
        --tags bag,near,side,indoor [--clip-id NAME] [--track-hint TEXT] [--out eval/labels]
    python -m eval.cvat_to_labels to-cvat eval/labels/<clip_id>.json [--out FILE.xml]

``to-labels`` reads a "CVAT for images 1.1" export of a video task (one ``<image>`` per
annotated frame) and also accepts "CVAT for video 1.1" (``<track>`` elements; the first
visible frame of each track is the event). ``to-cvat`` writes the images format, so
existing labels or model predictions can be uploaded to CVAT and corrected there.

CVAT labels (see ``eval/cvat_labels.json``): ``strike`` (hand, type, target), ``error``
(hand, type), ``skip_start`` (reason), ``skip_end``. Any shape kind works; only the frame
and the attributes are read.

Times: CVAT stores frame numbers (0-based, source fps). ``t_ms = int(frame / fps * 1000)``,
the same rule the pose stage uses, and ``frame = round(t_ms * fps / 1000)`` going back.
"""

from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError

from eval.schema import ClipLabels, load_labels

STRIKE = "strike"
ERROR = "error"
SKIP_START = "skip_start"
SKIP_END = "skip_end"
KNOWN_LABELS = (STRIKE, ERROR, SKIP_START, SKIP_END)

DEFAULT_LABELER = "owner"


class ConversionError(ValueError):
    """The CVAT export can't be turned into valid labels."""


@dataclass(frozen=True)
class Annotation:
    """One CVAT shape or tag: where it is in time, its label, and its attributes."""

    frame: int
    label: str
    attributes: dict[str, str] = field(default_factory=dict)


def frame_to_ms(frame: int, fps: float) -> int:
    """Time of a 0-based frame in ms from video start, at ``fps`` frames per second."""
    return int((frame / fps) * 1000)


def ms_to_frame(t_ms: int, fps: float) -> int:
    """Nearest 0-based frame to ``t_ms`` (ms from video start) at ``fps`` frames per second."""
    return round(t_ms * fps / 1000)


def _attributes(element: ET.Element) -> dict[str, str]:
    return {a.get("name", ""): (a.text or "").strip() for a in element.findall("attribute")}


def _frame_of(element: ET.Element, attr: str, source: str) -> int:
    raw = element.get(attr)
    if raw is None or not raw.strip().isdigit():
        raise ConversionError(f"{source}: <{element.tag}> has no integer {attr!r} (got {raw!r})")
    return int(raw)


def read_annotations(root: ET.Element, source: str = "annotations.xml") -> list[Annotation]:
    """Collect every annotation in a CVAT XML document, sorted by frame."""
    found: list[Annotation] = []
    for image in root.findall("image"):
        frame = _frame_of(image, "id", source)
        for shape in image:
            label = shape.get("label")
            if label is not None:
                found.append(Annotation(frame, label, _attributes(shape)))
    for track in root.findall("track"):
        label = track.get("label")
        visible = [s for s in track if s.get("frame") is not None and s.get("outside") != "1"]
        if label is None or not visible:
            continue
        first = min(visible, key=lambda s: _frame_of(s, "frame", source))
        found.append(Annotation(_frame_of(first, "frame", source), label, _attributes(first)))
    return sorted(found, key=lambda a: a.frame)


def task_name(root: ET.Element) -> str | None:
    """Name of the exported CVAT task or job, if the export records one."""
    for path in ("meta/task/name", "meta/job/name", "meta/project/name"):
        name = root.findtext(path)
        if name and name.strip():
            return name.strip()
    return None


def _required(ann: Annotation, name: str, source: str) -> str:
    value = ann.attributes.get(name, "")
    if not value:
        raise ConversionError(
            f"{source}: {ann.label} at frame {ann.frame} is missing attribute {name!r}"
        )
    return value


def cvat_to_labels(
    root: ET.Element,
    *,
    fps: float,
    stance: str,
    tags: Sequence[str] = (),
    clip_id: str | None = None,
    track_hint: str | None = None,
    labeler: str = DEFAULT_LABELER,
    label_version: int = 1,
    source: str = "annotations.xml",
) -> ClipLabels:
    """Build validated labels from a parsed CVAT export.

    Args:
        root: the ``<annotations>`` element.
        fps: source frames per second of the clip.
        stance: ``orthodox`` or ``southpaw``.
        tags: clip tags from FRD 6.5.
        clip_id: defaults to the CVAT task name without its file extension.

    Raises:
        ConversionError: unknown CVAT label, missing attribute, unpaired skip markers,
            or labels that fail the EVAL-01 schema.
    """
    if fps <= 0:
        raise ConversionError(f"{source}: fps must be > 0, got {fps}")
    name = clip_id or task_name(root)
    if not name:
        raise ConversionError(f"{source}: no task name in the export; pass --clip-id")
    name = Path(name).stem if clip_id is None else name

    strikes: list[dict[str, object]] = []
    errors: list[dict[str, object]] = []
    starts: list[Annotation] = []
    ends: list[Annotation] = []
    for ann in read_annotations(root, source):
        t_ms = frame_to_ms(ann.frame, fps)
        if ann.label == STRIKE:
            strikes.append(
                {
                    "t_ms": t_ms,
                    "hand": _required(ann, "hand", source),
                    "type": _required(ann, "type", source),
                    "target": _required(ann, "target", source),
                }
            )
        elif ann.label == ERROR:
            errors.append(
                {
                    "t_ms": t_ms,
                    "type": _required(ann, "type", source),
                    "hand": _required(ann, "hand", source),
                }
            )
        elif ann.label == SKIP_START:
            starts.append(ann)
        elif ann.label == SKIP_END:
            ends.append(ann)
        else:
            raise ConversionError(
                f"{source}: unknown CVAT label {ann.label!r} at frame {ann.frame} "
                f"(expected one of {', '.join(KNOWN_LABELS)})"
            )

    if len(starts) != len(ends):
        raise ConversionError(
            f"{source}: {len(starts)} skip_start but {len(ends)} skip_end; each skipped "
            "span needs both"
        )
    notes: list[dict[str, object]] = []
    for start, end in zip(starts, ends, strict=True):
        if end.frame < start.frame:
            raise ConversionError(
                f"{source}: skip_end at frame {end.frame} comes before skip_start at "
                f"frame {start.frame}"
            )
        notes.append(
            {
                "start_ms": frame_to_ms(start.frame, fps),
                "end_ms": frame_to_ms(end.frame, fps),
                "reason": _required(start, "reason", source),
            }
        )

    strikes.sort(key=lambda s: (int(str(s["t_ms"])), str(s["hand"])))
    try:
        return ClipLabels.model_validate(
            {
                "clip_id": name,
                "fps": fps,
                "tags": list(tags),
                "fighter": {"stance": stance, "track_hint": track_hint},
                "strikes": strikes,
                "errors": errors,
                "notes": notes,
                "labeler": labeler,
                "label_version": label_version,
            }
        )
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()
        )
        raise ConversionError(f"{source}: {problems}") from exc


def _add_point(
    images: dict[int, list[tuple[str, dict[str, str]]]],
    frame: int,
    label: str,
    attributes: dict[str, str],
) -> None:
    images.setdefault(frame, []).append((label, attributes))


def labels_to_cvat(labels: ClipLabels, *, width: int = 1280, height: int = 720) -> ET.Element:
    """Build a "CVAT for images 1.1" document from labels.

    Each event becomes a single point at the frame centre (``width`` and ``height`` in
    pixels); the position carries no meaning.
    """
    images: dict[int, list[tuple[str, dict[str, str]]]] = {}
    for s in labels.strikes:
        _add_point(
            images,
            ms_to_frame(s.t_ms, labels.fps),
            STRIKE,
            {"hand": s.hand, "type": s.type, "target": s.target},
        )
    for e in labels.errors:
        _add_point(images, ms_to_frame(e.t_ms, labels.fps), ERROR, {"hand": e.hand, "type": e.type})
    for n in labels.notes:
        _add_point(images, ms_to_frame(n.start_ms, labels.fps), SKIP_START, {"reason": n.reason})
        _add_point(images, ms_to_frame(n.end_ms, labels.fps), SKIP_END, {})

    root = ET.Element("annotations")
    ET.SubElement(root, "version").text = "1.1"
    task = ET.SubElement(ET.SubElement(root, "meta"), "task")
    ET.SubElement(task, "name").text = labels.clip_id
    ET.SubElement(task, "mode").text = "interpolation"
    for frame in sorted(images):
        image = ET.SubElement(
            root,
            "image",
            id=str(frame),
            name=f"frame_{frame:06d}",
            width=str(width),
            height=str(height),
        )
        for label, attributes in images[frame]:
            point = ET.SubElement(
                image,
                "points",
                label=label,
                source="manual",
                occluded="0",
                points=f"{width / 2:.2f},{height / 2:.2f}",
                z_order="0",
            )
            for key, value in attributes.items():
                ET.SubElement(point, "attribute", name=key).text = value
    ET.indent(root)
    return root


def snap_to_frames(labels: ClipLabels) -> ClipLabels:
    """Labels with every time moved to its nearest frame time (what CVAT can represent)."""

    def snap(t_ms: int) -> int:
        return frame_to_ms(ms_to_frame(t_ms, labels.fps), labels.fps)

    return labels.model_copy(
        update={
            "strikes": [s.model_copy(update={"t_ms": snap(s.t_ms)}) for s in labels.strikes],
            "errors": [e.model_copy(update={"t_ms": snap(e.t_ms)}) for e in labels.errors],
            "notes": [
                n.model_copy(update={"start_ms": snap(n.start_ms), "end_ms": snap(n.end_ms)})
                for n in labels.notes
            ],
        }
    )


def dump_labels(labels: ClipLabels) -> str:
    """Label file text: JSON, two-space indent, trailing newline."""
    return labels.model_dump_json(indent=2) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m eval.cvat_to_labels", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_in = sub.add_parser("to-labels", help="CVAT XML export -> eval/labels/<clip_id>.json")
    p_in.add_argument("xml", type=Path)
    p_in.add_argument("--fps", type=float, required=True, help="source fps of the clip")
    p_in.add_argument("--stance", required=True, choices=["orthodox", "southpaw"])
    p_in.add_argument("--tags", default="", help="comma-separated tags (FRD 6.5)")
    p_in.add_argument("--clip-id", default=None, help="default: CVAT task name")
    p_in.add_argument("--track-hint", default=None, help="which person is the fighter")
    p_in.add_argument("--labeler", default=DEFAULT_LABELER)
    p_in.add_argument("--label-version", type=int, default=1)
    p_in.add_argument("--out", type=Path, default=Path("eval/labels"), help="output directory")

    p_out = sub.add_parser("to-cvat", help="label JSON -> CVAT for images 1.1 XML")
    p_out.add_argument("labels", type=Path)
    p_out.add_argument("--out", type=Path, default=None, help="default: <clip_id>.xml")
    p_out.add_argument("--width", type=int, default=1280, help="frame width, pixels")
    p_out.add_argument("--height", type=int, default=720, help="frame height, pixels")
    args = parser.parse_args(argv)

    try:
        if args.command == "to-labels":
            root = ET.parse(args.xml).getroot()
            labels = cvat_to_labels(
                root,
                fps=args.fps,
                stance=args.stance,
                tags=[t.strip() for t in args.tags.split(",") if t.strip()],
                clip_id=args.clip_id,
                track_hint=args.track_hint,
                labeler=args.labeler,
                label_version=args.label_version,
                source=str(args.xml),
            )
            args.out.mkdir(parents=True, exist_ok=True)
            target = args.out / f"{labels.clip_id}.json"
            target.write_text(dump_labels(labels), encoding="utf-8")
            print(
                f"wrote {target}: {len(labels.strikes)} strikes, {len(labels.errors)} errors, "
                f"{len(labels.notes)} skipped spans"
            )
        else:
            labels = load_labels(args.labels)
            target = args.out or Path(f"{labels.clip_id}.xml")
            tree = ET.ElementTree(labels_to_cvat(labels, width=args.width, height=args.height))
            tree.write(target, encoding="utf-8", xml_declaration=True)
            print(f"wrote {target}")
    except (ConversionError, ValidationError, ET.ParseError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
