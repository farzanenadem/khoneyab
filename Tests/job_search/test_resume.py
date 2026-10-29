import io
import zipfile

import pytest
from fastapi.testclient import TestClient

from agent.job_search.resume import (
    ResumeError,
    extract_profile,
    extract_text,
    profile_query,
    search_with_resume,
    validate_profile,
)
from ui.src import api

RESUME = """فرزانه نمونه
تهران
کارشناس هوش مصنوعی با ۳ سال سابقه
مهارت‌ها: Python، یادگیری ماشین، مدل‌های زبانی بزرگ (LLM)، RAG، SQL
تحصیلات: کارشناسی ارشد مهندسی کامپیوتر
"""


def make_docx(text: str) -> bytes:
    paras = "".join(f"<w:p><w:r><w:t>{line}</w:t></w:r></w:p>" for line in text.splitlines())
    xml = f'<?xml version="1.0"?><w:document xmlns:w="w"><w:body>{paras}</w:body></w:document>'
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", xml)
    return buf.getvalue()


def make_pdf(text: str) -> bytes:
    pymupdf = pytest.importorskip("pymupdf")
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 72), text, fontsize=11)  # Latin text: built-in font has no Persian glyphs
    return doc.tobytes()


class FakeLLM:
    def __init__(self, content):
        self.content = content

    def invoke(self, prompt):
        assert "Resume:" in prompt
        return type("Msg", (), {"content": self.content})()


def test_extract_text_from_docx_txt_and_pdf():
    assert "Python" in extract_text("cv.docx", make_docx(RESUME))
    assert "هوش مصنوعی" in extract_text("cv.txt", RESUME.encode("utf-8"))
    pdf_text = extract_text("cv.pdf", make_pdf("Data Scientist, 4 years experience, Python, SQL, Machine Learning"))
    assert "Python" in pdf_text


def test_extract_text_rejects_bad_input():
    with pytest.raises(ResumeError):
        extract_text("cv.png", b"x" * 100)
    with pytest.raises(ResumeError):
        extract_text("cv.docx", b"not a zip file at all, definitely")
    with pytest.raises(ResumeError):
        extract_text("cv.txt", b"short")
    with pytest.raises(ResumeError):
        extract_text("cv.txt", b"a" * (6 * 1024 * 1024))


def test_llm_profile_is_validated_against_resume_text():
    raw = {
        "skills": ["Python", "RAG", "Kubernetes", "SQL"],   # Kubernetes is not in the resume
        "experience_years": 3,
        "education": ["کارشناسی ارشد مهندسی کامپیوتر", "PhD Harvard"],
        "roles": ["کارشناس هوش مصنوعی", "CTO"],
        "location": "اصفهان",                                 # not in the resume
    }
    p = validate_profile(raw, RESUME, "llm")
    assert p.skills == ["Python", "RAG", "SQL"]
    assert p.education == ["کارشناسی ارشد مهندسی کامپیوتر"]
    assert p.roles == ["کارشناس هوش مصنوعی"]
    assert p.location is None and p.experience_years == 3


def test_extract_profile_uses_llm_then_falls_back_to_rules(service):
    llm = FakeLLM('```json\n{"skills": ["Python", "LLM"], "roles": ["کارشناس هوش مصنوعی"], "experience_years": 3, "location": "تهران"}\n```')
    p = extract_profile(RESUME, service, llm)
    assert p.source == "llm" and p.location == "تهران" and "Python" in p.skills

    broken = extract_profile(RESUME, service, FakeLLM("not json"))
    assert broken.source == "rules"
    assert broken.experience_years == 3 and broken.location == "تهران"
    assert any(s.lower() == "python" for s in broken.skills)


def test_search_with_resume_returns_profile_and_skill_gaps(service):
    res = search_with_resume(service, RESUME, llm=None, top_k=3, live=False)
    assert res["profile"]["location"] == "تهران"
    assert "تهران" in res["generated_query"]
    top_ids = [r["job"]["id"] for r in res["results"]]
    assert "105" in top_ids or "101" in top_ids
    ds = next((r for r in res["results"] if r["job"]["id"] == "105"), None)
    if ds:
        assert ds["resume_match"]["matched_skills"] == ["Python"]


def test_profile_query_without_skills_raises(service):
    with pytest.raises(ResumeError):
        search_with_resume(service, "متن بدون هیچ مهارت شناخته‌شده‌ای برای آزمایش سیستم " * 2, live=False)
    assert profile_query(validate_profile({"skills": ["Python"]}, "Python dev", "llm")) == "Python"


def test_resume_endpoint(service, monkeypatch):
    monkeypatch.setattr(api, "load_api_config", lambda: {"chat_enabled": False, "resume_llm_enabled": False})
    monkeypatch.setattr(api, "job_search", service)
    monkeypatch.setattr(api, "resume_llm", None)
    with TestClient(api.app) as c:
        r = c.post("/resume/search", files={"file": ("cv.docx", make_docx(RESUME))}, data={"top_k": "3", "live": "false"})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["profile"]["source"] == "rules" and data["results"]
        assert "resume_match" in data["results"][0]
        bad = c.post("/resume/search", files={"file": ("cv.exe", b"x" * 50)})
        assert bad.status_code == 400
