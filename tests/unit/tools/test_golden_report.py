"""The README's measured table is generated from, and must match, the committed report."""

import json

import pytest

from tools.golden_report import END, README, REPORT, START, main, readme_block, render_readme


def test_render_replaces_only_the_marked_block() -> None:
    text = f"before\n{START}\nold\n{END}\nafter\n"
    assert render_readme(text, f"{START}\nnew\n{END}") == f"before\n{START}\nnew\n{END}\nafter\n"


def test_render_requires_the_markers() -> None:
    with pytest.raises(ValueError, match="golden:start"):
        render_readme("no markers here", "block")


def test_block_numbers_all_come_from_the_report() -> None:
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    block = readme_block(report)
    assert str(report["throughput"]["stage1_seconds"]) in block
    assert str(report["throughput"]["stages23_ms"]) in block
    assert f"{report['detections']['strikes']} strikes" in block
    assert report["hardware"] in block
    assert report["git_sha"] in block


def test_committed_readme_matches_committed_report() -> None:
    assert START in README.read_text(encoding="utf-8")
    assert main(["check"]) == 0


def test_committed_report_reproduces_the_golden_output() -> None:
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    assert all(report["matches_golden"].values())
