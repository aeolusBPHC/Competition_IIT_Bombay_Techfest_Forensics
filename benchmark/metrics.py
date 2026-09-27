from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass
class DetectionMetrics:
    true_positive: int
    false_positive: int
    false_negative: int
    true_negative: int

    @property
    def precision(self) -> float:
        denominator = self.true_positive + self.false_positive

        if denominator == 0:
            return 0.0

        return self.true_positive / denominator

    @property
    def recall(self) -> float:
        denominator = self.true_positive + self.false_negative

        if denominator == 0:
            return 0.0

        return self.true_positive / denominator

    @property
    def f1(self) -> float:
        denominator = self.precision + self.recall

        if denominator == 0:
            return 0.0

        return (
            2
            * self.precision
            * self.recall
            / denominator
        )

    @property
    def false_positive_rate(self) -> float:
        denominator = self.false_positive + self.true_negative

        if denominator == 0:
            return 0.0

        return self.false_positive / denominator

    @property
    def detection_rate(self) -> float:
        return self.recall

    def to_dict(self) -> dict:
        return {
            "true_positive": self.true_positive,
            "false_positive": self.false_positive,
            "false_negative": self.false_negative,
            "true_negative": self.true_negative,
            "precision": self.precision,
            "recall": self.recall,
            "f1": self.f1,
            "false_positive_rate": self.false_positive_rate,
            "detection_rate": self.detection_rate,
        }


def calculate_metrics(
    expected: Iterable[str],
    detected: Iterable[str],
    universe: Iterable[str] | None = None,
) -> DetectionMetrics:

    expected_set = set(expected)
    detected_set = set(detected)

    true_positive = len(expected_set & detected_set)
    false_positive = len(detected_set - expected_set)
    false_negative = len(expected_set - detected_set)

    if universe is None:
        true_negative = 0
    else:
        universe_set = set(universe)

        true_negative = len(
            universe_set
            - expected_set
            - detected_set
        )

    return DetectionMetrics(
        true_positive=true_positive,
        false_positive=false_positive,
        false_negative=false_negative,
        true_negative=true_negative,
    )
