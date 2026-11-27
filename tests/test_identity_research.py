"""Profile identity tags (university + role) and research eligibility by university, through the real routes.

Professor-led research (a research position, or a Research project with research_mode "advisor") is for students of
the professor's chosen university only, checked on the server at apply, invite, accept and accept-invitation.
Student-led research is open to students of every university.
"""
import re
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select
from app.main import app
from app.db import engine, init_db
from app import academics as AC, eligibility as EL
from app.models import (User, Project, Role, Application, Invitation, Block, Report, Opening, OpeningApp, Institution, AcademicUnit,
                        InstitutionDomain, StudentIdRule, Affiliation, StudentVerification, VerificationEvent)
from app.security import hash_password

PW = "Tr0ub4dor&3xyz"
DESC = "We study how students choose study rooms on campus, with sensors and a short survey."
pytestmark = pytest.mark.skipif(not str(engine.url).startswith("sqlite"), reason="needs the test SQLite database")


def mk(s, h, **kw):
    d = dict(email=f"{h}@x.tw", handle=h, name=h.title(), password_hash=hash_password(PW), email_verified=True, verified=True,
             skills="python, statistics", open_to_join=True)
    d.update(kw); u = User(**d); s.add(u); s.commit(); s.refresh(u); return u


@pytest.fixture()
def w():
    init_db()
    from app.main import HITS; HITS.clear()
    with Session(engine) as s:
        for t in (VerificationEvent, StudentVerification, OpeningApp, Opening, Invitation, Block, Report, Application, Role, Project,
                  Affiliation, StudentIdRule, InstitutionDomain, AcademicUnit, Institution, User):
            for row in s.exec(select(t)).all(): s.delete(row)
        s.commit()
        AC.do_import(s, apply=True)
        nthu = AC.nthu(s); ntu = s.exec(select(Institution).where(Institution.moe_code == "0003")).first()
        prof = mk(s, "prof", role="faculty", is_faculty=True, title="Professor", skills="")
        res = mk(s, "res", role="faculty", is_faculty=True, title="Researcher", skills="")
        a = mk(s, "anna", dept_id="eecs-cs", degree="bachelor", student_id="115000001")      # NTHU student
        b = mk(s, "bo", degree="bachelor")                                                  # NTU student
        n = mk(s, "nobody", degree="bachelor")                                              # no affiliation on record
        lead = mk(s, "lead", dept_id="eecs-ee", degree="bachelor", student_id="115000002")  # NTHU student, leads student-led research
        AC.attach(s, prof, nthu, kind="professor"); AC.attach(s, res, nthu, kind="researcher")
        AC.attach(s, a, nthu, "bachelor", "115000001", unit_key="eecs-cs"); AC.attach(s, lead, nthu, "bachelor", "115000002")
        AC.attach(s, b, ntu, "bachelor", "B12345678", unit_text="Dept of Psychology"); s.commit()
        AC.forget_ident()
        return dict(nthu=nthu.id, ntu=ntu.id, prof=prof.id, res=res.id, a=a.id, b=b.id, n=n.id, lead=lead.id)


def login(h, lang="en"):
    c = TestClient(app)
    if lang == "zh": c.cookies.set("lang", "zh")
    tok = re.search(r'name="csrf" value="([^"]+)"', c.get("/login").text)[1]
    c.post("/login", data=dict(csrf=tok, email=f"{h}@x.tw", password=PW))
    return c


def csrf(c, path="/profile"): return re.search(r'name="csrf" value="([^"]+)"', c.get(path).text)[1]


def post_research(c, mode, inst=None, title="Study room sensors"):
    data = dict(csrf=csrf(c, "/projects/new"), title=title, description=DESC, kind="Research", hours="4",
                roles_json='[{"name":"Data analyst","skills":"python, statistics"}]')
    if mode: data["research_mode"] = mode
    if inst is not None: data["research_inst"] = str(inst)
    return c.post("/projects/new", data=data)


def seat_of(s, pid): return s.exec(select(Role).where(Role.project_id == pid)).first()


def advisor_project(w, c=None):
    c = c or login("prof")
    post_research(c, "advisor", w["nthu"])
    with Session(engine) as s:
        pr = s.exec(select(Project).where(Project.owner_id == w["prof"])).first()
        return pr.id, seat_of(s, pr.id).id


