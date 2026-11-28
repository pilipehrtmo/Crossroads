"""Embedding similarity + a small ML ranker. Falls back to plain tag overlap if the libraries are missing."""
import os, functools
import numpy as np
from .config import MATCH_MODE
MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"   # multilingual, ~120 MB, runs on CPU
RANKER_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "ranker.joblib")

import threading
_lock = threading.Lock(); _model = None; _cache = {}

def _cross(user, owner):
    """1.0 when the two people come from different departments (the linked department when there is one, else the typed text)."""
    from .departments import key
    if not (owner and key(user) and key(owner)): return 0.0
    return 1.0 if key(user) != key(owner) else 0.0

def load_now():
    """Load the embedding model (slow the first time). Returns True if it is available."""
    global _model
    with _lock:
        if _model is None:
            try:
                from sentence_transformers import SentenceTransformer
                try: _model = SentenceTransformer(MODEL_NAME, local_files_only=True)   # cached copy: no network wait
                except Exception: _model = SentenceTransformer(MODEL_NAME)
            except Exception as e: print("Embedding model unavailable, using tag overlap only:", e)
    return _model is not None

def warm(): threading.Thread(target=load_now, daemon=True).start()   # load in the background so pages never hang

def embed(text):
    if _model is None: return None    # not loaded yet: callers fall back to tag overlap instead of blocking
    v = _cache.get(text)
    if v is None: v = _cache[text] = _model.encode(text, normalize_embeddings=True)
    return v

def tagset(t): return {x.strip().lower() for x in t.split(",") if x.strip()}
def jaccard(a, b):
    a, b = tagset(a), tagset(b); u = a | b
    return len(a & b) / len(u) if u else 0.0

def similarity(a, b):
    if not a.strip() or not b.strip(): return None
    ea, eb = embed(a), embed(b)
    return None if ea is None or eb is None else float(max(0.0, np.dot(ea, eb)))

def features(sim, tags_a, tags_b, hours_ok, cross):
    return [sim, jaccard(tags_a, tags_b), hours_ok, cross]   # order matters: train.py uses the same

@functools.lru_cache(1)
def _ranker():
    try:
        import joblib; return joblib.load(RANKER_PATH)
    except Exception: return None

def score(student_text, student_tags, seat_text, seat_tags, hours_ok, cross):
    j = jaccard(student_tags, seat_tags)
    if MATCH_MODE == "tags": return j
    sim = similarity(student_text, seat_text)
    if sim is None: return j
    if MATCH_MODE == "embeddings": return sim
    f = features(sim, student_tags, seat_tags, hours_ok, cross); r = _ranker()
    if r is not None: return float(r.predict_proba([f])[0][1])
    return 0.7 * sim + 0.3 * f[1]

# ---------- live matching: skill coverage (no embeddings or ranker; those stay for offline evaluation in train.py) ----------
from . import skills as SK

COV_T = {   # explanation lines, in both site languages
    "covers": {"en": "Covers {n} of {m} must-have skills: {x}", "zh": "符合 {m} 項必備技能中的 {n} 項：{x}"},
    "covers0": {"en": "Covers 0 of {m} must-have skills", "zh": "符合 {m} 項必備技能中的 0 項"},
    "missing": {"en": "Missing must-have: {x}", "zh": "缺少必備技能：{x}"},
    "nice": {"en": "Also has (nice to have): {x}", "zh": "加分技能：{x}"},
    "related": {"en": "Related but not counted: has {have}, the seat asks for {need}", "zh": "相關但不算符合：有 {have}，職位需要 {need}"},
    "complement": {"en": "Adds {x}, which no one on the team has yet", "zh": "帶來團隊目前沒有的技能：{x}"},
    "nomust": {"en": "This seat lists no must-have skills", "zh": "這個職位沒有列出必備技能"},
    "label": {"en": "{p}% match", "zh": "{p}% 符合"},
}
def _say(k, lang, **kw): return COV_T[k]["zh" if lang == "zh" else "en"].format(**kw)


