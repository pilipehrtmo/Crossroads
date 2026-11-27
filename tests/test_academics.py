"""Multi-university foundation: official institution import, NTHU migration, ID rules, per-institution uniqueness,
the MULTI_SCHOOL sign-up switch, and per-institution renewal dates."""
import re
from datetime import datetime
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select
from app.main import app
from app.db import engine, init_db
from app import academics as AC, config
from app.models import (User, Institution, InstitutionDomain, StudentIdRule, Affiliation, Project, Role, Application,
                        Invitation, Block, Report, StudentVerification, VerificationEvent, AcademicUnit)

PW = "Tr0ub4dor&3xyz"


@pytest.fixture()
def db():
    init_db()
    from app.main import HITS; HITS.clear()
    with Session(engine) as s:
        for t in (VerificationEvent, StudentVerification, Invitation, Block, Report, Application, Role, Project, Affiliation,
                  StudentIdRule, InstitutionDomain, AcademicUnit, Institution, User):
            for row in s.exec(select(t)).all(): s.delete(row)
        s.commit()
        yield s


def test_import_is_dry_run_by_default_then_idempotent(db):
    out = AC.do_import(db)
    assert out == dict(added=139, updated=0, rows=139) and db.exec(select(Institution)).first() is None
    AC.do_import(db, apply=True)
    assert len(db.exec(select(Institution)).all()) == 139
    n = AC.nthu(db)
    assert n.name_zh == "國立清華大學" and n.name_en == "National Tsing Hua University" and n.source_year == "115"
    assert db.exec(select(StudentIdRule).where(StudentIdRule.institution_id == n.id)).first().pattern == r"\d{9}"
    ntu = db.exec(select(Institution).where(Institution.moe_code == "0003")).first()
    assert ntu.name_zh == "國立臺灣大學" and ntu.name_en == ""          # no English name invented
    assert AC.do_import(db, apply=True)["added"] == 0 and AC.do_import(db)["updated"] == 0
    codes = [i.moe_code for i in db.exec(select(Institution)).all()]
    assert len(codes) == len(set(codes))                                 # no duplicate institutions


def test_migrate_keeps_departments_and_ids_and_refuses_duplicates(db):
    AC.do_import(db, apply=True)
    a = User(email="a@x.tw", handle="a", name="A", student_id="115000111", dept_id="eecs-cs", degree="bachelor"); db.add(a)
    p = User(email="p@x.tw", handle="p", name="P", role="faculty", faculty="Dept of Physics"); db.add(p)
    adm = User(email="adm@x.tw", handle="adm", name="Adm", is_admin=True); db.add(adm); db.commit()
    assert AC.do_migrate(db) == dict(accounts=2, applied=False) and db.exec(select(Affiliation)).first() is None
    AC.do_migrate(db, apply=True)
    fa = AC.current(db, a); fp = AC.current(db, p)
    assert fa.unit_key == "eecs-cs" and fa.student_id == "115000111" and fa.degree == "bachelor" and fa.kind == "student"
    assert fp.kind == "professor" and fp.student_id == "" and fp.unit_text == "Dept of Physics"
    assert AC.current(db, adm) is None
    assert AC.do_check(db) == dict(accounts=2, with_affiliation=2, more_than_one=0, duplicate_ids=0, institutions=139)
    assert AC.do_migrate(db, apply=True)["accounts"] == 0                # running it again changes nothing


def test_student_id_rules(db):
    AC.do_import(db, apply=True)
    n = AC.nthu(db); ntu = db.exec(select(Institution).where(Institution.moe_code == "0003")).first()
    assert AC.check_sid(db, n, "bachelor", "115006212")[0] == "ok"
    assert AC.check_sid(db, n, "bachelor", "12345678")[0] == "bad"      # NTHU has a rule: 9 digits
    assert AC.check_sid(db, ntu, "bachelor", "B12345678")[0] == "review"  # no documented rule: manual review, never rejected
    assert AC.check_sid(db, ntu, "bachelor", "b1 2;--")[0] == "bad"     # junk is still refused


