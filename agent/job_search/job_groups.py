"""Job groups: background knowledge learned from the JobVision Jobposts Dataset.

The Hugging Face dataset (anonymized JobVision ads, 2022-2024, CC BY-NC 4.0) is used
ONLY to understand what the user is looking for:

* two-level clustering: level 1 = the dataset's main job categories, level 2 =
  KMeans inside each category (k chosen by silhouette);
* a profile per group: typical titles, key software skills, experience levels;
* placing a free-text request into its closest groups (vectors in Qdrant).

Dataset rows are never search results: recommendations always come from the
current ads in the job index. Gender, age, military-service and disability
columns are never read.
"""

import json
import random
import re
import uuid
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable, Optional

import numpy as np

from agent.job_search.index import Embedder
from agent.job_search.matching import canon, phrase_regex

DATASET_URL = (
    "https://huggingface.co/datasets/JobVision/JobVision_Jobposts_Dataset/resolve/"
    "refs%2Fconvert%2Fparquet/default/train/0000.parquet"
)
# Dataset column -> record key. Only these columns are read from the file.
DATASET_COLUMNS = {
    "Jobpost_RawTitle": "title",
    "Jobpost_MainJobCategory": "category",
    "Jobpost_SoftwareSkills": "software",
    "Jobpost_AcademicFields": "academic",
    "Jobpost_RequiredExperienceYears": "experience",
    "Jobpost_IsRemote": "remote",
    "Jobpost_ProvinceFa": "province",
    "Jobpost_ActivationTime_YEAR_MONTH": "month",
}
# Documented so nobody adds them: matching must not depend on these.
EXCLUDED_COLUMNS = (
    "Jobpost_PreferredGender",
    "Jobpost_RequiredMinAge",
    "Jobpost_RequiredMaxAge",
    "Jobpost_RequiredMilitaryServiceCard",
    "Jobpost_HasDisabilitySupport",
)
COLLECTION = "job_groups"
# Fixed namespace so a group id always maps to the same Qdrant point id.
POINT_NAMESPACE = uuid.UUID("5a1f0c1e-6b8e-4c43-9c2b-0b4e8d1f2a77")
MAX_TITLE_NGRAM = 5
MAX_SILHOUETTE_REPEATS = 20
SILHOUETTE_SAMPLE = 3000
# A title enters the title index only if this share of its ads falls in one group;
# generic titles («برنامه نویس», «پرستار») spread over many groups and would mislead.
MIN_TITLE_PURITY = 0.6
DEFAULT_PLACE_WEIGHTS = {"semantic": 0.6, "skill": 0.3, "title": 0.1}
# Ads sometimes put a gender preference in the title («حسابدار - خانم»). It is not
# part of the job, so it is removed from group names, keywords and the title index.
GENDER_IN_TITLE_RE = re.compile(r"\s*[-–(\[]*\s*(?:فقط\s*)?(?:آقا|اقا|خانم|بانوان|آقایان)\s*[)\]]*\s*$")


def clean_title(title: str) -> str:
    return GENDER_IN_TITLE_RE.sub("", title).strip(" -–") or title.strip()


# ---------- reading the dataset ----------

def _json_list(raw) -> list[dict]:
    if not raw:
        return []
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, ValueError):
        return []
    return [x for x in data if isinstance(x, dict)] if isinstance(data, list) else []


def parse_software(raw) -> list[dict]:
    """[{"TitleFa": "فتوشاپ,فوتوشاپ", "TitleEn": "Adobe Photoshop", "Level": ...}] -> skills with aliases."""
    skills = []
    for item in _json_list(raw):
        en = (item.get("TitleEn") or "").strip()
        fa = [v.strip() for v in (item.get("TitleFa") or "").split(",") if v.strip()]
        name = en or (fa[0] if fa else "")
        if name:
            skills.append({"name": name, "aliases": list(dict.fromkeys([name, *fa])), "level": (item.get("Level") or "").strip()})
    return skills


def parse_academic(raw) -> list[str]:
    return [f for f in ((x.get("FieldType") or "").strip() for x in _json_list(raw)) if f]