# ---------- identity tags ----------
def test_profiles_show_university_and_role(w):
    c = TestClient(app)
    anna = c.get("/u/anna").text
    assert "National Tsing Hua University" in anna and 'idt-role idt-student">Student<' in anna
    prof = c.get("/u/prof").text
    assert "National Tsing Hua University" in prof and ">Professor<" in prof
    assert ">Researcher<" in c.get("/u/res").text
    bo = c.get("/u/bo").text
    assert "國立臺灣大學" in bo and ">Student<" in bo                 # no checked English name: the official Chinese name, not a guess


def test_missing_affiliation_is_shown_as_missing_never_guessed(w):
    html = TestClient(app).get("/u/nobody").text
    assert "University not set" in html and "National Tsing Hua University" not in html and "國立" not in html


def test_tags_in_chinese(w):
    c = TestClient(app); c.cookies.set("lang", "zh")
    html = c.get("/u/anna").text
    assert "國立清華大學" in html and ">學生<" in html
    assert "尚未設定學校" in c.get("/u/nobody").text


def test_tags_on_project_research_and_application_views(w):
    pid, rid = advisor_project(w)
    c = login("anna"); c.post(f"/roles/{rid}/apply", data=dict(csrf=csrf(c, f"/projects/{pid}"), message="I can analyse the sensor data in python."))
    lead_view = login("prof").get(f"/projects/{pid}").text
    assert lead_view.count("National Tsing Hua University") >= 3      # owner byline, team card, the applicant
    assert ">Professor<" in lead_view and ">Student<" in lead_view
    assert "Professor-led" in lead_view and "students only" in lead_view
    board = TestClient(app).get("/").text
    assert "idtags" in board


def test_profile_edit_cannot_change_university(w):
    c = login("bo")
    c.post("/profile", data=dict(csrf=csrf(c), name="Bo", institution="0002", institution_id=str(w["nthu"]), affiliation="0002"))
    with Session(engine) as s:
        assert AC.current(s, s.get(User, w["b"])).institution_id == w["ntu"]


# ---------- the research type is explicit ----------
def test_research_needs_an_explicit_leader_and_only_professors_lead(w):
    c = login("lead")
    assert "Choose who leads this research" in post_research(c, None).text
    assert "Only a verified professor" in post_research(c, "advisor", w["nthu"]).text
    with Session(engine) as s: assert s.exec(select(Project).where(Project.owner_id == w["lead"])).first() is None
    post_research(c, "student")
    with Session(engine) as s:
        pr = s.exec(select(Project).where(Project.owner_id == w["lead"])).first()
        assert pr.research_mode == "student" and pr.institution_id is None


def test_professor_must_pick_one_of_their_own_universities(w):
    c = login("prof")
    assert "Choose the university" in post_research(c, "advisor", w["ntu"]).text   # not their affiliation
    with Session(engine) as s: assert s.exec(select(Project).where(Project.owner_id == w["prof"])).first() is None
    pid, _ = advisor_project(w, c)
    with Session(engine) as s:
        pr = s.get(Project, pid); assert pr.research_mode == "advisor" and pr.institution_id == w["nthu"]


# ---------- professor-led: same university only ----------
def test_same_university_student_can_apply(w):
    pid, rid = advisor_project(w)
    c = login("anna"); c.post(f"/roles/{rid}/apply", data=dict(csrf=csrf(c, f"/projects/{pid}"), message="I can analyse the sensor data in python."))
    with Session(engine) as s: assert s.exec(select(Application).where(Application.user_id == w["a"])).first()


def test_other_university_and_no_university_cannot_apply_even_directly(w):
    pid, rid = advisor_project(w)
    for h in ("bo", "nobody"):
        c = login(h); page = c.get(f"/projects/{pid}").text
        assert "only students of" in page and f'action="/roles/{rid}/apply"' not in page   # no apply form, and why
        r = c.post(f"/roles/{rid}/apply", data=dict(csrf=csrf(c), message="Posting straight to the endpoint anyway."))
        assert "notelig" in str(r.url)
    with Session(engine) as s: assert s.exec(select(Application).where(Application.role_id == rid)).first() is None


