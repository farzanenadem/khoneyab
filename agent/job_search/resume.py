"""Resume-based job search (RFP B-01/B-02/B-05).

PDF/DOCX -> plain text -> structured profile (skills, experience, education, roles,
location) -> search query + live-crawl keywords -> ranked ads with matched and
missing skills.

The profile comes from the LLM when one is configured, and from rules otherwise.
Every extracted item is validated against the resume text: anything the resume
does not literally contain is discarded, so the profile cannot invent skills.
The resume is processed in memory only and never stored or logged (NF-03).
"""

import io
import json
import re
import zipfile
from typing import Optional

from pydantic import BaseModel, Field, ValidationError

from agent.job_search.matching import canon, contains_phrase
from agent.job_search.query_parser import EXPERIENCE_RE
from agent.utilities.persian_text import html_to_text, normalize_for_search

MAX_RESUME_BYTES = 5 * 1024 * 1024
MAX_TEXT_CHARS = 12000
SUPPORTED = (".pdf", ".docx", ".txt")


class ResumeError(ValueError):
    pass


class ResumeProfile(BaseModel):
    """Documented JSON schema of the extracted profile (RFP B-02)."""

    skills: list[str] = Field(default_factory=list, description="Technical/professional skills and tools")
    experience_years: Optional[int] = Field(default=None, ge=0, le=60, description="Total years of experience")
    education: list[str] = Field(default_factory=list, description="Degrees and fields of study")
    roles: list[str] = Field(default_factory=list, description="Previous job titles / target roles")
    location: Optional[str] = Field(default=None, description="City or province of residence")
    source: str = Field(default="rules", description="'llm' or 'rules'")


# ---------- text extraction ----------

def extract_text(filename: str, data: bytes) -> str:
    if len(data) > MAX_RESUME_BYTES:
        raise ResumeError("حجم فایل بیشتر از ۵ مگابایت است.")
    name = (filename or "").lower()
    if name.endswith(".pdf"):
        text = _pdf_text(data)
    elif name.endswith(".docx"):
        text = _docx_text(data)
    elif name.endswith(".txt"):
        text = data.decode("utf-8", errors="ignore")
    else:
        raise ResumeError("فقط فایل PDF، DOCX یا TXT پشتیبانی می‌شود.")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text).strip()
    if len(text) < 30:
        raise ResumeError("متنی از فایل استخراج نشد (ممکن است PDF اسکن‌شده و تصویری باشد).")
    return text[:MAX_TEXT_CHARS]


def _pdf_text(data: bytes) -> str:
    try:
        import pymupdf
    except ImportError:  # older PyMuPDF
        import fitz as pymupdf
    try:
        with pymupdf.open(stream=data, filetype="pdf") as doc:
            return "\n".join(page.get_text("text", sort=True) for page in doc)
    except Exception as e:
        raise ResumeError(f"فایل PDF خوانده نشد: {e}") from e


