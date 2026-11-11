"""Totem rules shared by normal, nested and delayed event effects."""
NEGATIVE_TAGS = {"die", "away", "locate_lock", "vertigo"}


def is_negative_buff(buff: list) -> bool:
    return bool(NEGATIVE_TAGS.intersection(buff[6:])) or buff[3] < 0 or buff[4] < 0


def positive_buff_parts(buff: list) -> list | None:
    """Keep beneficial parts of a mixed buff, preserving its duration and triggers."""
    result = buff[:6] + [tag for tag in buff[6:] if tag not in NEGATIVE_TAGS]
    result[3] = max(0, result[3])
    result[4] = max(result[3], result[4], 0)
    if result[3] == result[4] == 0 and not result[5] and not result[6:]:
        return None
    return result
