"""Tests for classification (keyword + stub LLM leg)."""

from __future__ import annotations

from arxiv_daily.classify import keyword_classify
from arxiv_daily.config import SubtopicConfig


def test_keyword_classify_strong_match():
    subs = [
        SubtopicConfig(id="01_vla", keywords=("vla", "rt-2", "openvla")),
        SubtopicConfig(id="02_manipulation", keywords=("diffusion policy", "act", "manipulation")),
    ]
    text = "OpenVLA is a 7B VLA model that scales to many robots. The authors build on RT-2 and outperform prior VLAs."
    sid, conf = keyword_classify(text, subs)
    assert sid == "01_vla"
    assert conf > 0.0


def test_keyword_classify_zero_match():
    subs = [SubtopicConfig(id="x", keywords=("foo", "bar"))]
    sid, conf = keyword_classify("An unrelated paper about galaxies.", subs)
    assert sid is None
    assert conf == 0.0


def test_keyword_classify_picks_highest():
    """With weighted Jaccard, a single-keyword topic wins when only that one keyword appears."""
    subs = [
        SubtopicConfig(id="a", keywords=("alpha",)),
        SubtopicConfig(id="b", keywords=("beta", "gamma", "delta")),
    ]
    # Text mentions only 'alpha'; 'b' has zero overlap and must lose.
    text = "We focus exclusively on alpha in this work. alpha alpha alpha alpha alpha alpha alpha."
    sid, conf = keyword_classify(text, subs)
    assert sid == "a"
    assert conf > 0.0
    # And conversely: when text mentions 'beta' only, 'b' wins.
    text2 = "beta beta beta beta beta beta beta beta gamma gamma delta delta"
    sid2, _ = keyword_classify(text2, subs)
    assert sid2 == "b"