def to_record(row: dict) -> Optional[dict]:
    rec = {key: row.get(col) for col, key in DATASET_COLUMNS.items()}
    title, category = (rec["title"] or "").strip(), (rec["category"] or "").strip()
    if not title or not category:
        return None
    try:
        experience = int(rec["experience"]) if rec["experience"] not in (None, "") else None
    except (TypeError, ValueError):
        experience = None
    return {
        "title": title,
        "category": category,
        "software": parse_software(rec["software"]),
        "academic": parse_academic(rec["academic"]),
        "experience": experience,
        "remote": str(rec["remote"]).lower() == "true",
        "province": (rec["province"] or "").strip(),
        "month": str(rec["month"] or ""),
    }


def read_dataset(path: Path) -> list[dict]:
    """Read only DATASET_COLUMNS from the parquet file."""
    import pyarrow.parquet as pq

    table = pq.read_table(path, columns=list(DATASET_COLUMNS))
    return [r for r in (to_record(row) for row in table.to_pylist()) if r is not None]


def download_dataset(path: Path, url: str = DATASET_URL, timeout: float = 120) -> Path:
    import requests

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".part")
    with requests.get(url, stream=True, timeout=timeout) as r:
        r.raise_for_status()
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
    tmp.replace(path)
    return path


def sample_records(records: Iterable[dict], per_category: int, since_month: str = "", seed: int = 42) -> list[dict]:
    """Up to `per_category` rows per category, newest first (ties shuffled with a fixed seed)."""
    rng = random.Random(seed)
    by_cat: dict[str, list[dict]] = defaultdict(list)
    for rec in records:
        if not since_month or rec["month"] >= since_month:
            by_cat[rec["category"]].append(rec)
    out = []
    for cat in sorted(by_cat):
        rows = by_cat[cat]
        rng.shuffle(rows)
        rows.sort(key=lambda r: r["month"], reverse=True)
        out.extend(rows[:per_category])
    return out


# ---------- clustering ----------

def record_text(rec: dict) -> str:
    """Same layout as index.passage_text, so groups and current ads share one vector space."""
    skills = " ، ".join(s["name"] for s in rec["software"])
    parts = [f"عنوان شغل: {rec['title']}", f"دسته‌بندی: {rec['category']}", f"مهارت‌ها: {skills}" if skills else ""]
    return "\n".join(p for p in parts if p)


