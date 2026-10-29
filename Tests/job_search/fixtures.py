"""Synthetic records shaped exactly like the JobVision listing export (rfp/jobs.jsonl)."""

import hashlib
import json

import numpy as np

from agent.utilities.persian_text import tokenize


def item(fa, en="", id_=0):
    return {"id": id_, "title": None, "titleFa": fa, "titleEn": en}


def make_raw(
    id_,
    title,
    company="شرکت نمونه",
    province="تهران",
    city="تهران",
    categories=("توسعه نرم افزار و برنامه نویسی",),
    industry="فناوری اطلاعات / نرم افزار و سخت افزار",
    work_type="تمام وقت",
    seniority="کارشناس",
    salary=None,
    remote=False,
    internship=False,
    experience=2,
    benefits=("بیمه",),
    labels=(),
):
    return {
        "score": 1,
        "itemIndex": 1,
        "id": id_,
        "title": title,
        "isPersian": True,
        "properties": {
            "isInternship": internship,
            "isRemote": remote,
            "isUrgent": False,
            "requiredRelatedExperienceYears": experience,
            "salaryCanBeShown": salary is not None,
            "isBlueCollarJob": False,
        },
        "company": {"id": 1, "nameFa": company, "nameEn": "", "pageUrl": "/companies/1/x", "logoUrl": ""},
        "location": {
            "country": item("ایران", "Iran"),
            "province": item(province, province),
            "city": item(city, city),
            "region": None,
        },
        "jobCategories": [item(c) for c in categories],
        "benefits": [item(b) for b in benefits],
        "workType": item(work_type),
        "seniorityLevel": item(seniority),
        "salary": (
            {"id": 0, "titleFa": f"{salary[0]} - {salary[1]} میلیون تومان", "min": salary[0], "max": salary[1]}
            if salary
            else None
        ),
        "industry": item(industry),
        "gender": item("تفاوتی ندارد"),
        "labels": list(labels),
        "activationTime": {"date": "2026-10-20T10:00:00Z"},
        "expireTime": {"date": "2026-12-20T10:00:00Z"},
    }


RAW_JOBS = [
    make_raw(101, "کارشناس هوش مصنوعی", categories=("علوم داده / هوش مصنوعی",), salary=(40, 60)),
    make_raw(102, "برنامه نویس پایتون (Django)", province="اصفهان", city="اصفهان", remote=True),
    make_raw(103, "حسابدار ارشد", categories=("مالی و حسابداری",), industry="مالی", seniority="کارشناس ارشد", experience=5),
    make_raw(104, "کارشناس فروش - خانم", province="البرز", city="کرج", categories=("فروش و بازاریابی - سطوح کارشناسی و مدیریتی",), industry="بازرگانی"),
    make_raw(105, "Data Scientist", categories=("علوم داده / هوش مصنوعی",), work_type="پاره وقت", experience=3),
    make_raw(106, "کارآموز حسابداری", categories=("مالی و حسابداری",), industry="مالی", seniority="کارآموز", internship=True, experience=0),
]

DETAILS = {
    105: {
        "id": 105,
        "url": "https://jobvision.ir/jobs/105/استخدام-data-scientist",
        "description": "وظایف:\n• توسعه مدل‌های زبانی بزرگ (LLM) و سیستم‌های RAG\n• پیاده‌سازی با Python و PyTorch",
        "skills": [],
        "software": [{"name": "Python", "level": "پیشرفته"}],
        "languages": [],
        "academic": [],
        "work_days": "شنبه تا چهارشنبه",
        "is_remote": True,
    }
}


def write_jsonl(path, rows):
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


class FakeEmbeddings:
    """Deterministic hashed bag-of-words embeddings (LangChain Embeddings interface)."""

    dim = 64

    def _vec(self, text):
        v = np.zeros(self.dim, dtype=np.float32)
        for tok in tokenize(text.replace("query:", " ").replace("passage:", " ")):
            v[int(hashlib.md5(tok.encode()).hexdigest(), 16) % self.dim] += 1.0
        return v.tolist()

    def embed_documents(self, texts):
        return [self._vec(t) for t in texts]

    def embed_query(self, text):
        return self._vec(text)
