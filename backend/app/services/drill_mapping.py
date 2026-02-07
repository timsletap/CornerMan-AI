"""Deterministic drill mapping for MVP. Maps error types to drill names."""

DRILL_MAP: dict[str, list[str]] = {
    "dropped_guard": [
        "Wall Touch Drill",
        "Mirror Guard Check",
        "Rubber Band Return Drill",
    ],
    "chicken_wing": [
        "Elbow Pin Shadow Boxing",
        "Towel Under Arm Drill",
        "Compact Punch Wall Drill",
    ],
    "other": [
        "General Shadow Boxing",
        "Heavy Bag Fundamentals",
    ],
}


def get_drills_for_error(error_type: str, max_drills: int = 2) -> list[str]:
    """Return drill names for a given error type."""
    drills = DRILL_MAP.get(error_type, DRILL_MAP["other"])
    return drills[:max_drills]
