"""Find teammates and invitations, through the real routes (TestClient on a throw-away SQLite database).

Covers: who is listed, who may invite, duplicate and limit rules, blocked users, accept fills the seat once,
an invitation racing an application for the same seat, demo data never meeting real people, CSRF.
"""
import os, re, tempfile
import pytest

from fastapi.testclient import TestClient
from sqlmodel import Session, select
from app.main import app
from app.db import engine, init_db
from app.models import User, Project, Role, Application, Invitation, Block, Report
from app.security import hash_password
from app import invites as INV

PW = "Tr0ub4dor&3xyz"
pytestmark = pytest.mark.skipif(not str(engine.url).startswith("sqlite"), reason="needs the test SQLite database")


def mk(s, h, **kw):
    d = dict(email=f"{h}@x.tw", handle=h, name=h.title(), password_hash=hash_password(PW), email_verified=True, verified=True)
    d.update(kw); u = User(**d); s.add(u); s.commit(); s.refresh(u); return u


@pytest.fixture()
def world():
    init_db()
    with Session(engine) as s:
        for t in (Invitation, Block, Report, Application, Role, Project, User):
            for row in s.exec(select(t)).all(): s.delete(row)
        s.commit()
        lead = mk(s, "lead", skills="python, react", dept_id="eecs-cs")
        arif = mk(s, "arif", skills="figma, ui design, user research", dept_id="c:arts", open_to_join=True)
        quiet = mk(s, "quiet", skills="figma, ui design", open_to_join=False)               # not opted in
        pend = mk(s, "pend", skills="figma, ui design", open_to_join=True, verified=False)   # not verified
        demo = mk(s, "demo", skills="figma, ui design", open_to_join=True, origin="demo")    # demo person
        pr = Project(owner_id=lead.id, title="Lost and found", description="d"); s.add(pr); s.commit(); s.refresh(pr)
        r = Role(project_id=pr.id, name="UI designer", skills="figma, ui design", nice_skills="user research"); s.add(r); s.commit(); s.refresh(r)
        return dict(lead=lead.id, arif=arif.id, quiet=quiet.id, pend=pend.id, demo=demo.id, pr=pr.id, r=r.id)


def login(email):
    c = TestClient(app)
    tok = re.search(r'name="csrf" value="([^"]+)"', c.get("/login").text)[1]
    c.post("/login", data=dict(csrf=tok, email=email, password=PW))
    return c, tok


def csrf(c, path="/activity"): return re.search(r'name="csrf" value="([^"]+)"', c.get(path).text)[1]


def test_only_verified_opted_in_real_people_are_listed(world):
    c, _ = login("lead@x.tw")
    html = c.get(f"/roles/{world['r']}/candidates").text
    assert 'href="/u/arif"' in html
    assert 'href="/u/quiet"' not in html and 'href="/u/pend"' not in html and 'href="/u/demo"' not in html
    assert "Covers 2 of 2 must-have skills: figma, ui design" in html


def test_non_lead_cannot_see_or_invite(world):
    c, _ = login("arif@x.tw")
    assert c.get(f"/roles/{world['r']}/candidates").status_code == 403
    t = csrf(c)
    assert c.post(f"/roles/{world['r']}/invite/{world['quiet']}", data=dict(csrf=t)).status_code == 403


def test_invite_requires_csrf(world):
    c, _ = login("lead@x.tw")
    r = c.post(f"/roles/{world['r']}/invite/{world['arif']}", data={}, follow_redirects=False)
    assert r.status_code in (400, 403)
    with Session(engine) as s: assert s.exec(select(Invitation)).first() is None


def test_invite_accept_fills_seat_once_and_records_member(world):
    c, _ = login("lead@x.tw"); t = csrf(c)
    c.post(f"/roles/{world['r']}/invite/{world['arif']}", data=dict(csrf=t, message="We need your design skills"))
    c.post(f"/roles/{world['r']}/invite/{world['arif']}", data=dict(csrf=t))            # a second click: no duplicate
    with Session(engine) as s:
        invs = s.exec(select(Invitation)).all(); assert len(invs) == 1 and invs[0].status == "pending"
        iid = invs[0].id
    a, _ = login("arif@x.tw"); ta = csrf(a)
    assert "We need your design skills" in a.get("/activity").text
    a.post(f"/invitations/{iid}/accepted", data=dict(csrf=ta))
    a.post(f"/invitations/{iid}/accepted", data=dict(csrf=ta))                          # double accept: still one member
    with Session(engine) as s:
        assert s.get(Role, world["r"]).filled is True
        apps = s.exec(select(Application).where(Application.role_id == world["r"], Application.status == "accepted")).all()
        assert [x.user_id for x in apps] == [world["arif"]]
        assert s.get(Invitation, iid).status == "accepted"


