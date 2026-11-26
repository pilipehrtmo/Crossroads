"""Impact numbers (/impact): what Matchmaker has really done, counted from the database.

Only REAL records count: a person or project marked origin "seed" (sample content we posted) or "demo" (presentation
accounts) never adds to a number, and neither do admins or banned accounts. Seed and demo counts are shown separately
so anyone can see what was left out. Nothing is estimated: every number is a COUNT over rows.

Definitions (also printed on the page):
  team formed         a real project with at least one accepted member who is a real person other than the lead
  collaboration       one accepted member on such a project (advisor seats counted separately)
  cross-department    the member's department differs from the lead's (both known)
  cross-college       the member's college differs from the lead's (both linked to an NTHU department)
  cross-university    the member's current institution differs from the lead's (only once affiliations exist)
"""
import time
from sqlmodel import Session, select
from .models import User, Project, Role, Application
from . import departments as DEP

REAL = "real"
_cache = {"at": 0.0, "data": None}


def counts(s: Session, institution_of=None) -> dict:
    """All impact numbers. institution_of(user) -> institution id or None (cross-university needs affiliations)."""
    users = {u.id: u for u in s.exec(select(User)).all()}
    projects = {p.id: p for p in s.exec(select(Project)).all()}
    rows = s.exec(select(Application, Role).join(Role, Role.id == Application.role_id).where(Application.status == "accepted")).all()

    def real_person(u): return bool(u) and getattr(u, "origin", REAL) == REAL and not u.is_admin and not u.banned
    def real_project(p): return bool(p) and getattr(p, "origin", REAL) == REAL and real_person(users.get(p.owner_id))

    teams, collab, advisors, cross_dept, cross_col, cross_uni, excluded = set(), 0, 0, 0, 0, 0, 0
    for a, r in rows:
        p = projects.get(r.project_id); m = users.get(a.user_id)
        if not p or not m or m.id == p.owner_id: continue
        if not (real_project(p) and real_person(m)): excluded += 1; continue
        lead = users[p.owner_id]
        if r.advisor: advisors += 1; continue
        collab += 1; teams.add(p.id)
        kl, km = DEP.key(lead), DEP.key(m)
        if kl and km and kl != km: cross_dept += 1
        cl, cm = DEP.colleges_of(lead.dept_id or ""), DEP.colleges_of(m.dept_id or "")
        if cl and cm and not (cl & cm): cross_col += 1
        if institution_of:
            il, im = institution_of(lead), institution_of(m)
            if il and im and il != im: cross_uni += 1
    people = [u for u in users.values() if real_person(u)]
    return dict(
        teams=len(teams), collaborations=collab, advisors=advisors, cross_department=cross_dept, cross_college=cross_col,
        cross_university=cross_uni if institution_of else None,
        people=len(people), verified=sum(1 for u in people if u.verified or u.is_faculty),
        projects=sum(1 for p in projects.values() if real_project(p)),
        excluded=dict(projects=sum(1 for p in projects.values() if getattr(p, "origin", REAL) != REAL),
                      people=sum(1 for u in users.values() if getattr(u, "origin", REAL) != REAL),
                      collaborations=excluded))


def cached(s: Session, institution_of=None, ttl=600) -> dict:
    if _cache["data"] is None or time.time() - _cache["at"] > ttl:
        _cache["data"], _cache["at"] = counts(s, institution_of), time.time()
    return _cache["data"]
