"""Multi-university foundation: institutions, their email domains and student-ID rules, and each person's affiliation.

What is real data and where it came from:
  * institutions: the Ministry of Education directory of colleges and universities (data.gov.tw dataset 6091,
    https://stats.moe.gov.tw/files/opendata/u1_new.json), academic year 115, saved in data/institutions_moe.csv.
    Chinese names only: that dataset has no English names, so name_en stays "" until checked on the school's own site.
  * NTHU's English name, departments (departments.json, 127 units with sources), email domains and its 9-digit student
    ID rule come from the app's existing, reviewed NTHU data.
  * every other school: no department catalog and no student-ID rule yet. Students type their department, any student
    ID is accepted for MANUAL review, and nothing is guessed.

Uniqueness: one current account per (institution, student ID). The old site-wide rule on User.student_id still holds
for NTHU accounts (they keep writing it); other schools' IDs live only in Affiliation, so the same number at two
schools never collides.

Safe migration (python -m app.academics ...), every step dry-run unless --apply:
  import     add/refresh institutions from data/institutions_moe.csv (+ NTHU domains, rule, renewal date)
  migrate    give every existing account without an affiliation an NTHU one, copying its department, degree and student
             ID unchanged; refuses if two accounts would share an NTHU student ID
  research   mark unclassified Research projects "review"; give each research position its professor's university
  check      counts that must match after migrating (users vs current affiliations, duplicates)
Rollback: MULTI_SCHOOL=0 hides the new sign-up fields; affiliations are additive and can be ignored or deleted.
"""
import csv, os, re, sys
from datetime import datetime
from sqlmodel import Session, select
from .models import User, Institution, InstitutionDomain, StudentIdRule, Affiliation

HERE = os.path.dirname(__file__)
CSV = os.path.join(HERE, "..", "data", "institutions_moe.csv")
MOE_URL = "https://data.gov.tw/dataset/6091"
MOE_FILE = "https://stats.moe.gov.tw/files/opendata/u1_new.json"
MOE_YEAR = "115"
SYSTEMS = {"1": "general", "2": "technological", "3": "teachers"}
NTHU = "0002"
NTHU_EN = ("National Tsing Hua University", "https://nthu-en.site.nthu.edu.tw/")
NTHU_DOMAINS = [("nthu.edu.tw", "staff"), ("gapp.nthu.edu.tw", "both"), ("oz.nthu.edu.tw", "student")]   # + m1xx.nthu.edu.tw (student mail, by year)
NTHU_SID = (r"\d{9}", "115006212", "existing NTHU rule in this app (9 digits)")
SID_OK = re.compile(r"^[A-Za-z0-9-]{4,20}$")   # what any student number may look like before a school-specific rule


def norm_sid(sid: str) -> str: return re.sub(r"\s+", "", sid or "").upper()


def nthu(s): return s.exec(select(Institution).where(Institution.moe_code == NTHU)).first()


def current(s, u):
    return s.exec(select(Affiliation).where(Affiliation.user_id == u.id, Affiliation.current == True)).first() if u and u.id else None


def institution_of_factory(s):
    """institution_of(user) -> institution id of their current affiliation, or None (for impact numbers)."""
    rows = s.exec(select(Affiliation).where(Affiliation.current == True)).all()
    m = {a.user_id: a.institution_id for a in rows}
    return lambda u: m.get(u.id)


def renewal_mmdd(u):
    from .db import engine
    with Session(engine) as s:
        a = current(s, u)
        inst = s.get(Institution, a.institution_id) if a else None
        return inst.renewal_mmdd if inst and inst.renewal_mmdd else ""


def check_sid(s, inst, degree, sid):
    """("ok"|"review"|"bad", message). A documented rule must match; with no rule the ID goes to manual review."""
    sid = (sid or "").strip()
    if not SID_OK.match(sid): return "bad", "Enter your student ID as it is printed on your student card (4 to 20 letters or digits)."
    rules = [r for r in s.exec(select(StudentIdRule).where(StudentIdRule.institution_id == inst.id)).all() if r.degree in ("", degree)]
    if not rules: return "review", ""
    if any(re.fullmatch(r.pattern, sid) for r in rules): return "ok", ""
    ex = next((r.example for r in rules if r.example), "")
    return "bad", f"This doesn't look like a student ID from {inst.name_en or inst.name_zh}" + (f", for example {ex}." if ex else ".")


