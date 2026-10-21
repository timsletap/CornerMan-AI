"""Licensed clip collector: license policy, source parsing, quality gates, ingest."""

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import httpx
import pytest

from tools.collect import collector, licenses, quality
from tools.collect.cli import main
from tools.collect.collector import Settings, collect_from_source, collect_local
from tools.collect.manifest import Manifest, credits_markdown
from tools.collect.sources import ArchiveSource, Candidate, WikimediaSource, YouTubeSource

needs_ffmpeg = pytest.mark.skipif(
    shutil.which("ffprobe") is None or shutil.which("ffmpeg") is None,
    reason="ffmpeg/ffprobe not on PATH",
)

GOOD = quality.ProbeResult(width=1280, height=720, fps=30.0, duration_s=60.0)


# --- licenses ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("CC BY-SA 4.0", "CC-BY-SA-4.0"),
        ("cc-by-3.0", "CC-BY-3.0"),
        ("CC BY-NC-ND 4.0", "CC-BY-NC-ND-4.0"),
        ("https://creativecommons.org/licenses/by-nc/2.0/", "CC-BY-NC-2.0"),
        ("http://creativecommons.org/publicdomain/zero/1.0/", "CC0"),
        ("https://creativecommons.org/publicdomain/mark/1.0/", "PDM"),
        ("Public domain", "PD"),
        ("CC0", "CC0"),
        ("own", "OWN"),
        ("All rights reserved", None),
        ("", None),
        (None, None),
    ],
)
def test_normalize(raw: str | None, expected: str | None) -> None:
    assert licenses.normalize(raw) == expected


@pytest.mark.parametrize(
    ("license_id", "allow_nc", "allowed"),
    [
        ("CC-BY-4.0", False, True),
        ("CC-BY-SA-3.0", False, True),
        ("CC0", False, True),
        ("PD", False, True),
        ("OWN", False, True),
        ("CC-BY-NC-4.0", False, False),
        ("CC-BY-NC-4.0", True, True),
        ("CC-BY-ND-4.0", True, False),
        ("CC-BY-NC-ND-4.0", True, False),
        (None, True, False),
    ],
)
def test_license_policy(license_id: str | None, allow_nc: bool, allowed: bool) -> None:
    assert licenses.check(license_id, allow_nc).allowed is allowed


# --- sources ----------------------------------------------------------------------


def _client(routes: dict[str, Any]) -> httpx.Client:
    """MockTransport client: route by URL path -> JSON body (or callable(request))."""

    def handler(request: httpx.Request) -> httpx.Response:
        body = routes[request.url.path]
        if callable(body):
            body = body(request)
        if isinstance(body, bytes):
            return httpx.Response(200, content=body)
        return httpx.Response(200, json=body)

    return httpx.Client(transport=httpx.MockTransport(handler))


def _wiki_page(index: int, title: str, mime: str, license_name: str) -> dict[str, Any]:
    return {
        "index": index,
        "title": f"File:{title}",
        "imageinfo": [
            {
                "url": f"https://upload.wikimedia.org/{title}",
                "descriptionurl": f"https://commons.wikimedia.org/wiki/File:{title}",
                "mime": mime,
                "width": 1920,
                "height": 1080,
                "duration": 12.5,
                "extmetadata": {
                    "LicenseShortName": {"value": license_name},
                    "Artist": {"value": '<a href="x">Jane &amp; Co</a>'},
                },
            }
        ],
    }


def test_wikimedia_parses_videos_in_rank_order() -> None:
    pages = {
        "2": _wiki_page(2, "b.webm", "video/webm", "CC BY 4.0"),
        "1": _wiki_page(1, "a.webm", "video/webm", "CC BY-SA 4.0"),
        "3": _wiki_page(3, "c.jpg", "image/jpeg", "CC0"),
    }
    seen: dict[str, str] = {}

    def api(request: httpx.Request) -> dict[str, Any]:
        seen.update(request.url.params)
        return {"query": {"pages": pages}}

    out = WikimediaSource(_client({"/w/api.php": api})).search("boxing", 10)

    assert [c.title for c in out] == ["a.webm", "b.webm"]
    assert out[0].creator == "Jane & Co"
    assert out[0].license_id == "CC-BY-SA-4.0"
    assert (out[0].height, out[0].duration_s) == (1080, 12.5)
    assert seen["gsrsearch"] == "boxing filetype:video"