def coverage(person_skills, role, team_skills=None):
    """How one person's skills cover one seat. Must-have = the seat's skills; nice-to-have = its nice_skills.

    rank = 1000 * (share of must-have skills covered) + (nice-to-have skills covered): optional skills only break ties,
    so they can never make up for a missing must-have. A seat with no must-have skills gives no ranking claim (rank None).
    team_skills: skills the accepted members already bring; used only to say what this person would add.
    """
    have = SK.tags(person_skills) if isinstance(person_skills, str) else list(person_skills)
    must = SK.tags(role.skills)
    nice = [t for t in SK.tags(getattr(role, "nice_skills", "") or "") if t not in must]
    hs = set(have)
    must_have = [t for t in must if t in hs]; must_missing = [t for t in must if t not in hs]
    nice_have = [t for t in nice if t in hs]; nice_missing = [t for t in nice if t not in hs]
    rel = [(t, SK.related_to(t, hs)) for t in must_missing + nice_missing]
    rel = [(t, r) for t, r in rel if r]
    team = set(SK.tags(team_skills)) if isinstance(team_skills, str) else set(team_skills or [])
    adds = [t for t in must_have + nice_have if t not in team] if team_skills is not None else []
    rank = None if not must else 1000 * len(must_have) // len(must) + len(nice_have)
    return dict(must=must, nice=nice, must_have=must_have, must_missing=must_missing, nice_have=nice_have,
                nice_missing=nice_missing, related=rel, adds=adds, rank=rank)


def explain(c, lang="en"):
    """Plain sentences for a coverage result, built only from the data in it."""
    if not c["must"]: out = [_say("nomust", lang)]
    elif c["must_have"]: out = [_say("covers", lang, n=len(c["must_have"]), m=len(c["must"]), x=", ".join(c["must_have"]))]
    else: out = [_say("covers0", lang, m=len(c["must"]))]
    if c["must"] and c["must_missing"]: out.append(_say("missing", lang, x=", ".join(c["must_missing"])))
    if c["nice_have"]: out.append(_say("nice", lang, x=", ".join(c["nice_have"])))
    for need, have in c["related"][:2]: out.append(_say("related", lang, have=", ".join(have), need=need))
    if c["adds"]: out.append(_say("complement", lang, x=", ".join(c["adds"])))
    return out


def pct(c):
    """Match percentage shown on cards and seats: the share of the seat's must-have skills the person has (0-100).
    None when the seat lists no must-have skills (no claim)."""
    return None if not c["must"] else 100 * len(c["must_have"]) // len(c["must"])


def label(c, lang="en"):
    """Short badge text, e.g. "67% match"; None when the seat lists no must-have skills. The must-have details
    ("Covers 2 of 3 must-have skills") are shown in the For you explanation instead."""
    p = pct(c)
    return None if p is None else _say("label", lang, p=p)


def match_pct(user, role, project, owner):
    """Kept for old callers: the share of must-have skills covered, 0-100 (no longer a similarity score)."""
    c = coverage(user.skills, role)
    return None if c["rank"] is None else c["rank"] // 10


def why(user, role, pct, lang="en"):
    return " · ".join(explain(coverage(user.skills, role), lang))


def team_gap(people, roles):
    """What a team already has and what it still lacks, from the REAL profiles of the lead and accepted members
    (a filled seat proves nothing about skills). roles: the project's non-advisor seats.
    Returns have (all skills the people bring), covered/missing must-have and nice-to-have skills across the seats."""
    have = []
    for u in people:
        for t in SK.tags(getattr(u, "skills", "") if u else ""):
            if t not in have: have.append(t)
    hs = set(have); must, nice = [], []
    for r in roles:
        for t in SK.tags(r.skills):
            if t not in must: must.append(t)
        for t in SK.tags(getattr(r, "nice_skills", "") or ""):
            if t not in nice: nice.append(t)
    nice = [t for t in nice if t not in must]
    return dict(have=have, must_covered=[t for t in must if t in hs], must_missing=[t for t in must if t not in hs],
                nice_covered=[t for t in nice if t in hs], nice_missing=[t for t in nice if t not in hs],
                open_seats=sum(1 for r in roles if not r.filled), filled_seats=sum(1 for r in roles if r.filled))
