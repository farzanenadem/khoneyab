"""Phrase matching on normalized Persian/English text."""

import re
from functools import lru_cache

from agent.utilities.persian_text import normalize_for_search

PLURAL_TOKENS_RE = re.compile(r"(?<!\S)(?:ها|های|هایی)(?!\S)")
PERSIAN_SUFFIXES = "(?:ی|ها|های|هایی|ان|تر)?"


def canon(text: str) -> str:
    """Search normalization plus removal of detached plural suffixes (مدل‌های -> مدل)."""
    text = normalize_for_search(text)
    text = PLURAL_TOKENS_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


@lru_cache(maxsize=4096)
def phrase_regex(phrase: str) -> re.Pattern:
    phrase = canon(phrase)
    body = r"\s+".join(re.escape(p) for p in phrase.split(" "))
    if re.search(r"[؀-ۿ]$", phrase):
        tail = PERSIAN_SUFFIXES + r"(?![؀-ۿ])"
    else:
        tail = r"(?![a-z0-9#+])"
    return re.compile(r"(?<![a-z0-9#+؀-ۿ])" + body + tail)


def contains_phrase(canon_text: str, phrase: str) -> bool:
    """`canon_text` must already be passed through canon()."""
    if not phrase.strip():
        return False
    return phrase_regex(phrase).search(canon_text) is not None


def find_phrase(canon_text: str, phrase: str):
    return phrase_regex(phrase).search(canon_text)