def test_archive_picks_largest_original_mp4() -> None:
    routes = {
        "/advancedsearch.php": {
            "response": {
                "docs": [
                    {
                        "identifier": "bag1",
                        "title": "Bag work",
                        "creator": ["A", "B"],
                        "licenseurl": "https://creativecommons.org/licenses/by/4.0/",
                    },
                    {"identifier": "audio1", "title": "Podcast", "licenseurl": "x"},
                ]
            }
        },
        "/metadata/bag1": {
            "files": [
                {"name": "bag.mp4", "source": "derivative", "size": "999999"},
                {"name": "bag_orig.mp4", "source": "original", "size": "500", "length": "01:30"},
                {"name": "bag.ogv", "source": "derivative", "size": "10"},
            ]
        },
        "/metadata/audio1": {"files": [{"name": "a.mp3", "source": "original"}]},
    }
    out = ArchiveSource(_client(routes)).search("boxing", 5)

    assert len(out) == 1
    c = out[0]
    assert c.download_url == "https://archive.org/download/bag1/bag_orig.mp4"
    assert c.creator == "A, B"
    assert c.license_id == "CC-BY-4.0"
    assert c.duration_s == 90.0


def test_youtube_rechecks_license_on_each_video() -> None:
    routes = {
        "/youtube/v3/search": {"items": [{"id": {"videoId": "cc1"}}, {"id": {"videoId": "std1"}}]},
        "/youtube/v3/videos": {
            "items": [
                {"id": "cc1", "status": {"license": "creativeCommon"}, "snippet": {"title": "T"}},
                {"id": "std1", "status": {"license": "youtube"}, "snippet": {"title": "U"}},
            ]
        },
    }
    out = YouTubeSource(_client(routes), "key").search("bag", 5)

    assert [c.source_url for c in out] == ["https://www.youtube.com/watch?v=cc1"]
    assert out[0].license_id == "CC-BY-3.0"
    assert out[0].download_url is None


def test_youtube_requires_api_key() -> None:
    with pytest.raises(ValueError, match="YOUTUBE_API_KEY"):
        YouTubeSource(_client({}), "")


# --- quality ----------------------------------------------------------------------


def test_good_clip_passes() -> None:
    assert quality.check_rules(GOOD, [10.0], quality.QualityRules()) == []


@pytest.mark.parametrize(
    ("info", "cuts", "people", "expected"),
    [
        (quality.ProbeResult(720, 1280, 30, 60), [], None, "portrait"),
        (quality.ProbeResult(640, 360, 30, 60), [], None, "height 360px"),
        (quality.ProbeResult(1280, 720, 15, 60), [], None, "15.0 fps"),
        (quality.ProbeResult(1280, 720, 30, 3), [], None, "duration 3.0s"),
        (GOOD, [1.0, 2.0, 3.0], None, "3 scene cuts"),
        (GOOD, [], 0.5, "person clearly visible in 50%"),
    ],
)
def test_rules_reject(
    info: quality.ProbeResult, cuts: list[float], people: float | None, expected: str
) -> None:
    reasons = quality.check_rules(info, cuts, quality.QualityRules(), people)
    assert any(expected in r for r in reasons), reasons


def test_parse_cut_times() -> None:
    stderr = (
        "[Parsed_showinfo_1 @ 0x1] n:   0 pts:  51200 pts_time:4.0     duration:512\n"
        "[Parsed_showinfo_1 @ 0x1] n:   1 pts: 102400 pts_time:8.25    duration:512\n"
    )
    assert quality.parse_cut_times(stderr) == [4.0, 8.25]


def test_measured_fps_prefers_packet_count() -> None:
    # WebM headers often report the 1/1000 time base as the rate.
    stream = {"avg_frame_rate": "30000/1", "nb_read_packets": "304"}
    assert quality.measured_fps(stream, 10.0) == pytest.approx(30.4)
    assert quality.measured_fps({"avg_frame_rate": "30000/1001"}, 0) == pytest.approx(29.97, 0.01)
    assert quality.measured_fps({"avg_frame_rate": "0/0"}, 0) == 0.0


