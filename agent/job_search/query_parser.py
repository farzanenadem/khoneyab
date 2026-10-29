"""Deterministic understanding of a free-text Persian job description.

Extracts soft preferences (location, remote, work type, seniority, experience,
salary floor) and the skill/role concepts to look for in job ads. Everything is
rule-based so it is fast, testable and never invents values.
"""

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, Optional

import yaml
from yaml.loader import SafeLoader

from agent.job_search.matching import canon, find_phrase
from agent.utilities.persian_text import PERSIAN_STOPWORDS, tokenize

REMOTE_PHRASES = [
    "دورکاری", "دور کاری", "دورکار", "دور کار", "ریموت", "remote", "از راه دور",
    "از خانه", "از منزل", "work from home", "wfh", "کار در منزل",
]
INTERNSHIP_PHRASES = ["کارآموزی", "کارآموز", "کار آموزی", "intern", "internship"]
WORK_TYPE_PHRASES = {
    "پاره وقت": ["پاره وقت", "پاره‌وقت", "part time", "part-time", "نیمه وقت"],
    "تمام وقت": ["تمام وقت", "تمام‌وقت", "full time", "full-time"],
    "قراردادی / پروژه ای": ["پروژه ای", "پروژه‌ای", "قراردادی", "فریلنس", "freelance", "پروژه‌ای"],
}
# Values are seniority titles as they appear in the dataset.
SENIORITY_PHRASES = {
    "junior": (
        ["جونیور", "جونیر", "junior", "تازه کار", "تازه‌کار", "مبتدی", "بدون سابقه", "فارغ التحصیل"],
        ["کارمند", "کارشناس", "کارآموز"],
    ),
    "senior": (
        ["سنیور", "senior", "کارشناس ارشد", "حرفه ای", "حرفه‌ای", "ارشد"],
        ["کارشناس ارشد"],
    ),
    "manager": (
        ["مدیر", "manager", "سرپرست", "لید", "lead", "team lead", "head of"],
        ["مدیر میانی", "معاون / مدیر ارشد", "مدیرعامل"],
    ),
    "intern": (INTERNSHIP_PHRASES, ["کارآموز"]),
}
NO_EXPERIENCE_PHRASES = ["بدون سابقه", "بدون تجربه", "تازه کار", "تازه‌کار", "فارغ التحصیل"]
EXPERIENCE_RE = re.compile(r"(\d{1,2})\s*(?:\+\s*)?(?:سال|years?|yrs?)")
SALARY_RE = re.compile(r"(?:حقوق|درآمد|دستمزد|salary)[^0-9]{0,25}(\d{1,3})\s*(?:میلیون|m\b|million)")
LOCATION_STRICT_PHRASES = ["فقط در", "حتما در", "حتماً در", "only in"]
NOISE_WORDS = {
    "سابقه", "تجربه", "سال", "شهر", "استان", "شرکت", "سطح", "اشنا", "اشنایی", "تسلط",
    "مسلط", "توانایی", "مهارت", "مهارتها", "علاقه", "علاقمند", "علاقه‌مند", "ترجیحا",
    "ترجیحاً", "میتوانم", "میتونم", "کارهای", "کنم", "دنبال", "هستم", "بزرگ", "years",
    "year", "experience", "job", "position", "looking", "حقوق", "میلیون", "تومان",
}


@dataclass
class Concept:
    label: str
    variants: list[str]
    from_synonyms: bool = False


@dataclass
class ParsedQuery:
    text: str
    locations: list[str] = field(default_factory=list)
    location_strict: bool = False
    wants_remote: bool = False
    wants_internship: bool = False
    work_types: list[str] = field(default_factory=list)
    seniority: list[str] = field(default_factory=list)
    experience_years: Optional[int] = None
    min_salary: Optional[int] = None
    concepts: list[Concept] = field(default_factory=list)

    @property
    def expansion_text(self) -> str:
        return " ".join(v for c in self.concepts for v in c.variants)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["concepts"] = [{"label": c.label, "variants": c.variants} for c in self.concepts]
        return d


