"""Who may join what, by university.

Two research models, with different rules:
  * professor-led research: a professor's research position (Opening) and a Research project whose research_mode is
    "advisor". Only students whose CURRENT affiliation is the university chosen for it (institution_id) may apply,
    be invited or be accepted. The professor picks that university from their own affiliations when publishing.
  * student-led research (research_mode "student") and every other kind of project: open to students of every
    university in Taiwan.
research_mode "review" marks an older Research project nobody has classified yet: it keeps working as before (open)
and is listed for admins until its owner or an admin chooses. The mode is never inferred from the owner or the title.

Every check here runs on the server, on each step that can add a person: apply, invite, accept an application,
accept an invitation, accept a research-position application. The university comes from the affiliation table
(set at sign-up or by an admin, never by an ordinary profile edit).
"""
from sqlmodel import select
from .models import Affiliation, User
from . import academics as AC

MODES = ("student", "advisor")


def project_inst(pr, role=None):
    """Institution a seat is restricted to, or None when it is open to every university. Advisor seats (for professors
    and mentors) are not student seats and stay open."""
    if pr is None or pr.kind != "Research" or pr.research_mode != "advisor": return None
    if role is not None and role.advisor: return None
    return pr.institution_id or -1   # -1: professor-led but its university is missing, so nobody qualifies (fail closed)


def opening_inst(o):
    return (o.institution_id or -1) if o is not None else None


def check(s, user, inst_id):
    """(ok, reason) for joining something restricted to inst_id. reason: "" | "noinst" | "other" | "unset"."""
    if inst_id is None: return True, ""
    if inst_id == -1: return False, "unset"
    mine = AC.institution_id_of(s, user) if user else None
    if mine is None: return False, "noinst"
    return (True, "") if mine == inst_id else (False, "other")


def for_project(s, user, pr, role=None): return check(s, user, project_inst(pr, role))


def for_opening(s, user, o): return check(s, user, opening_inst(o))


def own_institutions(s, u):
    """The affiliations a professor can publish under: their current ones (explicit choice on the form)."""
    if not u or not u.id: return []
    rows = s.exec(select(Affiliation).where(Affiliation.user_id == u.id, Affiliation.current == True)).all()
    return [a.institution_id for a in rows]


REASONS = {
    "en": {"other": "This is professor-led research: only students of {inst} can apply. Your account is registered at {mine}.",
           "noinst": "This is professor-led research: only students of {inst} can apply. Your account has no university on record yet, so you can't apply.",
           "unset": "This professor-led research has no university set yet, so it can't take applications. The professor or an admin needs to fix it."},
    "zh": {"other": "這是教授主導的研究：只有{inst}的學生可以申請。你的帳號登記的學校是{mine}。",
           "noinst": "這是教授主導的研究：只有{inst}的學生可以申請。你的帳號還沒有登記學校，所以無法申請。",
           "unset": "這個教授主導的研究還沒有設定學校，暫時無法接受申請。需要教授或管理員先修正。"},
}


def reason_text(s, user, inst_id, reason, lang="en"):
    lang = "zh" if lang == "zh" else "en"
    if not reason: return ""
    mine = AC.institution_id_of(s, user) if user else None
    return REASONS[lang][reason].format(inst=AC.inst_name(inst_id, lang) or "?", mine=AC.inst_name(mine, lang) if mine else "")


def team_universities(s, user_ids):
    """Distinct institution ids among these people (for the 'members from N universities' line)."""
    ids = [i for i in user_ids if i]
    if not ids: return set()
    rows = s.exec(select(Affiliation.institution_id).where(Affiliation.user_id.in_(ids), Affiliation.current == True)).all()
    return set(rows)
