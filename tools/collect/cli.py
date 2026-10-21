"""Command line for the licensed clip collector.

Usage:
    python -m tools.collect search  --source wikimedia --query "boxing heavy bag" [--limit 20]
    python -m tools.collect fetch   --source archive   --query "boxing training" [--pose-check]
    python -m tools.collect local   path/to/my_footage --consent path/to/consent.yaml
    python -m tools.collect credits [--out CREDITS.md]

Sources: wikimedia (Wikimedia Commons), archive (Internet Archive), youtube (Creative
Commons only; needs YOUTUBE_API_KEY). Accepted clips land in eval/clips/ with a
provenance record in eval/clips/manifest.jsonl. Nothing here is committed to git.
"""

from __future__ import annotations

import argparse
import os
import ssl
import sys
from pathlib import Path

import httpx

from tools.collect import licenses, quality
from tools.collect.collector import (
    DEFAULT_MAX_MB,
    Settings,
    Summary,
    collect_from_source,
    collect_local,
)
from tools.collect.manifest import Manifest, credits_markdown
from tools.collect.sources import USER_AGENT, ArchiveSource, Source, WikimediaSource, YouTubeSource

DEFAULT_CLIPS_DIR = Path("eval/clips")
SOURCES = ("wikimedia", "archive", "youtube")


def make_source(name: str, client: httpx.Client) -> Source:
    if name == "wikimedia":
        return WikimediaSource(client)
    if name == "archive":
        return ArchiveSource(client)
    return YouTubeSource(client, os.environ.get("YOUTUBE_API_KEY", ""))


def _settings(args: argparse.Namespace) -> Settings:
    rules = quality.QualityRules(min_height=args.min_height, max_cuts_per_min=args.max_cuts_per_min)
    person_check = None
    if getattr(args, "pose_check", False):
        model = args.pose_model

        def person_check(path: Path) -> float:
            return quality.person_fraction(path, model)

    return Settings(
        clips_dir=args.clips_dir,
        rules=rules,
        allow_nc=getattr(args, "allow_nc", False),
        max_bytes=args.max_mb << 20,
        person_check=person_check,
    )


def _print_summary(summary: Summary) -> None:
    for r in summary.accepted:
        print(f"  + {r.clip_id}  {r.width}x{r.height} {r.fps}fps {r.duration_s}s  [{r.license}]")
    for r in summary.rejected:
        print(f"  - {r.title}: {'; '.join(r.reject_reasons)}")
    for s in summary.skipped:
        print(f"  . {s}")
    print(
        f"accepted {len(summary.accepted)}, rejected {len(summary.rejected)}, "
        f"skipped {len(summary.skipped)}"
    )
    if summary.accepted:
        print(
            "Next: label the new clips, then add them to eval/splits.yaml "
            "(split by fighter; never tune on test)."
        )


def _client() -> httpx.Client:
    # Use the OS certificate store when available (corporate proxies, Windows roots).
    verify: ssl.SSLContext | bool = True
    try:
        import truststore

        verify = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except ImportError:
        pass
    return httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=60.0, verify=verify)


def cmd_search(args: argparse.Namespace) -> int:
    with _client() as client:
        for c in make_source(args.source, client).search(args.query, args.limit):
            decision = licenses.check(c.license_id, args.allow_nc)
            mark = "OK  " if decision.allowed else "SKIP"
            size = f"{c.width}x{c.height}" if c.height else "?"
            print(f"{mark} [{decision.reason}] {size} {c.title}\n     {c.source_url}")
    return 0


def cmd_fetch(args: argparse.Namespace) -> int:
    with _client() as client:
        source = make_source(args.source, client)
        _print_summary(collect_from_source(source, client, args.query, args.limit, _settings(args)))
    return 0


def cmd_local(args: argparse.Namespace) -> int:
    _print_summary(collect_local(args.folder, args.consent, _settings(args)))
    return 0


def cmd_credits(args: argparse.Namespace) -> int:
    text = credits_markdown(Manifest(args.clips_dir).accepted())
    if args.out:
        args.out.write_text(text, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(text, end="")
    return 0


def _add_common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--clips-dir", type=Path, default=DEFAULT_CLIPS_DIR)
    p.add_argument("--min-height", type=int, default=quality.QualityRules.min_height)
    p.add_argument("--max-cuts-per-min", type=float, default=quality.QualityRules.max_cuts_per_min)
    p.add_argument("--max-mb", type=int, default=DEFAULT_MAX_MB)
    p.add_argument("--pose-check", action="store_true", help="require a visible person (slow)")
    p.add_argument("--pose-model", default="yolov8m-pose.pt")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m tools.collect",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    for name, func, help_text in [
        ("search", cmd_search, "list candidates and their license status"),
        ("fetch", cmd_fetch, "download, gate, and file candidates"),
    ]:
        p = sub.add_parser(name, help=help_text)
        p.add_argument("--source", choices=SOURCES, required=True)
        p.add_argument("--query", required=True)
        p.add_argument("--limit", type=int, default=20)
        p.add_argument("--allow-nc", action="store_true", help="also accept NonCommercial")
        _add_common(p)
        p.set_defaults(func=func)

    p = sub.add_parser("local", help="ingest your own footage with a consent sheet")
    p.add_argument("folder", type=Path)
    p.add_argument("--consent", type=Path, required=True)
    _add_common(p)
    p.set_defaults(func=cmd_local)

    p = sub.add_parser("credits", help="print attributions for accepted clips")
    p.add_argument("--clips-dir", type=Path, default=DEFAULT_CLIPS_DIR)
    p.add_argument("--out", type=Path)
    p.set_defaults(func=cmd_credits)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except (ValueError, httpx.HTTPError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