def test_same_student_id_allowed_at_two_schools_not_twice_at_one(db):
    AC.do_import(db, apply=True)
    n = AC.nthu(db); ntu = db.exec(select(Institution).where(Institution.moe_code == "0003")).first()
    u1 = User(email="1@x.tw", handle="u1", name="U1"); u2 = User(email="2@x.tw", handle="u2", name="U2"); u3 = User(email="3@x.tw", handle="u3", name="U3")
    db.add(u1); db.add(u2); db.add(u3); db.commit()
    AC.attach(db, u1, ntu, "bachelor", "B12345678"); AC.attach(db, u2, n, "bachelor", "b12345678"); db.commit()
    assert AC.sid_taken(db, ntu.id, "b12345678") and not AC.sid_taken(db, AC.nthu(db).id, "B99999999")
    AC.attach(db, u3, ntu, "bachelor", "b 12345678")
    with pytest.raises(Exception): db.commit()                         # the database index refuses it too
    db.rollback()


def signup(c, **kw):
    t = re.search(r'name="csrf" value="([^"]+)"', c.get("/signup").text)[1]
    d = dict(csrf=t, email="", name="Lin Mei", student_id="", password=PW, password2=PW, role="student", degree="master", agree="1")
    d.update(kw); return c.post("/signup", data=d)


def test_multi_school_signup_records_affiliation_and_keeps_nthu_path(db, monkeypatch):
    AC.do_import(db, apply=True)
    monkeypatch.setattr(config, "MULTI_SCHOOL", True)
    assert "國立臺灣大學" in TestClient(app).get("/signup").text
    signup(TestClient(app), email="lin@ntu.edu.tw", student_id="R12345678", institution="0003", unit_text="Department of Psychology")
    u = db.exec(select(User).where(User.email == "lin@ntu.edu.tw")).first(); db.refresh(u)
    a = AC.current(db, u)
    assert u.student_id == "" and u.faculty == "Department of Psychology" and a.student_id == "R12345678" and a.review == "id_format,unit"
    r = signup(TestClient(app), email="dup@ntu.edu.tw", name="Chen Hao", student_id="r12345678", institution="0003", unit_text="Dept of Law")
    assert "already has an account" in r.text and not db.exec(select(User).where(User.email == "dup@ntu.edu.tw")).first()
    signup(TestClient(app), email="ok@nccu.edu.tw", name="Wu Jie", student_id="R12345678", institution="0001", unit_text="Dept of Law")
    assert db.exec(select(User).where(User.email == "ok@nccu.edu.tw")).first()      # same number, different school: fine
    signup(TestClient(app), email="n@gapp.nthu.edu.tw", name="Hsu Ting", student_id="115006299", institution="0002", dept_sel="eecs-cs")
    n = db.exec(select(User).where(User.email == "n@gapp.nthu.edu.tw")).first(); db.refresh(n)
    assert n.student_id == "115006299" and n.dept_id == "eecs-cs" and AC.current(db, n).unit_key == "eecs-cs"


def test_switch_off_means_no_institution_field(db, monkeypatch):
    AC.do_import(db, apply=True)
    monkeypatch.setattr(config, "MULTI_SCHOOL", False)
    assert 'name="institution"' not in TestClient(app).get("/signup").text


def test_renewal_date_follows_the_institution(db):
    from app import studentverify as SVM
    AC.do_import(db, apply=True)
    ntu = db.exec(select(Institution).where(Institution.moe_code == "0003")).first(); ntu.renewal_mmdd = "01-31"; db.add(ntu)
    u = User(email="r@x.tw", handle="r", name="R"); db.add(u); db.commit()
    AC.attach(db, u, ntu, "bachelor", "B1234567"); db.commit()
    assert SVM.renewal_for(u) == "01-31"
    v = User(email="v@x.tw", handle="v", name="V"); db.add(v); db.commit()
    assert SVM.renewal_for(v) == SVM.DEFAULT_RENEWAL
    e = SVM.expiry(datetime(2026, 1, 10), "01-31")
    assert e.year == 2027                                               # approved 3 weeks before: valid to next year
