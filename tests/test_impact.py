"""Impact numbers: only real people and real projects count (seed, demo, admin and banned rows are left out)."""
import os, tempfile
from sqlmodel import SQLModel, Session, create_engine
from app.models import User, Project, Role, Application
from app.impact import counts


def db():
    eng = create_engine(f"sqlite:///{os.path.join(tempfile.mkdtemp(), 'i.db')}")
    SQLModel.metadata.create_all(eng)
    return eng


def person(s, h, dept="", origin="real", **kw):
    u = User(email=f"{h}@x.tw", handle=h, name=h, dept_id=dept, origin=origin, **kw); s.add(u); s.commit(); s.refresh(u); return u


def team(s, lead, members, origin="real", advisor=None):
    p = Project(owner_id=lead.id, title="t", description="d", origin=origin); s.add(p); s.commit(); s.refresh(p)
    for m in members:
        r = Role(project_id=p.id, name="seat", filled=True); s.add(r); s.commit(); s.refresh(r)
        s.add(Application(role_id=r.id, user_id=m.id, status="accepted"))
    if advisor:
        r = Role(project_id=p.id, name="Advisor", advisor=True, filled=True); s.add(r); s.commit(); s.refresh(r)
        s.add(Application(role_id=r.id, user_id=advisor.id, status="accepted"))
    s.commit(); return p


def test_counts_real_rows_and_leaves_out_seed_demo_admin_banned():
    eng = db()
    with Session(eng) as s:
        lead = person(s, "lead", "eecs-cs"); same = person(s, "same", "eecs-cs"); other = person(s, "other", "sci-math")
        prof = person(s, "prof", is_faculty=True)
        team(s, lead, [same, other], advisor=prof)                       # real: 2 collaborations, 1 cross-department
        seedlead = person(s, "seedlead", origin="seed"); team(s, seedlead, [other])   # seed project owner: excluded
        demo = person(s, "demo", "sci-phys", origin="demo"); team(s, lead, [demo])     # demo member: excluded
        admin = person(s, "admin", is_admin=True); team(s, lead, [admin])            # admins never count
        gone = person(s, "gone", banned=True); team(s, lead, [gone])                 # banned accounts never count
        m = counts(s)
    assert m["teams"] == 1 and m["collaborations"] == 2 and m["advisors"] == 1
    assert m["cross_department"] == 1 and m["cross_university"] is None
    assert m["excluded"]["collaborations"] == 4
    assert m["excluded"]["people"] == 2 and m["excluded"]["projects"] == 0   # projects keep "real" unless marked


def test_seed_project_is_excluded_even_with_real_members():
    eng = db()
    with Session(eng) as s:
        lead = person(s, "lead"); m1 = person(s, "m1")
        team(s, lead, [m1], origin="seed")
        m = counts(s)
    assert m["teams"] == 0 and m["collaborations"] == 0 and m["excluded"]["projects"] == 1


def test_cross_university_counts_only_when_institutions_are_known():
    eng = db()
    with Session(eng) as s:
        lead = person(s, "lead"); a = person(s, "a"); b = person(s, "b"); c = person(s, "c")
        team(s, lead, [a, b, c])
        inst = {lead.id: 1, a.id: 2, b.id: 1}          # c has no affiliation: not counted either way
        m = counts(s, institution_of=lambda u: inst.get(u.id))
    assert m["cross_university"] == 1


def test_origin_tool_marks_only_listed_ids_and_is_repeatable():
    from app.origin_tool import plan, apply
    eng = db()
    with Session(eng) as s:
        a = person(s, "a"); b = person(s, "b")
        p = Project(owner_id=a.id, title="[Example] looks like a sample", description="d"); s.add(p); s.commit(); s.refresh(p)
        review = {"users": {"demo": [b.id, 999]}, "projects": {"seed": []}}
        ch = plan(s, review)
        assert ("users", b.id, "real", "demo") in ch and ("missing", "users", 999, "demo") in ch
        apply(s, ch)
        assert s.get(User, b.id).origin == "demo" and s.get(User, a.id).origin == "real"
        assert s.get(Project, p.id).origin == "real"          # a title is never used to classify
        assert [c for c in plan(s, review) if c[0] != "missing"] == []
