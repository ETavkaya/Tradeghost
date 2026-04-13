from __future__ import annotations


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def normalize_score(raw: float, raw_min: float = -1.0, raw_max: float = 1.0) -> float:
    if raw_max == raw_min:
        return 50.0
    normalized = ((raw - raw_min) / (raw_max - raw_min)) * 100
    return clamp(normalized, 0.0, 100.0)

