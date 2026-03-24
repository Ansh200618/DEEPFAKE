"""Shared helper types and utilities."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class DetectionResult:
    """Standardised result returned by every detector."""

    label: str          # "FAKE" | "REAL" | "SUSPICIOUS"
    confidence: float   # 0.0 – 1.0
    score: float        # raw composite score (higher → more likely fake)
    details: Dict[str, float] = field(default_factory=dict)
    flags: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "confidence": round(self.confidence * 100, 2),
            "score": round(self.score, 4),
            "details": {k: round(v, 4) for k, v in self.details.items()},
            "flags": self.flags,
        }


def clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    """Clamp *value* to [lo, hi]."""
    return max(lo, min(hi, value))


def softmax(values: List[float]) -> List[float]:
    """Numerically-stable softmax over a list of floats."""
    mx = max(values)
    exps = [math.exp(v - mx) for v in values]
    total = sum(exps)
    return [e / total for e in exps]


def label_from_score(score: float, fake_thresh: float = 0.55,
                     suspicious_thresh: float = 0.40) -> str:
    """Map a continuous *score* to a human-readable label."""
    if score >= fake_thresh:
        return "FAKE"
    if score >= suspicious_thresh:
        return "SUSPICIOUS"
    return "REAL"
