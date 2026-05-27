from datetime import timedelta


def parse_since(since: str) -> timedelta:
    since = since.strip().lower()
    if since.endswith("d"):
        return timedelta(days=int(since[:-1]))
    if since.endswith("w"):
        return timedelta(weeks=int(since[:-1]))
    raise ValueError(f"Invalid since value: {since}. Use e.g. 7d or 2w")