def test_accepting_a_bypassed_application_is_refused(w):
    pid, rid = advisor_project(w)
    with Session(engine) as s:
        a = Application(role_id=rid, user_id=w["b"], message="row written around the form"); s.add(a); s.commit(); s.refresh(a); aid = a.id
    c = login("prof"); c.post(f"/applications/{aid}/accepted", data=dict(csrf=csrf(c, f"/projects/{pid}")))
    with Session(engine) as s:
        assert s.get(Application, aid).status == "pending" and not s.get(Role, rid).filled


def test_invitations_cannot_add_another_university(w):
    pid, rid = advisor_project(w)
    c = login("prof")
    assert 'href="/u/bo"' not in c.get(f"/roles/{rid}/candidates").text and 'href="/u/anna"' in c.get(f"/roles/{rid}/candidates").text
    c.post(f"/roles/{rid}/invite/{w['b']}", data=dict(csrf=csrf(c, f"/roles/{rid}/candidates"), message="join us"))
    with Session(engine) as s:
        assert s.exec(select(Invitation).where(Invitation.user_id == w["b"])).first() is None
        inv = Invitation(role_id=rid, project_id=pid, user_id=w["b"], from_id=w["prof"]); s.add(inv); s.commit(); s.refresh(inv); iid = inv.id
    b = login("bo"); b.post(f"/invitations/{iid}/accepted", data=dict(csrf=csrf(b, "/activity")))
    with Session(engine) as s:
        assert s.get(Invitation, iid).status != "accepted" and not s.get(Role, rid).filled
        assert s.exec(select(Application).where(Application.user_id == w["b"], Application.status == "accepted")).first() is None


def test_the_selected_university_decides_not_the_professors_later_one(w):
    pid, rid = advisor_project(w)
    with Session(engine) as s:   # the professor moves to NTU later; this research stays NTHU's
        AC.attach(s, s.get(User, w["prof"]), s.get(Institution, w["ntu"]), kind="professor"); s.commit()
        pr = s.get(Project, pid)
        assert EL.for_project(s, s.get(User, w["a"]), pr, s.get(Role, rid))[0]
        assert not EL.for_project(s, s.get(User, w["b"]), pr, s.get(Role, rid))[0]


def test_advisor_seats_stay_open_to_professors(w):
    with Session(engine) as s:
        pr = Project(owner_id=w["prof"], title="T", description=DESC, kind="Research", research_mode="advisor", institution_id=w["nthu"])
        s.add(pr); s.commit(); s.refresh(pr)
        r = Role(project_id=pr.id, name="Co-advisor", advisor=True); s.add(r); s.commit()
        assert EL.project_inst(pr, r) is None and EL.project_inst(pr) == w["nthu"]


def test_research_positions_same_university_only(w):
    with Session(engine) as s:
        o = Opening(owner_id=w["prof"], title="Research assistant", description=DESC, hours="8", positions=2, institution_id=w["nthu"])
        s.add(o); s.commit(); s.refresh(o); oid = o.id
    c = login("bo"); page = c.get(f"/openings/{oid}").text
    assert "only students of" in page and "National Tsing Hua University students only" in page
    c.post(f"/openings/{oid}/apply", data=dict(csrf=csrf(c, f"/openings/{oid}"), message="I would like to join this research."))
    a = login("anna"); a.post(f"/openings/{oid}/apply", data=dict(csrf=csrf(a, f"/openings/{oid}"), message="I would like to join this research."))
    with Session(engine) as s:
        assert s.exec(select(OpeningApp).where(OpeningApp.user_id == w["b"])).first() is None
        assert s.exec(select(OpeningApp).where(OpeningApp.user_id == w["a"])).first()
        x = OpeningApp(opening_id=oid, user_id=w["b"], message="row written around the form"); s.add(x); s.commit(); s.refresh(x); xid = x.id
    p = login("prof"); p.post(f"/opening-apps/{xid}/accepted", data=dict(csrf=csrf(p, f"/openings/{oid}")))
    with Session(engine) as s: assert s.get(OpeningApp, xid).status == "pending"


def test_position_form_needs_one_of_the_professors_universities(w):
    c = login("prof")
    d = dict(csrf=csrf(c, "/openings/new"), title="Research assistant", description=DESC, hours="8", positions="1", institution_id=str(w["ntu"]))
    assert "Choose the university" in c.post("/openings/new", data=d).text
    d["institution_id"] = str(w["nthu"]); c.post("/openings/new", data=d)
    with Session(engine) as s: assert s.exec(select(Opening).where(Opening.owner_id == w["prof"])).first().institution_id == w["nthu"]


