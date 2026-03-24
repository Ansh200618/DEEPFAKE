"""
Tests for TextDetector.
"""
import pytest
from app.detectors.text_detector import TextDetector

detector = TextDetector()

FAKE_NEWS = (
    "SHOCKING!!! Scientists HATE this one weird trick that DESTROYS the deep state "
    "conspiracy the government doesn't want you to know about!! Share before DELETED!! "
    "BREAKING: Anonymous sources reveal CORRUPT elite plan to STEAL YOUR MONEY and "
    "BAN freedom FOREVER. This CRIMINAL cover-up exposed exclusively right here. "
    "Forward to everyone you know — our lives DEPEND on it!!! The TRUTH they're hiding."
)

REAL_NEWS = (
    "According to a report published on March 15, 2024 by the Reuters Institute for "
    "the Study of Journalism at Oxford University, global digital news consumption "
    "declined by approximately 8% in 2023 compared with the previous year. The study, "
    "which surveyed 93,000 respondents across 46 countries, found that trust in news "
    "organisations reached its lowest recorded level of 40% in the United States. "
    "Lead researcher Dr. Nic Newman cited increasing concerns about misinformation "
    "and political polarisation as contributing factors."
)

SHORT_TEXT = "Too short."


class TestTextDetector:

    def test_fake_news_scores_high(self):
        result = detector.analyze(FAKE_NEWS)
        assert result.label in ("FAKE", "SUSPICIOUS"), (
            f"Expected FAKE/SUSPICIOUS for obvious fake news, got {result.label} "
            f"(score={result.score:.3f})"
        )
        assert result.score > 0.4

    def test_real_news_scores_lower(self):
        result = detector.analyze(REAL_NEWS)
        # Real news should score lower than obvious fake news
        fake_score = detector.analyze(FAKE_NEWS).score
        assert result.score < fake_score

    def test_short_text_returns_insufficient(self):
        result = detector.analyze(SHORT_TEXT)
        assert result.label == "INSUFFICIENT_DATA"

    def test_empty_text_returns_insufficient(self):
        result = detector.analyze("   ")
        assert result.label == "INSUFFICIENT_DATA"

    def test_all_detail_keys_present(self):
        result = detector.analyze(REAL_NEWS)
        for key in ("clickbait", "readability_anomaly", "factual_density",
                    "emotion_intensity", "structural_flags"):
            assert key in result.details

    def test_to_dict_valid(self):
        d = detector.analyze(REAL_NEWS).to_dict()
        assert d["label"] in ("FAKE", "SUSPICIOUS", "REAL")
        assert 0.0 <= d["confidence"] <= 100.0

    def test_flags_populated_for_fake(self):
        result = detector.analyze(FAKE_NEWS)
        assert len(result.flags) > 0

    def test_score_range(self):
        for text in [FAKE_NEWS, REAL_NEWS]:
            result = detector.analyze(text)
            assert 0.0 <= result.score <= 1.0, f"Score out of range: {result.score}"
