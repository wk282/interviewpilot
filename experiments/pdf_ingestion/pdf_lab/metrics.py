from __future__ import annotations

import re


def normalize_for_comparison(value: str) -> str:
    return re.sub(r"\s+", "", value).lower()


def levenshtein_distance(left: str, right: str) -> int:
    if len(left) < len(right):
        left, right = right, left
    previous = list(range(len(right) + 1))
    for left_index, left_character in enumerate(left, start=1):
        current = [left_index]
        for right_index, right_character in enumerate(right, start=1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[right_index] + 1,
                    previous[right_index - 1] + (left_character != right_character),
                )
            )
        previous = current
    return previous[-1]


def character_error_rate(expected: str, actual: str) -> float:
    normalized_expected = normalize_for_comparison(expected)
    normalized_actual = normalize_for_comparison(actual)
    if not normalized_expected:
        return 0.0 if not normalized_actual else 1.0
    return levenshtein_distance(normalized_expected, normalized_actual) / len(
        normalized_expected
    )


def route_accuracy(expected: list[str], actual: list[str]) -> float:
    if len(expected) != len(actual):
        raise ValueError("Expected and actual page routes must have equal length")
    if not expected:
        return 1.0
    return sum(left == right for left, right in zip(expected, actual)) / len(expected)