# ---------- student-led: cross-university ----------
def test_student_led_research_takes_other_universities(w):
    c = login("lead"); post_research(c, "student")
    with Session(engine) as s:
        pr = s.exec(select(Project).where(Project.owner_id == w["lead"])).first(); pid, rid = pr.id, seat_of(s, pr.id).id
    assert 'href="/u/bo"' in c.get(f"/roles/{rid}/candidates").text            # recommended across universities
    b = login("bo"); b.post(f"/roles/{rid}/apply", data=dict(csrf=csrf(b, f"/projects/{pid}"), message="I can analyse the sensor data in python."))
    with Session(engine) as s: aid = s.exec(select(Application).where(Application.user_id == w["b"])).first().id
    c.post(f"/applications/{aid}/accepted", data=dict(csrf=csrf(c, f"/projects/{pid}")))
    with Session(engine) as s: assert s.get(Application, aid).status == "accepted" and s.get(Role, rid).filled
    page = c.get(f"/projects/{pid}").text
    assert "Members from 2 universities" in page and "國立臺灣大學" in page and "Student-led" in page


# ---------- older records ----------
def test_old_research_is_flagged_for_review_and_positions_get_their_professors_university(w):
    with Session(engine) as s:
        old = Project(owner_id=w["lead"], title="Old study", description=DESC, kind="Research"); s.add(old)
        o1 = Opening(owner_id=w["prof"], title="Old position", description=DESC, hours="8")
        o2 = Opening(owner_id=w["n"], title="Owner without university", description=DESC, hours="8"); s.add(o1); s.add(o2); s.commit()
        dry = AC.do_research(s)
        assert dry["research_to_review"] == [old.id] and dry["openings_set"] == {o1.id: w["nthu"]} and dry["openings_unresolved"] == [o2.id]
        s.refresh(old); assert old.research_mode == ""                                   # dry run wrote nothing
        AC.do_research(s, apply=True); s.refresh(old); s.refresh(o1); s.refresh(o2)
        assert old.research_mode == "review" and o1.institution_id == w["nthu"] and o2.institution_id is None
        assert EL.project_inst(old) is None                                               # under review: works as before
        assert not EL.for_opening(s, s.get(User, w["a"]), o2)[0]                         # no university: nobody qualifies
        pid = old.id
    adm = login("prof")
    assert adm.post(f"/admin/research/{pid}/student", data=dict(csrf=csrf(adm))).status_code == 403
    with Session(engine) as s:
        u = mk(s, "boss", is_admin=True, verified=False)
    a = login("boss")
    a.post(f"/admin/research/{pid}/advisor", data=dict(csrf=csrf(a, "/admin")))         # owner is a student: refused
    with Session(engine) as s: assert s.get(Project, pid).research_mode == "review"
    a.post(f"/admin/research/{pid}/student", data=dict(csrf=csrf(a, "/admin")))
    with Session(engine) as s: assert s.get(Project, pid).research_mode == "student"


# ---------- students of universities without a department catalog ----------
def test_other_university_student_types_department_and_never_gets_an_nthu_one(w):
    c = login("bo")
    page = c.get("/profile").text
    assert 'name="unit_text"' in page and 'name="dept_sel"' not in page        # no NTHU department list
    c.post("/profile", data=dict(csrf=csrf(c), name="Bo", unit_text="Department of Psychology", dept_sel="eecs-cs", hours="4"))
    with Session(engine) as s:
        u = s.get(User, w["b"]); a = AC.current(s, u)
        assert u.dept_id == "" and u.faculty == "Department of Psychology" and a.unit_text == "Department of Psychology"
        assert a.institution_id == w["ntu"]                                      # still NTU
    assert 'name="dept_sel"' in login("anna").get("/profile").text or "dept_picker" not in page   # NTHU students keep the catalog


def test_university_is_not_repeated_in_the_study_line(w):
    html = TestClient(app).get("/u/bo").text
    assert html.count(">國立臺灣大學<") == 1                                  # shown once (the tag), not again in the study line