def sid_taken(s, inst_id, sid) -> bool:
    n = norm_sid(sid)
    return bool(n) and s.exec(select(Affiliation.id).where(Affiliation.institution_id == inst_id, Affiliation.sid_norm == n,
                                                           Affiliation.current == True)).first() is not None


def attach(s, u, inst, degree="", sid="", unit_key="", unit_text="", kind="student", review=""):
    """Record a new current affiliation (the caller commits)."""
    forget_ident()
    for old in s.exec(select(Affiliation).where(Affiliation.user_id == u.id, Affiliation.current == True)).all(): old.current = False
    a = Affiliation(user_id=u.id, institution_id=inst.id, unit_key=unit_key, unit_text=unit_text[:80], degree=degree,
                    student_id=(sid or "").strip()[:20], sid_norm=norm_sid(sid)[:20], kind=kind, review=review)
    s.add(a); return a


# ---------- identity tags: every person is shown with their university and their role ----------
ROLE_T = {"en": {"student": "Student", "professor": "Professor", "researcher": "Researcher", "admin": "Admin"},
          "zh": {"student": "學生", "professor": "教授", "researcher": "研究人員", "admin": "管理員"}}
NO_INST = {"en": "University not set", "zh": "尚未設定學校"}
_ID = {"at": 0.0, "aff": {}, "inst": {}}


def forget_ident(): _ID["at"] = 0.0


def _ident_cache():
    """{user_id: (institution_id, kind)} for current affiliations and {institution_id: (name_en, name_zh)}, kept 30 s."""
    import time
    if time.time() - _ID["at"] > 30:
        from .db import engine
        with Session(engine) as s:
            _ID["inst"] = {i.id: (i.name_en, i.name_zh) for i in s.exec(select(Institution)).all()}
            _ID["aff"] = {a.user_id: (a.institution_id, a.kind) for a in s.exec(select(Affiliation).where(Affiliation.current == True)).all()}
        _ID["at"] = time.time()
    return _ID


def inst_name(iid, lang="en"):
    """Official English name when it has been checked, otherwise the official Chinese name; never a made-up translation."""
    n = _ident_cache()["inst"].get(iid)
    if not n: return ""
    return n[1] if lang == "zh" or not n[0] else n[0]


def ident(u, lang="en"):
    """What every profile shows: university (from the person's own current affiliation, never guessed from the email or
    department) and role. No affiliation = inst "" (shown as "University not set")."""
    if not u: return None
    lang = "zh" if lang == "zh" else "en"
    a = _ident_cache()["aff"].get(u.id)
    kind = a[1] if a else ""
    if u.role == "faculty": role = "researcher" if kind == "researcher" else "professor"
    elif u.is_admin and not a: role = "admin"
    else: role = "student"
    return dict(inst=inst_name(a[0], lang) if a else "", inst_id=a[0] if a else None, role=role, role_label=ROLE_T[lang][role],
                none_label=NO_INST[lang])


def institution_id_of(s, u):
    a = current(s, u)
    return a.institution_id if a else None


def label(s, u, lang="en"):
    a = current(s, u)
    inst = s.get(Institution, a.institution_id) if a else None
    if not inst: return ""
    return inst.name_zh if lang == "zh" or not inst.name_en else inst.name_en


def choices(s, lang="en"):
    """(moe_code, display name) for the sign-up list: NTHU first, then by MOE code."""
    rows = s.exec(select(Institution).where(Institution.active == True).order_by(Institution.moe_code)).all()
    rows.sort(key=lambda i: (i.moe_code != NTHU, i.moe_code))
    return [(i.moe_code, (i.name_en + " " + i.name_zh) if i.name_en and lang != "zh" else i.name_zh) for i in rows]


# ---------- maintenance commands ----------
def read_csv():
    with open(CSV, encoding="utf-8") as f:
        return [r for r in csv.DictReader(f, delimiter="|")]


