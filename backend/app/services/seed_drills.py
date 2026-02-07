"""Seed the drills table with predefined corrective drills."""

from sqlalchemy.orm import Session

from app.models.drill import Drill

SEED_DRILLS = [
    {
        "name": "Wall Touch Drill",
        "description": (
            "Stand with your back against a wall. Throw combinations, ensuring "
            "your rear hand touches the wall (near your chin) after every punch. "
            "This builds the habit of returning your hand to guard position."
        ),
        "error_type": "dropped_guard",
        "difficulty_level": 1,
    },
    {
        "name": "Mirror Guard Check",
        "description": (
            "Shadow box in front of a mirror. After every combination, freeze and "
            "check: Is your non-punching hand at chin level? If not, reset and "
            "repeat slower."
        ),
        "error_type": "dropped_guard",
        "difficulty_level": 1,
    },
    {
        "name": "Rubber Band Return Drill",
        "description": (
            "Attach a light resistance band to your wrist and a fixed point at "
            "chin height. The band provides tactile feedback when your hand drops "
            "below guard position."
        ),
        "error_type": "dropped_guard",
        "difficulty_level": 2,
    },
    {
        "name": "Partner Punish Drill",
        "description": (
            "Partner throws a light jab to your chin every time they see your "
            "guard drop. Start with slow combinations. Consequence-based learning."
        ),
        "error_type": "dropped_guard",
        "difficulty_level": 3,
    },
    {
        "name": "Elbow Pin Shadow Boxing",
        "description": (
            "Shadow box with a tennis ball squeezed between your elbow and ribcage "
            "on the punching side. If the ball drops, your elbow flared out "
            "(telegraphed). Focus on compact, tight punches."
        ),
        "error_type": "chicken_wing",
        "difficulty_level": 1,
    },
    {
        "name": "Towel Under Arm Drill",
        "description": (
            "Tuck a small towel under each armpit. Throw straights (jab/cross) "
            "without dropping the towel. This forces you to keep elbows tight and "
            "eliminate the wind-up."
        ),
        "error_type": "chicken_wing",
        "difficulty_level": 1,
    },
    {
        "name": "Compact Punch Wall Drill",
        "description": (
            "Stand 6 inches from a wall. Throw punches without your elbow touching "
            "the wall behind you. This eliminates the backward elbow pull that "
            "telegraphs your strikes."
        ),
        "error_type": "chicken_wing",
        "difficulty_level": 2,
    },
    {
        "name": "General Shadow Boxing",
        "description": (
            "3 rounds of 3 minutes shadow boxing with focus on form. Move around, "
            "throw combinations, and maintain guard throughout."
        ),
        "error_type": "other",
        "difficulty_level": 1,
    },
    {
        "name": "Heavy Bag Fundamentals",
        "description": (
            "3 rounds of 3 minutes on the heavy bag. Focus on clean technique: "
            "full extension, hip rotation, return to guard."
        ),
        "error_type": "other",
        "difficulty_level": 2,
    },
]


def seed_drills(db: Session) -> None:
    """Seed the drills table with initial data. Idempotent - skips existing."""
    for drill_data in SEED_DRILLS:
        existing = db.query(Drill).filter(Drill.name == drill_data["name"]).first()
        if not existing:
            db.add(Drill(**drill_data))
    db.commit()
