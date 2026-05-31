def winner_for_instant(
    covering: list[str],
    ranks: dict[str, int],
) -> str | None:
    if not covering:
        return None
    return min(covering, key=lambda s: (ranks.get(s, 9999), s))
