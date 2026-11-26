"""Find teammates and invitations.

A project lead opens "Find teammates" under an open seat and sees verified students who said they are open to join a
team (User.open_to_join), ranked by how well their skills cover the seat (matching.coverage, the same rule as the board).
The lead can invite them; the student accepts or declines from Activity.

Rules (all checked on the server, every time):
  * only verified, opted-in, not banned, non-admin students are listed or can be invited; blocked pairs never meet
  * only a verified lead (student or professor) or an admin can invite; pending students cannot
  * one invitation per person per seat, ever: after a decline the lead cannot ask again
  * at most INVITES_PER_DAY invitations per lead per 24 hours and PENDING_PER_SEAT pending per seat
  * demo or seed projects only find demo or seed people, and real projects only real people, so demo data never
    mixes with real users
  * accepting fills the seat with take_seat() (one statement, one winner) and records an accepted Application, so the
    team page, contacts, track record and impact numbers all work exactly as for an application
Contact details stay hidden until the invitation is accepted, as with applications.
"""
from datetime import datetime, timedelta
from fastapi import Request, Depends, Form, HTTPException
from sqlmodel import Session, select, or_, and_
from .db import get_session
from .models import User, Project, Role, Application, Invitation, Block, Report
from . import departments as DEP
from . import validate as V
from .matching import coverage, explain, label as cov_label, team_gap
from .main import app, render, me, go, limited, days_left, team_info, take_seat, pick_lang

INVITES_PER_DAY = 10
PENDING_PER_SEAT = 3
SHOW = 10


def blocked(s: Session, a: int, b: int) -> bool:
    """True when either person blocked the other."""
    return s.exec(select(Block.id).where(or_(and_(Block.blocker_id == a, Block.blocked_id == b),
                                             and_(Block.blocker_id == b, Block.blocked_id == a)))).first() is not None


def can_invite(u) -> bool:
    """Verified students, verified professors and admins may invite; pending accounts may not."""
    return bool(u) and not u.banned and (u.is_admin or u.is_faculty or bool(u.verified))


def discoverable(u) -> bool:
    return bool(u) and u.open_to_join and bool(u.verified) and not u.banned and not u.is_admin and not u.is_faculty


def _same_world(pr, u) -> bool:
    """Real projects meet real people; demo/seed projects meet demo/seed people."""
    return (getattr(pr, "origin", "real") == "real") == (getattr(u, "origin", "real") == "real")


def seat_for_lead(s, user, rid):
    """(role, project) when `user` may recruit for this open, non-advisor seat; else raises 404/403."""
    r = s.get(Role, rid); pr = s.get(Project, r.project_id) if r else None
    if not pr: raise HTTPException(404)
    if not user or not (user.id == pr.owner_id or user.is_admin): raise HTTPException(403)
    return r, pr


def candidates(s, pr, r, lead, college="", degree="", other_college=False):
    """Up to SHOW ranked candidates for one seat, each with its coverage and plain reasons."""
    ti = team_info(s, pr)
    team = {pr.owner_id} | {u.id for u, _ in ti["members"] + ti["advisors"]}
    have = ti["gap"]["have"]
    invited = {i.user_id: i for i in s.exec(select(Invitation).where(Invitation.role_id == r.id)).all()}
    applied = set(s.exec(select(Application.user_id).where(Application.role_id == r.id, Application.status == "pending")).all())
    lead_cols = DEP.colleges_of(getattr(s.get(User, pr.owner_id), "dept_id", "") or "")
    blocks = s.exec(select(Block).where(or_(Block.blocker_id == pr.owner_id, Block.blocked_id == pr.owner_id))).all()
    blocked_ids = {b.blocked_id for b in blocks} | {b.blocker_id for b in blocks}
    from .academics import institution_of_factory
    inst_of = institution_of_factory(s); lead_inst = inst_of(s.get(User, pr.owner_id))
    out = []
    for u in s.exec(select(User).where(User.open_to_join == True, User.verified == True, User.banned == False,
                                       User.is_admin == False, User.is_faculty == False)).all():
        if u.id in team or u.id in blocked_ids or not _same_world(pr, u): continue
        cols = DEP.colleges_of(u.dept_id or "")
        if college and college not in cols: continue
        if degree and (u.degree or "") != degree: continue
        other = bool(lead_cols and cols and not (lead_cols & cols))
        if other_college and not other: continue
        c = coverage(u.skills, r, have)
        if not (c["must_have"] or c["nice_have"]): continue          # nothing in common with this seat: not a candidate
        ui = inst_of(u); other_uni = bool(lead_inst and ui and ui != lead_inst)
        out.append(dict(u=u, cov=c, other=other or other_uni, other_uni=other_uni, invited=invited.get(u.id), applied=u.id in applied,
                        hours_ok=(u.hours or 0) >= (pr.hours_per_week or 0)))
    out.sort(key=lambda x: (-(x["cov"]["rank"] if x["cov"]["rank"] is not None else len(x["cov"]["nice_have"])),
                            not x["other"], not x["hours_ok"], x["u"].id))
    return out[:SHOW]


