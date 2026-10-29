"""Learning roadmap for a specific job ad.

The skills to learn come only from the ad (its skills/software lists); skills the
user already has (from their resume) are excluded. The LLM, when configured, only
writes the learning steps for those skills; anything outside the ad's requirements
is discarded, so the roadmap cannot invent requirements. Without an LLM a
deterministic roadmap is produced from the same data.
"""

import json
import re
from typing import Optional

from agent.job_search.matching import canon, contains_phrase
from agent.job_search.resume import job_requirements

MAX_SKILLS = 8
DESC_CHARS = 2500

LLM_PROMPT = """You are a career coach. Build a learning roadmap so a candidate can qualify for this job ad.
Write all text in Persian. Return ONLY a JSON object:
{{"summary": str, "stages": [{{"skill": str, "why": str, "steps": [str, ..], "weeks": int}}]}}
Rules:
- "skill" must be copied exactly from the list "Skills to learn"; do not add other skills.
- Order stages from foundational to advanced; for each give 2-4 concrete steps (topics, a small project, practice).
- "why" must refer to what the ad says (quote or paraphrase the ad text); do not invent requirements, salary or company facts.
- "weeks" is a rough estimate (1-12) for a beginner.
- "summary": 1-2 sentences on how far the candidate is from this job.

Job title: {title}
Required experience (years): {experience}
Ad description:
{description}

Skills the candidate already has: {known}
Skills to learn: {todo}"""


def _fallback_stage(skill: str, title: str) -> dict:
    return {
        "skill": skill,
        "why": f"«{skill}» در آگهی «{title}» به‌عنوان مهارت موردنیاز ذکر شده است.",
        "steps": [
            f"یادگیری مفاهیم پایه «{skill}» با یک دوره یا مستندات رسمی",
            f"انجام یک پروژه کوچک عملی با «{skill}»",
            f"افزودن این پروژه و مهارت «{skill}» به رزومه",
        ],
        "weeks": None,
    }


def _llm_roadmap(job: dict, known: list[str], todo: list[str], llm) -> Optional[dict]:
    prompt = LLM_PROMPT.format(
        title=job.get("title", ""),
        experience=job.get("required_experience_years"),
        description=(job.get("description") or "")[:DESC_CHARS] or "(no description)",
        known="، ".join(known) or "(none given)",
        todo="، ".join(todo),
    )
    try:
        content = getattr(llm.invoke(prompt), "content", None) or ""
        m = re.search(r"\{.*\}", content, re.S)
        return json.loads(m.group(0)) if m else None
    except Exception:  # timeouts, malformed JSON: use the deterministic roadmap
        return None


def _clean_stages(raw: dict, todo: list[str], title: str) -> list[dict]:
    """Keep only stages for skills that are in the ad's missing list, in LLM order."""
    allowed = {canon(s): s for s in todo}
    stages, done = [], set()
    for st in raw.get("stages") or []:
        if not isinstance(st, dict):
            continue
        key = canon(str(st.get("skill", "")))
        steps = [str(x).strip() for x in st.get("steps") or [] if str(x).strip()][:5]
        if key not in allowed or key in done or not steps:
            continue
        done.add(key)
        weeks = st.get("weeks")
        stages.append(
            {
                "skill": allowed[key],
                "why": str(st.get("why") or "").strip() or _fallback_stage(allowed[key], title)["why"],
                "steps": steps,
                "weeks": weeks if isinstance(weeks, int) and 1 <= weeks <= 52 else None,
            }
        )
    # Skills the LLM skipped still appear, so the roadmap covers every gap.
    stages += [_fallback_stage(s, title) for k, s in allowed.items() if k not in done]
    return stages


def build_roadmap(job: dict, known_skills: Optional[list[str]] = None, llm=None) -> dict:
    known = [s.strip() for s in known_skills or [] if s and s.strip()]
    known_text = canon(" ، ".join(known))
    reqs = job_requirements(job)
    have = [s for s in reqs if contains_phrase(known_text, s)]
    todo = [s for s in reqs if s not in have][:MAX_SKILLS]
    title = job.get("title", "")

    raw = _llm_roadmap(job, known, todo, llm) if llm is not None and todo else None
    if raw:
        stages, source = _clean_stages(raw, todo, title), "llm"
        summary = str(raw.get("summary") or "").strip()
    else:
        stages, source = [_fallback_stage(s, title) for s in todo], "rules"
        summary = ""
    if not summary:
        summary = (
            f"برای آگهی «{title}» {len(todo)} مهارت از مهارت‌های ذکرشده در آگهی را باید تقویت کنید."
            if todo
            else "مهارت‌های ذکرشده در آگهی با مهارت‌های شما پوشش داده شده‌اند."
        )
    return {
        "job_id": job.get("id"),
        "title": title,
        "summary": summary,
        "have_skills": have,
        "stages": stages,
        "requirements_listed": bool(reqs),
        "source": source,
    }