def _docx_text(data: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            xml = z.read("word/document.xml").decode("utf-8")
    except (zipfile.BadZipFile, KeyError) as e:
        raise ResumeError("فایل DOCX معتبر نیست.") from e
    xml = re.sub(r"</w:p>", "\n", xml)
    xml = re.sub(r"<w:tab/>", " ", xml)
    return html_to_text(re.sub(r"<[^>]+>", "", xml).replace("\n", "<br>"))


# ---------- profile extraction ----------

LLM_PROMPT = """You extract a structured profile from a resume (Persian or English).
Return ONLY a JSON object with these keys:
{{"skills": [..], "experience_years": int|null, "education": [..], "roles": [..], "location": str|null}}
Rules:
- Copy skills, tools, roles, degrees and city names exactly as written in the resume; do not translate or invent.
- skills: technical and professional skills/tools (max 20), most important first.
- roles: job titles the person held or is targeting (max 5).
- experience_years: total years of work experience if stated or computable, else null.
- location: city/province where the person lives or wants to work, if written, else null.

Resume:
{text}"""


def _grounded(items, text_canon: str, limit: int) -> list[str]:
    out, seen = [], set()
    for item in items or []:
        item = str(item).strip()
        key = canon(item)
        if not key or key in seen or len(key) < 2:
            continue
        if contains_phrase(text_canon, item):
            seen.add(key)
            out.append(item)
        if len(out) >= limit:
            break
    return out


def validate_profile(raw: dict, text: str, source: str) -> ResumeProfile:
    """Keep only items that literally occur in the resume text."""
    text_canon = canon(text)
    location = raw.get("location")
    if location and not contains_phrase(text_canon, str(location)):
        location = None
    years = raw.get("experience_years")
    try:
        years = int(years) if years is not None else None
    except (TypeError, ValueError):
        years = None
    try:
        return ResumeProfile(
            skills=_grounded(raw.get("skills"), text_canon, 20),
            experience_years=years if years is None or 0 <= years <= 60 else None,
            education=_grounded(raw.get("education"), text_canon, 5),
            roles=_grounded(raw.get("roles"), text_canon, 5),
            location=location,
            source=source,
        )
    except ValidationError:
        return ResumeProfile(source=source)


def rule_profile(text: str, service) -> ResumeProfile:
    """Deterministic profile: known skills/locations from the index vocabulary and synonyms."""
    text_canon = canon(text)
    vocab = set()
    for job in service.index.jobs:
        vocab.update(s["name"] for s in job.get("software") or [])
        vocab.update(job.get("skills") or [])
    for group in service.synonym_groups:
        vocab.update(group)
    found: dict[str, str] = {}  # canonical form -> first spelling seen (Python / python)
    for v in sorted(vocab):
        key = canon(v)
        if len(key) > 1 and key not in found and contains_phrase(text_canon, v):
            found[key] = v
    # Drop skills that are part of a longer matched skill (e.g. "excel" inside "microsoft excel").
    skills = [
        v for k, v in sorted(found.items(), key=lambda kv: -len(kv[0]))
        if not any(k != o and contains_phrase(o, k) for o in found)
    ][:20]
    years = [int(m.group(1)) for m in EXPERIENCE_RE.finditer(normalize_for_search(text))]
    locations = [loc for loc in service.parser.locations.values() if contains_phrase(text_canon, loc)]
    return ResumeProfile(
        skills=skills,
        experience_years=max(years) if years else None,
        location=locations[0] if locations else None,
        source="rules",
    )


def llm_profile(text: str, llm) -> Optional[dict]:
    try:
        reply = llm.invoke(LLM_PROMPT.format(text=text))
        content = getattr(reply, "content", reply)
        m = re.search(r"\{.*\}", content, re.S)
        return json.loads(m.group(0)) if m else None
    except Exception:  # timeouts, malformed JSON: fall back to rules (NF-06)
        return None


def extract_profile(text: str, service, llm=None) -> ResumeProfile:
    if llm is not None:
        raw = llm_profile(text, llm)
        if raw:
            profile = validate_profile(raw, text, "llm")
            if profile.skills or profile.roles:
                return profile
    return rule_profile(text, service)


# ---------- search ----------

def profile_query(profile: ResumeProfile) -> str:
    parts = profile.roles[:3] + profile.skills[:12]
    if profile.experience_years is not None:
        parts.append(f"{profile.experience_years} سال سابقه")
    if profile.location:
        parts.append(f"ترجیحاً {profile.location}")
    return " ، ".join(parts)


def job_requirements(job: dict) -> list[str]:
    return list(dict.fromkeys((job.get("skills") or []) + [s["name"] for s in job.get("software") or []]))


def search_with_resume(service, text: str, llm=None, filters=None, top_k: int = 10, live: bool = True) -> dict:
    profile = extract_profile(text, service, llm)
    query = profile_query(profile)
    if not query.strip():
        raise ResumeError("مهارت یا عنوان شغلی قابل‌تشخیصی در رزومه پیدا نشد.")
    keywords = (profile.roles[:2] + profile.skills[:3])[:4]
    result = service.search(query, filters, top_k=top_k, live=live, keywords=keywords or None)
    text_canon = canon(text)
    for r in result["results"]:
        reqs = job_requirements(r["job"])
        r["resume_match"] = {
            "matched_skills": [s for s in reqs if contains_phrase(text_canon, s)],
            "missing_skills": [s for s in reqs if not contains_phrase(text_canon, s)],
        }
    result["profile"] = profile.model_dump()
    result["generated_query"] = query
    return result