@app.get("/roles/{rid}/candidates")
def find_teammates(req: Request, rid: int, college: str = "", degree: str = "", other: str = "",
                   user=Depends(me), s: Session = Depends(get_session)):
    if not user: return go("/login")
    r, pr = seat_for_lead(s, user, rid)
    lang = pick_lang(req)
    ok = not r.filled and not r.advisor and pr.status == "open"
    rows = candidates(s, pr, r, user, college=college, degree=degree, other_college=bool(other)) if ok else []
    for x in rows: x["why"] = explain(x["cov"], lang); x["label"] = cov_label(x["cov"], lang)
    sent = len(s.exec(select(Invitation.id).where(Invitation.from_id == user.id, Invitation.at > datetime.utcnow() - timedelta(days=1))).all())
    pend = len(s.exec(select(Invitation.id).where(Invitation.role_id == r.id, Invitation.status == "pending")).all())
    return render(req, "candidates.html", user, r=r, pr=pr, rows=rows, ok=ok, can=can_invite(user), sent=sent, pend=pend,
                  per_day=INVITES_PER_DAY, per_seat=PENDING_PER_SEAT, colleges=[(c["id"], c["zh"] if lang == "zh" else c["en"]) for c in DEP.COLLEGES.values() if c.get("kind") != "phased_out"], college=college,
                  degree=degree, other=bool(other), degrees=DEP.DEGREES, notice=req.query_params.get("n", ""))


@app.post("/roles/{rid}/invite/{uid}", dependencies=[limited("invite", 30, 3600)])
def invite(rid: int, uid: int, message: str = Form(""), user=Depends(me), s: Session = Depends(get_session)):
    if not user: return go("/login")
    r, pr = seat_for_lead(s, user, rid)
    back = f"/roles/{rid}/candidates"
    if not can_invite(user): return go(back + "?n=notverified")
    d = days_left(pr.deadline)
    if r.filled or r.advisor or pr.status != "open" or (d is not None and d < 0): return go(back + "?n=closed")
    u = s.get(User, uid)
    if not discoverable(u) or not _same_world(pr, u) or u.id == pr.owner_id: return go(back + "?n=notopen")
    if blocked(s, pr.owner_id, u.id) or blocked(s, user.id, u.id): return go(back + "?n=notopen")
    if s.exec(select(Invitation.id).where(Invitation.role_id == rid, Invitation.user_id == uid)).first(): return go(back + "?n=already")
    if s.exec(select(Application.id).where(Application.role_id == rid, Application.user_id == uid, Application.status.in_(["pending", "accepted"]))).first():
        return go(back + "?n=applied")
    since = datetime.utcnow() - timedelta(days=1)
    if len(s.exec(select(Invitation.id).where(Invitation.from_id == user.id, Invitation.at > since)).all()) >= INVITES_PER_DAY:
        return go(back + "?n=daylimit")
    if len(s.exec(select(Invitation.id).where(Invitation.role_id == rid, Invitation.status == "pending")).all()) >= PENDING_PER_SEAT:
        return go(back + "?n=seatlimit")
    message = V.normalize_text(message)[:400]
    s.add(Invitation(role_id=rid, project_id=pr.id, user_id=uid, from_id=user.id, message=message))
    try: s.commit()
    except Exception:   # the unique (seat, person) index: a second click or a second tab got there first
        s.rollback(); return go(back + "?n=already")
    from .notify import notify
    notify(s, [uid], "invite", f"{user.name or user.handle} invited you to the {r.name} seat on {pr.title}", "/activity#invites", pr.id, user.id)
    return go(back + "?n=invited")


