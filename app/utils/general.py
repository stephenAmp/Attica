from sqlalchemy import cast, Float, func

def safe_divide(numerator, denominator)-> float | None:
    return cast(numerator, Float) / func.nullif(denominator, 0)


def difference(candidate, baseline):
    if candidate is None or baseline is None:
        return None

    return candidate - baseline