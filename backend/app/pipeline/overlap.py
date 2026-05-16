from pathlib import Path
from typing import Any

import yaml

RULES_DIR = Path(__file__).resolve().parent.parent / "rules"


def load_overlap_priority() -> list[str]:
    path = RULES_DIR / "overlap.yaml"
    with path.open() as f:
        data = yaml.safe_load(f)
    return list(data.get("priority", []))


def priority_rank(slug: str, priority: list[str]) -> int:
    try:
        return priority.index(slug)
    except ValueError:
        return len(priority)


def winner_for_instant(
    covering: list[str],
    priority: list[str],
) -> str | None:
    if not covering:
        return None
    return min(covering, key=lambda s: priority_rank(s, priority))