def load_synonym_groups(path: Optional[Path]) -> list[list[str]]:
    if path is None or not Path(path).exists():
        return []
    with open(path, encoding="utf-8") as f:
        data = yaml.load(f, Loader=SafeLoader) or {}
    return [[str(v) for v in g] for g in data.get("groups", []) if g]


class QueryParser:
    def __init__(self, locations: Iterable[str] = (), synonym_groups: Iterable[list[str]] = ()):
        # canonical form -> display form
        self.locations = {canon(loc): loc for loc in locations if loc and len(canon(loc)) > 1}
        self.synonym_groups = [list(g) for g in synonym_groups]

    @staticmethod
    def _consume(text: str, phrases: Iterable[str]) -> tuple[str, bool]:
        """Remove every occurrence of the given phrases from canonical text."""
        hit = False
        for phrase in sorted(phrases, key=lambda p: -len(canon(p))):
            while (m := find_phrase(text, phrase)) is not None:
                hit = True
                text = (text[: m.start()] + " " + text[m.end():]).strip()
        return text, hit

    def parse(self, query: str) -> ParsedQuery:
        text = canon(query)
        pq = ParsedQuery(text=query.strip())

        # Numbers first so that "3 سال" is not left as noise.
        if (m := SALARY_RE.search(text)) is not None:
            pq.min_salary = int(m.group(1))
            text = text[: m.start()] + " " + text[m.end():]
        if (m := EXPERIENCE_RE.search(text)) is not None:
            pq.experience_years = int(m.group(1))
            text = text[: m.start()] + " " + text[m.end():]

        text, pq.wants_remote = self._consume(text, REMOTE_PHRASES)

        for work_type, phrases in WORK_TYPE_PHRASES.items():
            text, hit = self._consume(text, phrases)
            if hit:
                pq.work_types.append(work_type)

        _, no_exp = self._consume(text, NO_EXPERIENCE_PHRASES)
        if no_exp and pq.experience_years is None:
            pq.experience_years = 0

        # Synonym groups run before seniority/location so that «مدیر محصول» or
        # «ری اکت» (ری is also a city) stay whole. Longest variants win.
        variants = sorted(
            ((v, gi) for gi, g in enumerate(self.synonym_groups) for v in g),
            key=lambda x: -len(canon(x[0])),
        )
        matched_groups: dict[int, str] = {}
        for variant, gi in variants:
            text, hit = self._consume(text, [variant])
            if hit and gi not in matched_groups:
                matched_groups[gi] = variant
        for gi, surface in matched_groups.items():
            pq.concepts.append(
                Concept(label=surface, variants=self.synonym_groups[gi], from_synonyms=True)
            )

        for key in ("intern", "senior", "manager", "junior"):
            phrases, levels = SENIORITY_PHRASES[key]
            text, hit = self._consume(text, phrases)
            if hit:
                if key == "intern":
                    pq.wants_internship = True
                for level in levels:
                    if level not in pq.seniority:
                        pq.seniority.append(level)

        text, pq.location_strict = self._consume(text, LOCATION_STRICT_PHRASES)
        for loc_canon in sorted(self.locations, key=len, reverse=True):
            text, hit = self._consume(text, [loc_canon])
            if hit and self.locations[loc_canon] not in pq.locations:
                pq.locations.append(self.locations[loc_canon])

        # Remaining content words become single-term concepts.
        seen = {canon(v) for c in pq.concepts for v in c.variants}
        for token in tokenize(text):
            if token in NOISE_WORDS or token in PERSIAN_STOPWORDS or token.isdigit():
                continue
            if token in seen:
                continue
            seen.add(token)
            pq.concepts.append(Concept(label=token, variants=[token]))

        return pq