@app.post("/invitations/{iid}/{decision}", dependencies=[limited("invdecide", 60, 3600)])
def decide_invitation(iid: int, decision: str, user=Depends(me), s: Session = Depends(get_session)):
    if not user: return go("/login")
    inv = s.get(Invitation, iid)
    if not inv: raise HTTPException(404)
    r = s.get(Role, inv.role_id); pr = s.get(Project, inv.project_id)
    from .notify import notify
    if decision == "withdrawn":   # the lead takes it back
        if not (user.id == inv.from_id or user.id == pr.owner_id or user.is_admin): raise HTTPException(403)
        if inv.status == "pending": inv.status, inv.decided_at = "withdrawn", datetime.utcnow(); s.commit()
        return go(f"/roles/{inv.role_id}/candidates?n=withdrawn")
    if user.id != inv.user_id: raise HTTPException(403)
    if inv.status != "pending" or decision not in ("accepted", "declined"): return go("/activity#invites")
    if decision == "declined":
        inv.status, inv.decided_at = "declined", datetime.utcnow(); s.commit()
        notify(s, [inv.from_id], "invite_decision", f"{user.name or user.handle} declined your invitation to {pr.title}", f"/projects/{pr.id}#seats", pr.id, user.id)
        return go("/activity?n=invdeclined#invites")
    d = days_left(pr.deadline)
    if pr.status != "open" or (d is not None and d < 0) or blocked(s, pr.owner_id, user.id) or user.banned:
        inv.status, inv.decided_at = "closed", datetime.utcnow(); s.commit()
        return go("/activity?n=invclosed#invites")
    if not take_seat(s, r.id):   # someone else got the seat first (an application or another invitation)
        s.rollback(); inv = s.get(Invitation, iid)
        if inv.status == "pending": inv.status, inv.decided_at = "closed", datetime.utcnow(); s.commit()
        return go("/activity?n=seatfull#invites")
    a = s.exec(select(Application).where(Application.role_id == r.id, Application.user_id == user.id)).first()
    if a: a.status, a.at = "accepted", datetime.utcnow()
    else: s.add(Application(role_id=r.id, user_id=user.id, message="Joined by invitation.", status="accepted"))
    inv.status, inv.decided_at = "accepted", datetime.utcnow()
    for o in s.exec(select(Application).where(Application.role_id == r.id, Application.user_id != user.id, Application.status == "pending")).all(): o.status = "closed"
    for o in s.exec(select(Invitation).where(Invitation.role_id == r.id, Invitation.id != inv.id, Invitation.status == "pending")).all():
        o.status, o.decided_at = "closed", datetime.utcnow()
    s.commit()
    notify(s, [inv.from_id, pr.owner_id], "invite_decision", f"{user.name or user.handle} accepted your invitation and joined {pr.title} as {r.name}", f"/projects/{pr.id}#seats", pr.id, user.id)
    return go(f"/projects/{pr.id}?n=joined")


@app.post("/report-invitation/{iid}", dependencies=[limited("flag", 30, 3600)])
def report_invitation(iid: int, reason: str = Form(""), user=Depends(me), s: Session = Depends(get_session)):
    if not user: return go("/login")
    inv = s.get(Invitation, iid)
    if not inv or inv.user_id != user.id: raise HTTPException(404)
    reason = V.normalize_text(reason)[:300] or "Unwanted invitation"
    if not s.exec(select(Report.id).where(Report.reporter_id == user.id, Report.kind == "invitation", Report.target_id == iid)).first():
        s.add(Report(reporter_id=user.id, target_user_id=inv.from_id, kind="invitation", target_id=iid, reason=reason))
    if inv.status == "pending": inv.status, inv.decided_at = "declined", datetime.utcnow()
    s.commit()
    return go("/activity?n=reported#invites")


@app.post("/block/{uid}", dependencies=[limited("block", 30, 3600)])
def block_user(uid: int, next: str = Form("/activity"), user=Depends(me), s: Session = Depends(get_session)):
    if not user: return go("/login")
    other = s.get(User, uid)
    if not other or other.id == user.id or other.is_admin: return go("/activity")
    if not s.exec(select(Block.id).where(Block.blocker_id == user.id, Block.blocked_id == uid)).first():
        s.add(Block(blocker_id=user.id, blocked_id=uid))
        for inv in s.exec(select(Invitation).where(Invitation.status == "pending", or_(and_(Invitation.user_id == user.id, Invitation.from_id == uid),
                                                                                       and_(Invitation.user_id == uid, Invitation.from_id == user.id)))).all():
            inv.status, inv.decided_at = "declined" if inv.user_id == user.id else "withdrawn", datetime.utcnow()
        s.commit()
    return go((next if next.startswith(("/activity", "/u/")) else "/activity") + ("&" if "?" in next else "?") + "n=blocked")


@app.post("/unblock/{uid}")
def unblock_user(uid: int, next: str = Form("/profile"), user=Depends(me), s: Session = Depends(get_session)):
    if not user: return go("/login")
    for b in s.exec(select(Block).where(Block.blocker_id == user.id, Block.blocked_id == uid)).all(): s.delete(b)
    s.commit()
    return go(next if next.startswith(("/profile", "/u/")) else "/profile")


def for_activity(s, user):
    """Invitations this person received (newest first) and the ones they sent, for the Activity page."""
    got = s.exec(select(Invitation).where(Invitation.user_id == user.id).order_by(Invitation.at.desc()).limit(50)).all()
    sent = s.exec(select(Invitation).where(Invitation.from_id == user.id).order_by(Invitation.at.desc()).limit(50)).all()
    ids = {i.role_id for i in got + sent}; pids = {i.project_id for i in got + sent}; uids = {i.from_id for i in got} | {i.user_id for i in sent}
    roles = {r.id: r for r in s.exec(select(Role).where(Role.id.in_(ids or [-1]))).all()}
    projs = {p.id: p for p in s.exec(select(Project).where(Project.id.in_(pids or [-1]))).all()}
    people = {u.id: u for u in s.exec(select(User).where(User.id.in_(uids or [-1]))).all()}
    row = lambda i, who: dict(i=i, r=roles.get(i.role_id), p=projs.get(i.project_id), who=people.get(who))
    return dict(got=[row(i, i.from_id) for i in got], sent=[row(i, i.user_id) for i in sent])