def _normalize(m: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(m, axis=-1, keepdims=True)
    norms[norms == 0] = 1.0
    return m / norms


def cluster_category(vectors: np.ndarray, weights: np.ndarray, k_min: int, k_max: int,
                     min_rows: int, min_silhouette: float, seed: int) -> tuple[np.ndarray, np.ndarray, float]:
    """KMeans with k chosen by cosine silhouette. Returns (labels, unit centroids, silhouette)."""
    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_score

    n = len(vectors)
    single = (np.zeros(n, dtype=int), _normalize(np.average(vectors, axis=0, weights=weights)[None, :]), 0.0)
    if weights.sum() < min_rows or n < k_min:
        return single
    # Silhouette over rows (unique texts repeated by their count, capped) so that a
    # title posted 30 times weighs more than a one-off title.
    reps = np.minimum(weights, MAX_SILHOUETTE_REPEATS).astype(int)
    rows = np.repeat(vectors, reps, axis=0)
    best = None
    for k in range(k_min, min(k_max, n) + 1):
        km = KMeans(n_clusters=k, n_init=5, random_state=seed).fit(vectors, sample_weight=weights)
        row_labels = np.repeat(km.labels_, reps)
        if not 2 <= len(set(row_labels)) < len(rows):
            continue
        score = float(silhouette_score(
            rows, row_labels, metric="cosine", sample_size=min(len(rows), SILHOUETTE_SAMPLE), random_state=seed
        ))
        if best is None or score > best[2]:
            best = (km.labels_.astype(int), _normalize(km.cluster_centers_), score)
    return best if best is not None and best[2] >= min_silhouette else single


def _level(years: Optional[int]) -> Optional[str]:
    if years is None:
        return None
    return "junior" if years <= 2 else ("mid" if years <= 5 else "senior")


def group_profile(group_id: str, category: str, rows: list[dict], min_skill_share: float,
                  max_skills: int = 15, sparse_share: float = 0.3) -> dict:
    n = len(rows)
    titles = Counter(clean_title(r["title"]) for r in rows)
    skill_rows: dict[str, list[dict]] = defaultdict(list)
    aliases: dict[str, set] = defaultdict(set)
    for r in rows:
        for s in {s["name"]: s for s in r["software"]}.values():
            skill_rows[s["name"]].append({"level": s["level"], "exp": r["experience"]})
            aliases[s["name"]].update(s["aliases"])
    key_skills = []
    for name, hits in sorted(skill_rows.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        share = len(hits) / n
        if share < min_skill_share or len(key_skills) >= max_skills:
            break
        exps = [h["exp"] for h in hits if h["exp"] is not None]
        key_skills.append({
            "name": name,
            "aliases": sorted(aliases[name]),
            "share": round(share, 3),
            "level": Counter(h["level"] for h in hits if h["level"]).most_common(1)[0][0] if any(h["level"] for h in hits) else "",
            "typical_level": _level(int(np.median(exps))) if exps else None,
        })
    exps = [r["experience"] for r in rows if r["experience"] is not None]
    levels = Counter(_level(e) for e in exps)
    keywords = list(dict.fromkeys(canon(t) for t, _ in titles.most_common(10) if canon(t)))[:4]
    return {
        "id": group_id,
        "category": category,
        "name": titles.most_common(1)[0][0],
        "size": n,
        "titles": [{"title": t, "count": c} for t, c in titles.most_common(5)],
        "key_skills": key_skills,
        "skills_sparse": sum(1 for r in rows if r["software"]) / n < sparse_share,
        "experience": {
            "median_years": float(np.median(exps)) if exps else None,
            **{lvl: round(levels[lvl] / len(exps), 3) if exps else 0.0 for lvl in ("junior", "mid", "senior")},
        },
        "academic": [f for f, _ in Counter(f for r in rows for f in r["academic"]).most_common(5)],
        "remote_share": round(sum(r["remote"] for r in rows) / n, 3),
        "provinces": [p for p, _ in Counter(r["province"] for r in rows if r["province"]).most_common(5)],
        "search_keywords": keywords,
    }


def build_groups(records: list[dict], embedder: Embedder, k_min: int = 2, k_max: int = 6, min_rows: int = 40,
                 min_silhouette: float = 0.05, min_skill_share: float = 0.10, seed: int = 42,
                 batch_size: int = 64, log=print) -> tuple[list[dict], np.ndarray, dict]:
    """Two-level clustering. Returns (group profiles, unit centroids, title -> group id)."""
    # Identical texts are embedded once and weighted by how often they occur.
    texts = [record_text(r) for r in records]
    unique = list(dict.fromkeys(texts))
    pos = {t: i for i, t in enumerate(unique)}
    vectors = np.vstack([
        embedder.embed_passages(unique[i: i + batch_size]) for i in range(0, len(unique), batch_size)
    ])
    log(f"Embedded {len(unique)} unique texts from {len(records)} rows")

    groups, centroids, title_votes = [], [], defaultdict(Counter)
    by_cat: dict[str, list[int]] = defaultdict(list)
    for i, rec in enumerate(records):
        by_cat[rec["category"]].append(i)
    for c_idx, cat in enumerate(sorted(by_cat)):
        rows = by_cat[cat]
        counts = Counter(pos[texts[i]] for i in rows)
        uids = sorted(counts)
        labels, cents, sil = cluster_category(
            vectors[uids], np.array([counts[u] for u in uids], dtype=float),
            k_min, k_max, min_rows, min_silhouette, seed,
        )
        label_of = dict(zip(uids, labels))
        for g in range(len(cents)):
            members = [records[i] for i in rows if label_of[pos[texts[i]]] == g]
            if not members:
                continue
            gid = f"{c_idx:02d}-{g}"
            profile = group_profile(gid, cat, members, min_skill_share)
            profile["silhouette"] = round(sil, 3)
            groups.append(profile)
            centroids.append(cents[g])
            for m in members:
                title_votes[canon(clean_title(m["title"]))][gid] += 1
        log(f"{cat}: {len(rows)} rows -> {len(cents)} group(s), silhouette={sil:.3f}")
    titles = {
        t: votes.most_common(1)[0][0] for t, votes in title_votes.items()
        if t and votes.most_common(1)[0][1] / sum(votes.values()) >= MIN_TITLE_PURITY
    }
    # Skills found in most groups (Excel, Word...) say little about which group fits.
    df = Counter(s["name"] for g in groups for s in g["key_skills"])
    for g in groups:
        for s in g["key_skills"]:
            s["idf"] = round(float(np.log((1 + len(groups)) / (1 + df[s["name"]])) + 1.0), 3)
    return groups, np.vstack(centroids).astype(np.float32), titles


# ---------- storage (Qdrant) and placement ----------

def point_id(group_id: str) -> str:
    return str(uuid.uuid5(POINT_NAMESPACE, group_id))


class JobGroups:
    """Group profiles + centroids in a Qdrant collection, title index in memory."""

    def __init__(self, client, titles: dict[str, str], meta: dict, collection: str = COLLECTION,
                 weights: Optional[dict] = None, synonym_groups: Iterable[list[str]] = ()):
        self.client = client
        # Bilingual synonyms (configs/job_search_synonyms.yaml) let «بک اند» find «back-end» titles.
        self.synonym_groups = [[c for c in dict.fromkeys(canon(v) for v in g) if c] for g in synonym_groups]
        self.collection = collection
        self.titles = titles
        self.meta = meta
        self.weights = {**DEFAULT_PLACE_WEIGHTS, **(weights or {})}
        self._skill_rx: dict[str, re.Pattern] = {}

    # --- persistence ---

    @classmethod
    def create(cls, client, groups: list[dict], centroids: np.ndarray, titles: dict[str, str], meta: dict,
               collection: str = COLLECTION, **kwargs) -> "JobGroups":
        from qdrant_client import models

        if client.collection_exists(collection):
            client.delete_collection(collection)
        client.create_collection(
            collection, vectors_config=models.VectorParams(size=int(centroids.shape[1]), distance=models.Distance.COSINE)
        )
        client.upsert(collection, points=[
            models.PointStruct(id=point_id(g["id"]), vector=c.tolist(), payload=g) for g, c in zip(groups, centroids)
        ])
        return cls(client, titles, {**meta, "groups": len(groups)}, collection, **kwargs)

    def save_local(self, directory: Path) -> None:
        """Title index + build metadata; the groups themselves live in Qdrant."""
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "titles.json").write_text(json.dumps(self.titles, ensure_ascii=False), encoding="utf-8")
        (directory / "meta.json").write_text(json.dumps(self.meta, ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, client, directory: Path, collection: str = COLLECTION, **kwargs) -> "JobGroups":
        directory = Path(directory)
        if not client.collection_exists(collection):
            raise FileNotFoundError(f"Qdrant collection '{collection}' not found; run build_job_groups_cli")
        titles = json.loads((directory / "titles.json").read_text(encoding="utf-8"))
        meta = json.loads((directory / "meta.json").read_text(encoding="utf-8"))
        return cls(client, titles, meta, collection, **kwargs)

    def get(self, group_id: str) -> Optional[dict]:
        found = self.client.retrieve(self.collection, ids=[point_id(group_id)])
        return found[0].payload if found else None

    # --- placement ---

    def _query_variants(self, cq: str) -> list[str]:
        """The request plus one-phrase synonym swaps («بک اند» -> «back-end», ...)."""
        variants = [cq]
        for group in self.synonym_groups:
            for phrase in group:
                if phrase_regex(phrase).search(cq):
                    variants += [phrase_regex(phrase).sub(other, cq, count=1) for other in group if other != phrase]
                    break
        return list(dict.fromkeys(variants))

    def _title_hits(self, query: str) -> set[str]:
        """Groups of the LONGEST job titles found in the request or its synonym variants
        («برنامه نویس بک اند» -> «برنامه نویس back-end» wins over the generic «برنامه نویس»)."""
        token_lists = [v.split() for v in self._query_variants(canon(query))]
        longest = max((len(t) for t in token_lists), default=0)
        for size in range(min(MAX_TITLE_NGRAM, longest), 0, -1):
            hits = {gid for tokens in token_lists for i in range(len(tokens) - size + 1)
                    if (gid := self.titles.get(" ".join(tokens[i: i + size])))}
            if hits:
                return hits
        return set()

    def _mentioned(self, canon_query: str, skill: dict) -> bool:
        rx = self._skill_rx.get(skill["name"])
        if rx is None:
            parts = sorted({phrase_regex(a).pattern for a in skill["aliases"] if canon(a)}, key=len, reverse=True)
            rx = self._skill_rx[skill["name"]] = re.compile("|".join(parts)) if parts else re.compile(r"(?!x)x")
        return rx.search(canon_query) is not None

    def place(self, query_vector: np.ndarray, query: str, top_k: int = 3, candidates: int = 20) -> list[dict]:
        """Closest groups for a request: Qdrant cosine search, re-scored with skills and titles."""
        hits = self.client.query_points(
            self.collection, query=np.asarray(query_vector, dtype=np.float32).tolist(),
            limit=candidates, with_payload=True, with_vectors=True,
        ).points
        title_ids = self._title_hits(query)
        for gid in title_ids - {h.payload["id"] for h in hits}:  # a title match always competes
            hits += self.client.retrieve(self.collection, ids=[point_id(gid)], with_payload=True, with_vectors=True)
        cq = canon(query)
        matched_by_group = {h.payload["id"]: [s["name"] for s in h.payload["key_skills"] if self._mentioned(cq, s)] for h in hits}
        user_skills = {name for names in matched_by_group.values() for name in names}
        scored = []
        for h in hits:
            g = h.payload
            top_skills = g["key_skills"][:5]
            matched = matched_by_group[g["id"]]
            # F1 of: share of the group's top skills the user has, and share of the
            # user's skills the group asks for (a one-skill group no longer wins easily).
            # IDF-weighted, so generic skills (Excel, Word) count less than specific ones.
            idf = {sk["name"]: sk.get("idf", 1.0) for h2 in hits for sk in h2.payload["key_skills"]}
            top_w = sum(idf[sk["name"]] for sk in top_skills)
            recall = sum(idf[sk["name"]] for sk in top_skills if sk["name"] in matched) / top_w if top_w else 0.0
            user_w = sum(idf[n] for n in user_skills)
            precision = sum(idf[n] for n in matched) / user_w if user_w else 0.0
            skill = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
            semantic = float(np.dot(np.asarray(h.vector, dtype=np.float32), query_vector))
            scored.append({
                "group": {k: v for k, v in g.items()},
                "semantic": semantic,
                "skill": skill,
                "title": 1.0 if g["id"] in title_ids else 0.0,
                "matched_skills": matched,
                "missing_skills": [s["name"] for s in top_skills if s["name"] not in matched],
                "centroid": np.asarray(h.vector, dtype=np.float32),
            })
        if not scored:
            return []
        # Components that carry no signal for this request do not dilute the score.
        w = dict(self.weights)
        if not any(s["skill"] for s in scored):
            w["skill"] = 0.0
        if not title_ids:
            w["title"] = 0.0
        total = sum(w.values()) or 1.0
        for s in scored:
            s["fit"] = round((w["semantic"] * s["semantic"] + w["skill"] * s["skill"] + w["title"] * s["title"]) / total, 4)
            s["semantic"] = round(s["semantic"], 4)
        scored.sort(key=lambda s: -s["fit"])
        return scored[:top_k]


def create_qdrant_client(url: str = "", path: str = ""):
    """url -> server (docker service); path -> embedded local storage; neither -> in-memory."""
    from qdrant_client import QdrantClient

    if url:
        return QdrantClient(url=url)
    return QdrantClient(path=path) if path else QdrantClient(":memory:")


def public_group(placement: dict) -> dict:
    """Placement as returned by the API (no vectors)."""
    return {k: v for k, v in placement.items() if k != "centroid"}
