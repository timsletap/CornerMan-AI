"""License normalization and the policy for which clips may be collected.

Only footage we may use and annotate is kept: public domain, CC0, CC BY, CC BY-SA, and
footage the owner recorded with the fighters' consent. NonCommercial licenses are kept
only with ``allow_nc`` (CornerMan has a paid tier, so they are off by default).
NoDerivatives licenses are always rejected: annotated overlays are derivative works.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

OWN = "OWN"
"""Footage the owner recorded, with consent tracked per fighter (local ingest)."""

_URL_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"creativecommons\.org/publicdomain/zero/"), "CC0"),
    (re.compile(r"creativecommons\.org/publicdomain/mark/"), "PDM"),
    (re.compile(r"creativecommons\.org/licenses/(by(?:-nc)?(?:-sa|-nd)?)/([\d.]+)"), "CC"),
]

_NAME_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^(cc0|cc-zero|cc zero)", re.I), "CC0"),
    (re.compile(r"^(public domain|pd\b|pd-|pdm)", re.I), "PD"),
    (
        re.compile(r"^cc[\s-]+(by(?:[\s-]+nc)?(?:[\s-]+sa|[\s-]+nd)?)(?:[\s-]+([\d.]+))?", re.I),
        "CC",
    ),
]


def normalize(name_or_url: str | None) -> str | None:
    """Map a license name or URL to an SPDX-like id such as ``CC-BY-SA-4.0``.

    Returns None when the license is missing or not recognized.
    """
    if not name_or_url:
        return None
    text = name_or_url.strip()
    for pattern, kind in _URL_PATTERNS:
        m = pattern.search(text)
        if m:
            if kind != "CC":
                return kind
            return f"CC-{m.group(1).upper()}-{m.group(2)}"
    for pattern, kind in _NAME_PATTERNS:
        m = pattern.search(text)
        if m:
            if kind != "CC":
                return kind
            parts = re.split(r"[\s-]+", m.group(1).upper())
            version = f"-{m.group(2)}" if m.group(2) else ""
            return "CC-" + "-".join(parts) + version
    if text.upper() == OWN:
        return OWN
    return None


@dataclass(frozen=True)
class LicenseDecision:
    allowed: bool
    reason: str


def check(license_id: str | None, allow_nc: bool = False) -> LicenseDecision:
    """Decide whether a normalized license may be collected."""
    if license_id is None:
        return LicenseDecision(False, "no recognized license")
    if license_id in {OWN, "CC0", "PD", "PDM"}:
        return LicenseDecision(True, license_id)
    if not license_id.startswith("CC-BY"):
        return LicenseDecision(False, f"unsupported license {license_id}")
    if "-ND" in license_id:
        return LicenseDecision(False, f"{license_id} forbids derivatives (overlays, labels)")
    if "-NC" in license_id and not allow_nc:
        return LicenseDecision(False, f"{license_id} is non-commercial (use --allow-nc)")
    return LicenseDecision(True, license_id)


def requires_attribution(license_id: str) -> bool:
    return license_id.startswith("CC-BY")
