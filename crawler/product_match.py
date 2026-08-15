from __future__ import annotations

import re
from dataclasses import dataclass

STOPWORDS = {
    "a", "an", "and", "the", "for", "with", "in", "on", "of", "to",
    "buy", "price", "sale", "online", "official", "shop", "store", "saudi",
    "arabia", "ksa", "sar", "new", "original",
}

CRITICAL_VARIANTS = {
    "pro", "max", "plus", "ultra", "mini", "lite", "air", "se",
    "men", "mens", "women", "womens", "kids", "kid", "junior",
}

WIDE_MARKERS = {"wide", "2e", "4e", "extra-wide", "extrawide"}


def _norm(text: str | None) -> str:
    s = (text or "").lower()
    s = s.replace("’", "'").replace("–", "-").replace("—", "-")
    s = re.sub(r"[^a-z0-9.+-]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def tokens(text: str | None) -> list[str]:
    return re.findall(r"[a-z]+(?:-[a-z]+)?|\d+(?:\.\d+)?", _norm(text))


def _numbers(ts: list[str]) -> set[str]:
    return {t for t in ts if re.fullmatch(r"\d+(?:\.\d+)?", t)}


def _wide_present(ts: set[str]) -> bool:
    if ts & WIDE_MARKERS:
        return True
    # Common footwear width notation sometimes appears as separate tokens.
    return "2" in ts and "e" in ts or "4" in ts and "e" in ts


@dataclass(frozen=True)
class MatchResult:
    accepted: bool
    score: float
    reason: str


def evaluate_match(query: str, title: str | None) -> MatchResult:
    """Conservative product-title match for price comparison.

    The goal is false-positive resistance: a wrong model/variant is more damaging to
    price intelligence than temporarily having no quote.
    """
    q = tokens(query)
    t = tokens(title)
    if not q or not t:
        return MatchResult(False, 0.0, "missing title/query")

    qs, ts = set(q), set(t)
    qnums, tnums = _numbers(q), _numbers(t)

    # Model/generation numbers in the requested product are mandatory.
    missing_nums = qnums - tnums
    if missing_nums:
        return MatchResult(False, 0.0, f"missing model number: {', '.join(sorted(missing_nums))}")

    # Width is a purchase-critical footwear variant. Do not silently compare standard fit.
    if "wide" in qs or "2e" in qs or "4e" in qs or "extra-wide" in qs or "extrawide" in qs:
        if not _wide_present(ts):
            return MatchResult(False, 0.0, "missing requested wide-fit variant")

    # Explicit edition/gender/size-family variant words are mandatory when requested.
    requested_variants = (qs & CRITICAL_VARIANTS)
    # Normalize common apostrophe/plural gender spellings.
    equivalence = {
        "men": {"men", "mens"}, "mens": {"men", "mens"},
        "women": {"women", "womens"}, "womens": {"women", "womens"},
        "kid": {"kid", "kids", "junior"}, "kids": {"kid", "kids", "junior"},
        "junior": {"kid", "kids", "junior"},
    }
    for v in requested_variants:
        allowed = equivalence.get(v, {v})
        if not (ts & allowed):
            return MatchResult(False, 0.0, f"missing requested variant: {v}")

    qcore = [x for x in q if x not in STOPWORDS and x not in qnums and x not in WIDE_MARKERS]
    if not qcore:
        qcore = [x for x in q if x not in STOPWORDS]
    core_set = set(qcore)
    overlap = core_set & ts
    ratio = len(overlap) / max(1, len(core_set))

    # Short specific queries should match all meaningful words. Longer product names
    # can tolerate one descriptive token missing from a marketplace title.
    if len(core_set) <= 2:
        accepted = ratio >= 1.0
    elif len(core_set) <= 4:
        accepted = ratio >= 0.67
    else:
        accepted = ratio >= 0.60

    if not accepted:
        return MatchResult(False, round(ratio * 100, 1), "insufficient title overlap")

    # Prefer exact lexical coverage and direct model-number agreement.
    score = ratio * 80.0
    if qnums:
        score += 12.0
    if requested_variants or (qs & WIDE_MARKERS):
        score += 8.0
    score = min(100.0, score)
    return MatchResult(True, round(score, 1), "matched")