# --- collection -------------------------------------------------------------------


class FakeSource:
    name = "wikimedia"

    def __init__(self, candidates: list[Candidate]) -> None:
        self.candidates = candidates

    def search(self, query: str, limit: int) -> list[Candidate]:
        return self.candidates[:limit]


def _cand(name: str, license_raw: str = "CC BY 4.0", height: int | None = 720) -> Candidate:
    return Candidate(
        source="wikimedia",
        source_url=f"https://commons.wikimedia.org/wiki/File:{name}",
        download_url=f"https://upload.wikimedia.org/{name}",
        title=name,
        creator="Jane",
        license_raw=license_raw,
        license_url=None,
        height=height,
    )


@pytest.fixture
def fake_media(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Probe/cut results keyed by file content, so tests choose what each 'video' is."""
    by_content: dict[bytes, tuple[quality.ProbeResult, list[float]]] = {
        b"good": (GOOD, []),
        b"good2": (GOOD, []),
        b"edited": (GOOD, [float(i) for i in range(20)]),
    }
    monkeypatch.setattr(quality, "probe", lambda p: by_content[p.read_bytes()][0])
    monkeypatch.setattr(quality, "detect_cuts", lambda p: by_content[p.read_bytes()][1])
    return {"by_content": by_content}


def test_collect_accepts_rejects_skips_and_dedups(tmp_path: Path, fake_media: Any) -> None:
    contents = {"a.webm": b"good", "b.webm": b"edited", "dup.webm": b"good", "c.mp4": b"good2"}
    client = _client({f"/{name}": body for name, body in contents.items()})
    source = FakeSource(
        [
            _cand("a.webm"),
            _cand("b.webm"),
            _cand("nd.webm", "CC BY-ND 4.0"),
            _cand("small.webm", height=240),
            _cand("dup.webm"),
            _cand("c.mp4", "Public domain"),
        ]
    )
    settings = Settings(clips_dir=tmp_path / "clips")

    summary = collect_from_source(source, client, "q", 10, settings, log=lambda _: None)

    assert [r.title for r in summary.accepted] == ["a.webm", "c.mp4"]
    assert [r.title for r in summary.rejected] == ["b.webm"]
    assert "edited footage" in summary.rejected[0].reject_reasons[0]
    skipped = "\n".join(summary.skipped)
    assert "forbids derivatives" in skipped
    assert "height 240px" in skipped
    assert "duplicate" in skipped

    files = sorted(p.name for p in settings.clips_dir.iterdir())
    a = summary.accepted[0]
    assert a.file in files and a.file.endswith(".webm") and a.clip_id.startswith("wikimedia_a_")
    assert summary.accepted[1].file.endswith(".mp4")
    assert files == sorted([summary.accepted[0].file, summary.accepted[1].file, "manifest.jsonl"])

    manifest = Manifest(settings.clips_dir)
    assert [r.status for r in manifest.records] == ["accepted", "rejected", "accepted"]
    assert (
        manifest.records[0].attribution
        == f'"a.webm" by Jane, CC-BY-4.0, {_cand("a.webm").source_url}'
    )

    # Second run: everything already in the manifest is skipped without downloading.
    again = collect_from_source(source, client, "q", 10, settings, log=lambda _: None)
    assert again.accepted == [] and again.rejected == []
    assert sum("already in manifest" in s for s in again.skipped) == 3


def test_oversized_download_is_skipped_and_cleaned(tmp_path: Path, fake_media: Any) -> None:
    client = _client({"/big.webm": b"x" * 2048})
    settings = Settings(clips_dir=tmp_path / "clips", max_bytes=1024)

    summary = collect_from_source(
        FakeSource([_cand("big.webm")]), client, "q", 1, settings, log=lambda _: None
    )

    assert "larger than" in summary.skipped[0]
    assert not (settings.clips_dir / ".staging").exists()
    assert Manifest(settings.clips_dir).records == []


def test_credits_list_third_party_clips_only(tmp_path: Path, fake_media: Any) -> None:
    client = _client({"/a.webm": b"good"})
    settings = Settings(clips_dir=tmp_path)
    collect_from_source(FakeSource([_cand("a.webm")]), client, "q", 1, settings, log=print)
    text = credits_markdown(Manifest(tmp_path).accepted())
    assert "[a.webm](https://commons.wikimedia.org/wiki/File:a.webm) by Jane, CC-BY-4.0" in text


CONSENT = """
recorded_by: owner
fighters:
  f01: {consent: true, date: 2026-10-20}
  f02: {consent: false}
clips:
  bag.mp4: [f01]
  spar.mp4: [f01, f02]
  ghost.mp4: [f09]
"""


def test_local_ingest_requires_consent_for_every_fighter(tmp_path: Path, fake_media: Any) -> None:
    footage = tmp_path / "footage"
    footage.mkdir()
    for name, body in [
        ("bag.mp4", b"good"),
        ("spar.mp4", b"good2"),
        ("ghost.mp4", b"good2"),
        ("unlisted.mp4", b"good2"),
        ("notes.txt", b"x"),
    ]:
        (footage / name).write_bytes(body)
    consent = tmp_path / "consent.yaml"
    consent.write_text(CONSENT, encoding="utf-8")
    settings = Settings(clips_dir=tmp_path / "clips")

    summary = collect_local(footage, consent, settings)

    assert [(r.title, r.license, r.fighters) for r in summary.accepted] == [
        ("bag.mp4", "OWN", ["f01"])
    ]
    skipped = "\n".join(summary.skipped)
    assert "spar.mp4: fighter f02 has not consented" in skipped
    assert "ghost.mp4: fighter f09 has no consent entry" in skipped
    assert "unlisted.mp4 is not listed" in skipped
    assert (footage / "bag.mp4").exists()  # originals are copied, not moved
    assert "bag" not in credits_markdown(Manifest(settings.clips_dir).accepted())


def test_consent_file_rejects_unknown_keys(tmp_path: Path) -> None:
    path = tmp_path / "consent.yaml"
    path.write_text("recorded_by: me\nfighters: {}\nclips: {}\nnames: [Bob]\n", encoding="utf-8")
    with pytest.raises(ValueError, match="names"):
        collector.load_consent(path)


def test_example_consent_file_is_valid() -> None:
    example = Path(collector.__file__).with_name("consent.example.yaml")
    consent = collector.load_consent(example)
    assert collector.consent_problems(consent, "spar_round1.mp4") == []


def test_cli_credits(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["credits", "--clips-dir", str(tmp_path)]) == 0
    assert capsys.readouterr().out.startswith("# Clip credits")


# --- real ffmpeg ------------------------------------------------------------------


def _ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True, timeout=120)


@needs_ffmpeg
def test_probe_and_cut_detection_on_generated_video(tmp_path: Path) -> None:
    steady = tmp_path / "steady.mp4"
    _ffmpeg("-f", "lavfi", "-i", "testsrc=size=640x480:rate=25:duration=6", str(steady))
    cut = tmp_path / "cut.mp4"
    _ffmpeg(
        "-f", "lavfi", "-i", "color=c=black:size=640x480:rate=25:duration=3",
        "-f", "lavfi", "-i", "color=c=white:size=640x480:rate=25:duration=3",
        "-filter_complex", "[0:v][1:v]concat=n=2:v=1[v]", "-map", "[v]", str(cut),
    )  # fmt: skip

    info = quality.probe(steady)
    assert (info.width, info.height) == (640, 480)
    assert info.fps == pytest.approx(25, abs=0.5)
    assert info.duration_s == pytest.approx(6, abs=0.2)
    assert quality.detect_cuts(steady) == []
    assert [round(t) for t in quality.detect_cuts(cut)] == [3]


@needs_ffmpeg
def test_unreadable_file_is_rejected(tmp_path: Path) -> None:
    tmp = tmp_path / "x.mp4.part"
    tmp.write_bytes(b"not a video")
    record = collector.ClipRecord(clip_id="p", status="rejected", source="local", source_url="u")
    out = collector.ingest_file(tmp, record, Manifest(tmp_path), Settings(clips_dir=tmp_path))
    assert out is not None and out.status == "rejected"
    assert "unreadable" in out.reject_reasons[0]
    assert not tmp.exists()
    assert json.loads((tmp_path / "manifest.jsonl").read_text())["status"] == "rejected"
