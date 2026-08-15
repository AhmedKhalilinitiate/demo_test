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

WIDE_MARKERS = {"wide", "2e", "4e", "extrawide"}


def _norm(text: str | None) -> str:
    s = (text or "").lower()
    s = s.replace("’", "").replace("'", "").replace("–", "-").replace("—", "-")
    s = re.sub(r"[-_/]+", " ", s)
    s = re.sub(r"[^a-z0-9.+]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def tokens(text: str | None) -> list[str]:
    return re.findall(r"[a-z0-9]+(?:\.[0-9]+)?", _norm(text))


def _numbers(ts: list[str]) -> set[str]:
    return {t for t in ts if re.fullmatch(r"\d+(?:\.\d+)?", t)}


def _model_codes(ts: list[str]) -> set[str]:
    return {
        t for t in ts
        if len(t) >= 3 and any(c.isdigit() for c in t) and any(c.isalpha() for c in t)
        and t not in {"2e", "4e"}
    }


def _wide_present(ts: set[str]) -> bool:
    return bool(ts & WIDE_MARKERS) or ("extra" in ts and "wide" in ts)


@dataclass(frozen=True)
class MatchResult:
    accepted: bool
    score: float
    reason: str


def evaluate_match(query: str, title: str | None) -> MatchResult:
    """Conservative product-title match for price comparison.

    False positives are intentionally more expensive than false negatives: a wrong
    generation/edition/fit can create a fake deal and poison price history.
    """
    q = tokens(query)
    t = tokens(title)
    if not q or not t:
        return MatchResult(False, 0.0, "missing title/query")

    qs, ts = set(q), set(t)
    qnums, tnums = _numbers(q), _numbers(t)
    qcodes = _model_codes(q)

    missing_nums = qnums - tnums
    if missing_nums:
        return MatchResult(False, 0.0, f"missing model number: {', '.join(sorted(missing_nums))}")

    missing_codes = qcodes - ts
    if missing_codes:
        return MatchResult(False, 0.0, f"missing model code: {', '.join(sorted(missing_codes))}")

    wants_wide = "wide" in qs or "2e" in qs or "4e" in qs or "extrawide" in qs
    if wants_wide and not _wide_present(ts):
        return MatchResult(False, 0.0, "missing requested wide-fit variant")

    requested_variants = qs & CRITICAL_VARIANTS
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

    qcore = [
        x for x in q
        if x not in STOPWORDS and x not in qnums and x not in qcodes
        and x not in WIDE_MARKERS and x != "extra"
    ]
    if not qcore:
        qcore = [x for x in q if x not in STOPWORDS]
    core_set = set(qcore)
    overlap = core_set & ts
    ratio = len(overlap) / max(1, len(core_set))

    if len(core_set) <= 2:
        accepted = ratio >= 1.0
    elif len(core_set) <= 4:
        accepted = ratio >= 0.67
    else:
        accepted = ratio >= 0.60

    if not accepted:
        return MatchResult(False, round(ratio * 100, 1), "insufficient title overlap")

    score = ratio * 76.0
    if qnums:
        score += 10.0
    if qcodes:
        score += 8.0
    if requested_variants or wants_wide:
        score += 6.0
    return MatchResult(True, round(min(100.0, score), 1), "matched")
