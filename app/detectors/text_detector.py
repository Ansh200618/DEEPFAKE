"""
Text / Fake-News Detector
=========================
Techniques used
---------------
1. Clickbait & Sensationalism Score – ALL-CAPS ratio, excessive punctuation,
   emotional trigger words, superlatives.
2. Readability & Complexity – Flesch Reading Ease; very low or very high
   scores correlate with machine-generated or deliberately misleading text.
3. Factual Density – ratio of numerical data, named entities (simple regex),
   and hedge words; fake news tends to be vague.
4. Emotional Manipulation – count of fear/anger/urgency words.
5. Structural Red-Flags – very short paragraphs, lack of source attribution,
   missing byline indicators.
All five sub-scores are blended into a single composite fakeness probability.
"""
from __future__ import annotations

import math
import re
from typing import Dict, Tuple

from app.utils.helpers import DetectionResult, clamp, label_from_score

# ── word lists (embedded – no external downloads needed) ─────────────────────
_EMOTIONAL_WORDS = {
    "shocking", "unbelievable", "horrifying", "disgusting", "outrageous",
    "scandal", "breaking", "urgent", "alert", "warning", "danger",
    "exposed", "revealed", "secret", "conspiracy", "cover-up", "fraud",
    "fake", "hoax", "lies", "cheating", "corrupt", "evil", "destroy",
    "catastrophe", "disaster", "crisis", "threat", "attack", "war",
    "hate", "kill", "murder", "dead", "death", "tragedy", "panic",
    "fear", "terror", "nightmare", "explode", "collapse", "ban", "forced",
    "banned", "censored", "suppressed", "banned", "silenced", "arrest",
    "criminal", "illegal", "stolen", "robbed", "hijacked",
}

_CLICKBAIT_PHRASES = [
    r"\byou won'?t believe\b",
    r"\bwhat (they|he|she) don'?t want you to know\b",
    r"\bthis will (shock|blow|amaze)\b",
    r"\b(doctors?|scientists?|experts?) hate\b",
    r"\bone weird trick\b",
    r"\bthe truth about\b",
    r"\bwhat happens next\b",
    r"\bshare before (it'?s )?deleted\b",
    r"\bgo viral\b",
    r"\bmust[ -]see\b",
    r"\bbreaking[:\s!]",
    r"\bexclusive[:\s!]",
]

_HEDGE_WORDS = {
    "allegedly", "reportedly", "sources say", "anonymous",
    "according to insiders", "some say", "many believe", "it is rumoured",
    "unverified", "unconfirmed", "could be", "might be", "possibly",
    "apparently", "it seems", "people are saying",
}

# ── weights ───────────────────────────────────────────────────────────────────
_CLICK_WEIGHT    = 0.30
_READ_WEIGHT     = 0.20
_FACT_WEIGHT     = 0.20
_EMOTION_WEIGHT  = 0.20
_STRUCT_WEIGHT   = 0.10