def do_import(s, apply=False):
    now = datetime.utcnow(); added = updated = 0
    for r in read_csv():
        i = s.exec(select(Institution).where(Institution.moe_code == r["moe_code"])).first()
        vals = dict(name_zh=r["name_zh"], public=r["public"] == "G", system=SYSTEMS.get(r["system"], ""), city=r["city"],
                    website=r["website_host"], source_url=MOE_URL, source_year=MOE_YEAR, checked_at=now)
        if i is None:
            added += 1
            if apply: s.add(Institution(moe_code=r["moe_code"], **vals))
        elif any(getattr(i, k) != v for k, v in vals.items() if k != "checked_at"):
            updated += 1
            if apply:
                for k, v in vals.items(): setattr(i, k, v)
    if apply:
        s.commit()
        n = nthu(s)
        if n:
            n.name_en, n.en_source, n.catalog = NTHU_EN[0], NTHU_EN[1], "nthu"
            for d, aud in NTHU_DOMAINS:
                if not s.exec(select(InstitutionDomain).where(InstitutionDomain.institution_id == n.id, InstitutionDomain.domain == d)).first():
                    s.add(InstitutionDomain(institution_id=n.id, domain=d, audience=aud, source_url="app/faculty.py (existing NTHU rules)"))
            if not s.exec(select(StudentIdRule).where(StudentIdRule.institution_id == n.id)).first():
                s.add(StudentIdRule(institution_id=n.id, pattern=NTHU_SID[0], example=NTHU_SID[1], source_url=NTHU_SID[2]))
            s.commit()
    return dict(added=added, updated=updated, rows=len(read_csv()))


def do_migrate(s, apply=False):
    n = nthu(s)
    if not n: return dict(error="run 'import' first: NTHU is not in the institution table")
    have = {a.user_id for a in s.exec(select(Affiliation)).all()}
    todo = [u for u in s.exec(select(User)).all() if u.id not in have and not u.is_admin]
    seen, dups = {}, []
    for u in todo:
        k = norm_sid(u.student_id) if u.role != "faculty" else ""
        if k and k in seen: dups.append((seen[k], u.id, k))
        elif k: seen[k] = u.id
    taken = {a.sid_norm for a in s.exec(select(Affiliation).where(Affiliation.institution_id == n.id, Affiliation.current == True)).all() if a.sid_norm}
    dups += [(None, u.id, norm_sid(u.student_id)) for u in todo if norm_sid(u.student_id) in taken]
    if dups: return dict(error="duplicate NTHU student IDs: fix these accounts first", duplicates=dups)
    if apply:
        for u in todo:
            fac = u.role == "faculty"
            attach(s, u, n, degree="" if fac else (u.degree or ""), sid="" if fac else u.student_id,
                   unit_key=u.dept_id or "", unit_text="" if u.dept_id else (u.faculty or ""), kind="professor" if fac else "student")
        s.commit()
    return dict(accounts=len(todo), applied=apply)


def do_research(s, apply=False):
    """Research eligibility data, after 'migrate':
    * Research projects with no explicit research_mode are marked "review" (kept open as before, listed for admins):
      the mode is never guessed from the owner's role or the title.
    * Every research position (Opening) is professor-led by definition: it gets its professor's current university.
      A professor with no university on record is reported, not guessed."""
    from .models import Project, Opening
    review = [p for p in s.exec(select(Project).where(Project.kind == "Research")).all() if p.research_mode not in ("student", "advisor", "review")]
    fix, unresolved = [], []
    for o in s.exec(select(Opening).where(Opening.institution_id == None)).all():
        a = current(s, s.get(User, o.owner_id))
        (fix if a else unresolved).append((o, a.institution_id if a else None))
    if apply:
        for p in review: p.research_mode = "review"; s.add(p)
        for o, iid in fix: o.institution_id = iid; s.add(o)
        s.commit()
    return dict(research_to_review=[p.id for p in review], openings_set={o.id: iid for o, iid in fix},
                openings_unresolved=[o.id for o, _ in unresolved], applied=apply)


def do_check(s):
    users = [u for u in s.exec(select(User)).all() if not u.is_admin]
    cur = s.exec(select(Affiliation).where(Affiliation.current == True)).all()
    per = {}
    for a in cur: per[a.user_id] = per.get(a.user_id, 0) + 1
    keys = [(a.institution_id, a.sid_norm) for a in cur if a.sid_norm]
    return dict(accounts=len(users), with_affiliation=sum(1 for u in users if per.get(u.id)), more_than_one=sum(1 for v in per.values() if v > 1),
                duplicate_ids=len(keys) - len(set(keys)), institutions=len(s.exec(select(Institution)).all()))


if __name__ == "__main__":
    from .db import engine, init_db
    init_db()
    cmd, apply = (sys.argv[1] if len(sys.argv) > 1 else "check"), "--apply" in sys.argv
    with Session(engine) as s:
        out = {"import": do_import, "migrate": do_migrate, "research": do_research}.get(cmd, lambda s, apply=False: do_check(s))(s, apply) if cmd != "check" else do_check(s)
    print(out)
    if cmd in ("import", "migrate", "research") and not apply: print("dry run: nothing written (add --apply)")