def test_pending_student_cannot_invite_or_be_invited(world):
    with Session(engine) as s:
        u = s.get(User, world["lead"]); u.verified = False; s.add(u); s.commit()
    c, _ = login("lead@x.tw"); t = csrf(c)
    c.post(f"/roles/{world['r']}/invite/{world['arif']}", data=dict(csrf=t))
    with Session(engine) as s: assert s.exec(select(Invitation)).first() is None


def test_unverified_or_demo_person_cannot_be_invited_by_crafted_request(world):
    c, _ = login("lead@x.tw"); t = csrf(c)
    for who in ("pend", "demo", "quiet"):
        c.post(f"/roles/{world['r']}/invite/{world[who]}", data=dict(csrf=t))
    with Session(engine) as s: assert s.exec(select(Invitation)).first() is None


def test_blocked_user_is_hidden_and_cannot_be_invited(world):
    a, _ = login("arif@x.tw"); ta = csrf(a)
    a.post(f"/block/{world['lead']}", data=dict(csrf=ta))
    c, _ = login("lead@x.tw"); t = csrf(c)
    assert 'href="/u/arif"' not in c.get(f"/roles/{world['r']}/candidates").text
    c.post(f"/roles/{world['r']}/invite/{world['arif']}", data=dict(csrf=t))
    with Session(engine) as s: assert s.exec(select(Invitation)).first() is None


def test_seat_limit_and_no_reinvite_after_decline(world):
    with Session(engine) as s:
        extra = [mk(s, f"x{i}", skills="figma", open_to_join=True).id for i in range(4)]
    c, _ = login("lead@x.tw"); t = csrf(c)
    for uid in extra: c.post(f"/roles/{world['r']}/invite/{uid}", data=dict(csrf=t))
    with Session(engine) as s:
        assert len(s.exec(select(Invitation).where(Invitation.status == "pending")).all()) == INV.PENDING_PER_SEAT
        iid = s.exec(select(Invitation).where(Invitation.user_id == extra[0])).first().id
    x, _ = login("x0@x.tw"); x.post(f"/invitations/{iid}/declined", data=dict(csrf=csrf(x)))
    c.post(f"/roles/{world['r']}/invite/{extra[0]}", data=dict(csrf=t))
    with Session(engine) as s:
        assert len(s.exec(select(Invitation).where(Invitation.user_id == extra[0])).all()) == 1


def test_invitation_loses_cleanly_when_an_application_filled_the_seat(world):
    with Session(engine) as s:
        other = mk(s, "other", skills="figma")
        s.add(Application(role_id=world["r"], user_id=other.id, message="I would like to join this team", status="pending")); s.commit()
        aid = s.exec(select(Application)).first().id
    c, _ = login("lead@x.tw"); t = csrf(c)
    c.post(f"/roles/{world['r']}/invite/{world['arif']}", data=dict(csrf=t))
    c.post(f"/applications/{aid}/accepted", data=dict(csrf=t))       # the application wins first
    with Session(engine) as s: iid = s.exec(select(Invitation)).first().id
    a, _ = login("arif@x.tw"); r = a.post(f"/invitations/{iid}/accepted", data=dict(csrf=csrf(a)), follow_redirects=False)
    with Session(engine) as s:
        assert s.get(Invitation, iid).status == "closed"
        assert len(s.exec(select(Application).where(Application.status == "accepted")).all()) == 1


def test_report_invitation_creates_report_and_declines(world):
    c, _ = login("lead@x.tw"); c.post(f"/roles/{world['r']}/invite/{world['arif']}", data=dict(csrf=csrf(c)))
    with Session(engine) as s: iid = s.exec(select(Invitation)).first().id
    a, _ = login("arif@x.tw"); a.post(f"/report-invitation/{iid}", data=dict(csrf=csrf(a), reason="spam"))
    with Session(engine) as s:
        assert s.get(Invitation, iid).status == "declined"
        rep = s.exec(select(Report)).first(); assert rep.kind == "invitation" and rep.target_user_id == world["lead"]


def test_only_the_invited_person_can_answer(world):
    c, _ = login("lead@x.tw"); c.post(f"/roles/{world['r']}/invite/{world['arif']}", data=dict(csrf=csrf(c)))
    with Session(engine) as s: iid = s.exec(select(Invitation)).first().id
    q, _ = login("quiet@x.tw")
    assert q.post(f"/invitations/{iid}/accepted", data=dict(csrf=csrf(q))).status_code == 403