class TextDetector:
    """Stateless text / news fake-content analyser."""

    def analyze(self, text: str) -> DetectionResult:
        """Analyse a block of *text* and return a :class:`DetectionResult`."""
        text = text.strip()
        if len(text) < 30:
            return DetectionResult(
                label="INSUFFICIENT_DATA", confidence=0.0, score=0.0,
                flags=["Text too short for reliable analysis (< 30 chars)"]
            )

        click_score,   click_val   = self._clickbait_score(text)
        read_score,    read_val    = self._readability_score(text)
        fact_score,    fact_val    = self._factual_density_score(text)
        emotion_score, emotion_val = self._emotion_score(text)
        struct_score,  struct_val  = self._structural_score(text)

        composite = clamp(
            click_score   * _CLICK_WEIGHT
            + read_score  * _READ_WEIGHT
            + fact_score  * _FACT_WEIGHT
            + emotion_score * _EMOTION_WEIGHT
            + struct_score  * _STRUCT_WEIGHT
        )

        flags: list[str] = []
        if click_score > 0.5:
            flags.append("Clickbait / sensationalist language detected")
        if read_score > 0.5:
            flags.append("Readability anomaly – may be machine-generated text")
        if fact_score > 0.5:
            flags.append("Low factual density – vague or unsubstantiated claims")
        if emotion_score > 0.5:
            flags.append("High emotional-manipulation language")
        if struct_score > 0.5:
            flags.append("Structural red-flags: missing attribution or sources")

        label = label_from_score(composite)
        confidence = composite if label == "FAKE" else (1.0 - composite)

        return DetectionResult(
            label=label,
            confidence=clamp(confidence),
            score=composite,
            details={
                "clickbait":           click_val,
                "readability_anomaly": read_val,
                "factual_density":     fact_val,
                "emotion_intensity":   emotion_val,
                "structural_flags":    struct_val,
            },
            flags=flags,
        )

    # ------------------------------------------------------------------
    # Sub-scorers
    # ------------------------------------------------------------------
    @staticmethod
    def _clickbait_score(text: str) -> Tuple[float, float]:
        lower = text.lower()
        words = re.findall(r"\b\w+\b", text)
        if not words:
            return 0.0, 0.0

        caps_ratio = sum(1 for w in words if w.isupper() and len(w) > 2) / len(words)
        excl_ratio = text.count("!") / max(len(words), 1)
        question_ratio = text.count("?") / max(len(words), 1)

        phrase_hits = sum(
            1 for p in _CLICKBAIT_PHRASES if re.search(p, lower)
        )

        raw = caps_ratio * 2.0 + excl_ratio * 10.0 + phrase_hits * 0.2 + question_ratio * 5.0
        return clamp(raw / 3.0), raw

    @staticmethod
    def _readability_score(text: str) -> Tuple[float, float]:
        """
        Flesch Reading Ease: 0 (hard) – 100 (easy).
        Machine-generated propaganda is often extremely easy (> 80) or
        deliberately convoluted (< 20).
        """
        sentences = [s.strip() for s in re.split(r"[.!?]+", text) if s.strip()]
        words     = re.findall(r"\b[a-zA-Z']+\b", text)
        syllables = sum(_count_syllables(w) for w in words)

        n_sent = max(len(sentences), 1)
        n_word = max(len(words), 1)

        flesch = 206.835 - 1.015 * (n_word / n_sent) - 84.6 * (syllables / n_word)
        flesch = max(0.0, min(100.0, flesch))

        # Penalise extreme ends
        if flesch > 85 or flesch < 20:
            anomaly = abs(flesch - 52.5) / 47.5
        else:
            anomaly = abs(flesch - 52.5) / 95.0

        return clamp(anomaly), flesch

    @staticmethod
    def _factual_density_score(text: str) -> Tuple[float, float]:
        """
        High-fakeness ↔ low factual density (few numbers, few proper nouns,
        many hedge words).
        """
        words  = re.findall(r"\b\w+\b", text)
        n_word = max(len(words), 1)

        numbers        = len(re.findall(r"\b\d[\d,.%]*\b", text))
        proper_nouns   = len(re.findall(r"\b[A-Z][a-z]{2,}\b", text))
        hedge_count    = sum(1 for h in _HEDGE_WORDS if h in text.lower())

        density = (numbers + proper_nouns * 0.5) / n_word
        hedge_penalty = hedge_count * 0.05

        raw_score = clamp(1.0 - density * 5.0 + hedge_penalty)
        return raw_score, density

    @staticmethod
    def _emotion_score(text: str) -> Tuple[float, float]:
        lower = text.lower()
        words = re.findall(r"\b\w+\b", lower)
        n_word = max(len(words), 1)

        hit_count = sum(1 for w in words if w in _EMOTIONAL_WORDS)
        intensity = hit_count / n_word

        score = clamp(intensity / 0.15)
        return score, intensity

    @staticmethod
    def _structural_score(text: str) -> Tuple[float, float]:
        flags = 0.0
        lower = text.lower()

        # No attribution / source reference
        if not re.search(r"\b(according to|source[s]?|cited|ref[s]?:|via)\b", lower):
            flags += 0.4
        # No date mention
        if not re.search(
            r"\b(\d{4}|\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*)\b",
            lower
        ):
            flags += 0.2
        # Very short (< 50 words)
        if len(re.findall(r"\b\w+\b", text)) < 50:
            flags += 0.2
        # Excessive capitalisation of entire sentences
        sentences = [s.strip() for s in re.split(r"[.!?]+", text) if len(s.strip()) > 8]
        all_caps_sents = sum(1 for s in sentences if s.upper() == s) if sentences else 0
        if all_caps_sents / max(len(sentences), 1) > 0.3:
            flags += 0.2

        return clamp(flags), flags


# ── helpers ───────────────────────────────────────────────────────────────────
def _count_syllables(word: str) -> int:
    """Rough English syllable counter."""
    word = word.lower().strip("'")
    if len(word) <= 3:
        return 1
    word = re.sub(r"[^a-z]", "", word)
    vowels = re.findall(r"[aeiouy]+", word)
    count  = len(vowels)
    if word.endswith("e"):
        count -= 1
    return max(count, 1)
