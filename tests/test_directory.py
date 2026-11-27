"""Bilingual directory: additive imports that never overwrite, department lists strictly per university, official or
typed departments at sign-up and on the profile, and the sign-up document step (an upload never verifies anyone)."""
import io, re
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select
from app.main import app
from app.db import engine, init_db
from app import academics as AC, config, storage
from app.models import (User, Institution, InstitutionDomain, StudentIdRule, Affiliation, AcademicUnit, StudentVerification,
                        VerificationEvent, Project, Role, Application, Invitation, Block, Report)
from tests.test_academics import signup, PW


@pytest.fixture()
def db(tmp_path, monkeypatch):
    init_db()
    from app.main import HITS; HITS.clear()
    storage.set_verify_backend(storage.LocalStorage(str(tmp_path / "v")))
    monkeypatch.setattr(config, "MULTI_SCHOOL", True)
    with Session(engine) as s:
        for t in (VerificationEvent, StudentVerification, Invitation, Block, Report, Application, Role, Project, Affiliation,
                  StudentIdRule, InstitutionDomain, AcademicUnit, Institution, User):
            for row in s.exec(select(t)).all(): s.delete(row)
        s.commit()
        AC.do_import(s, apply=True); AC.do_names(s, apply=True); AC.do_units(s, apply=True); AC.forget_ident()
        yield s
    storage.set_verify_backend(None)


def code(s, moe):
    return s.exec(select(Institution).where(Institution.moe_code == moe)).first()


def test_directory_import_is_additive_and_never_overwrites(db):
    assert code(db, "0002").name_en == "National Tsing Hua University"          # NTHU's reviewed name stays
    ntu = code(db, "0003"); assert ntu.name_en == "National Taiwan University" and ntu.aliases == "NTU" and ntu.en_status == "verified"
    assert "udb.moe.edu.tw" in ntu.en_source
    assert code(db, "0050").en_status == "needs_review"                          # kept as MOE publishes it, flagged
    ntu.name_en = "Hand-checked name"; db.add(ntu); db.commit()
    out = AC.do_names(db, apply=True)
    assert out["set_en_n"] == 0 and ("0003", "name_en already set", "Hand-checked name", "National Taiwan University") in out["conflicts"]
    assert code(db, "0003").name_en == "Hand-checked name"
    again = AC.do_units(db)
    assert again["add"] == 0 and again["same"] == again["rows"] and len(db.exec(select(AcademicUnit)).all()) == again["rows"]
    assert len(db.exec(select(Institution)).all()) == 139


def test_no_english_name_is_invented_for_units(db):
    rows = db.exec(select(AcademicUnit)).all()
    assert all(u.en_source for u in rows if u.name_en)                            # every English name has its source
    nthu = code(db, "0002")
    cs = db.exec(select(AcademicUnit).where(AcademicUnit.institution_id == nthu.id, AcademicUnit.name_zh == "資訊工程學系")).first()
    assert cs and cs.name_en == "Department of Computer Science"                 # paired from NTHU's reviewed catalog


def test_units_api_is_strictly_per_university(db):
    c = TestClient(app)
    j = c.get("/api/units/0005").json()
    ncku = code(db, "0005")
    keys = {u["k"] for u in j["units"]}
    own = {"moe:" + u.unit_code for u in db.exec(select(AcademicUnit).where(AcademicUnit.institution_id == ncku.id)).all()}
    assert keys == own and len(keys) > 50
    assert c.get("/api/units/0002").json() == {"code": "0002", "catalog": "nthu", "units": []}   # NTHU uses its catalog
    assert c.get("/api/units/9999").status_code == 404 and c.get("/api/units/..%2F").status_code == 404


def test_signup_with_official_unit_and_no_cross_school_key(db):
    ntu = code(db, "0003"); ncku = code(db, "0005")
    other = db.exec(select(AcademicUnit).where(AcademicUnit.institution_id == ntu.id)).first()
    r = signup(TestClient(app), email="x@ncku.edu.tw", student_id="E14000001", institution="0005", unit_key="moe:" + other.unit_code, vmode="skip")
    assert "not in the list" in r.text and not db.exec(select(User).where(User.email == "x@ncku.edu.tw")).first()
    mine = db.exec(select(AcademicUnit).where(AcademicUnit.institution_id == ncku.id, AcademicUnit.name_zh == "資訊工程學系")).first()
    signup(TestClient(app), email="y@ncku.edu.tw", student_id="E14000002", institution="0005", unit_key="moe:" + mine.unit_code, unit_text="whatever", vmode="skip")
    u = db.exec(select(User).where(User.email == "y@ncku.edu.tw")).first(); db.refresh(u); a = AC.current(db, u)
    assert a.institution_id == ncku.id and a.unit_key == "moe:" + mine.unit_code and a.unit_text == "資訊工程學系" and "unit" not in a.review
    assert u.faculty == "資訊工程學系" and u.student_status in ("", "pending") and not u.verified
    r = signup(TestClient(app), email="z@ntu.edu.tw", student_id="B10000003", institution="", inst_field="1", unit_text="Law", vmode="skip")
    assert "Choose your university" in r.text


def test_signup_document_goes_to_review_never_verified(db):
    from PIL import Image
    buf = io.BytesIO(); Image.new("RGB", (60, 40), "white").save(buf, "PNG")
    c = TestClient(app); t = re.search(r'name="csrf" value="([^"]+)"', c.get("/signup").text)[1]
    d = dict(csrf=t, email="d@ntu.edu.tw", name="Doc Tester", student_id="B10000004", password=PW, password2=PW, role="student",
             degree="bachelor", agree="1", institution="0003", unit_text="Department of Psychology", vmode="now", doc_type="student_card", consent="1")
    c.post("/signup", data=d, files={"vdoc": ("card.png", buf.getvalue(), "image/png")})
    u = db.exec(select(User).where(User.email == "d@ntu.edu.tw")).first(); db.refresh(u)
    sv = db.exec(select(StudentVerification).where(StudentVerification.user_id == u.id)).all()
    assert u.student_status == "needs_review" and not u.verified and len(sv) == 1 and sv[0].state == "needs_review"
    ev = db.exec(select(VerificationEvent).where(VerificationEvent.user_id == u.id)).all()
    assert [e.action for e in ev] == ["submitted"] and ev[0].note == "at sign-up"
    c.post("/signup", data=d, files={"vdoc": ("card.png", buf.getvalue(), "image/png")})          # the same form sent again
    assert len(db.exec(select(StudentVerification).where(StudentVerification.user_id == u.id)).all()) == 1
    assert len(db.exec(select(User).where(User.email == "d@ntu.edu.tw")).all()) == 1
    # a script disguised as an image is refused before any account exists
    c2 = TestClient(app); t2 = re.search(r'name="csrf" value="([^"]+)"', c2.get("/signup").text)[1]
    d.update(csrf=t2, email="e@ntu.edu.tw", student_id="B10000005")
    r = c2.post("/signup", data=d, files={"vdoc": ("card.png", b"<script>alert(1)</script>", "image/png")})
    assert "JPEG or PNG" in r.text and not db.exec(select(User).where(User.email == "e@ntu.edu.tw")).first()
    big = b"%PDF-1.4\n" + b"0" * (5 * 1024 * 1024 + 10)
    d.update(email="f@ntu.edu.tw", student_id="B10000006")
    r = c2.post("/signup", data=d, files={"vdoc": ("x.pdf", big, "application/pdf")})
    assert "larger than 5 MB" in r.text and not db.exec(select(User).where(User.email == "f@ntu.edu.tw")).first()


def test_profile_changes_department_never_university(db):
    signup(TestClient(app), email="p@ntu.edu.tw", student_id="B10000007", institution="0003", unit_text="Psych", vmode="skip")
    c = TestClient(app); t = re.search(r'name="csrf" value="([^"]+)"', c.get("/login").text)[1]
    c.post("/login", data=dict(csrf=t, email="p@ntu.edu.tw", password=PW))
    page = c.get("/profile").text
    assert "國立臺灣大學" in page and 'name="institution"' not in page and 'data-unitpick data-inst="0003"' in page
    ntu = code(db, "0003"); ncku = code(db, "0005")
    law = db.exec(select(AcademicUnit).where(AcademicUnit.institution_id == ntu.id, AcademicUnit.name_zh == "法律學系")).first()
    foreign = db.exec(select(AcademicUnit).where(AcademicUnit.institution_id == ncku.id)).first()
    t = re.search(r'name="csrf" value="([^"]+)"', page)[1]
    base = dict(csrf=t, name="Lin Mei", hours="5", degree="master", institution="0005")
    r = c.post("/profile", data={**base, "unit_key": "moe:" + foreign.unit_code, "unit_text": "x"})
    assert "not in your university&#39;s list" in r.text
    c.post("/profile", data={**base, "unit_key": "moe:" + law.unit_code, "unit_text": "x"})
    u = db.exec(select(User).where(User.email == "p@ntu.edu.tw")).first(); db.refresh(u); a = AC.current(db, u)
    assert a.institution_id == ntu.id and a.unit_key == "moe:" + law.unit_code and a.unit_text == "法律學系" and "unit" not in a.review


def test_admin_affiliation_review_access_and_audit(db):
    signup(TestClient(app), email="q@ntu.edu.tw", student_id="B10000008", institution="0003", unit_text="Lawz", vmode="skip")
    u = db.exec(select(User).where(User.email == "q@ntu.edu.tw")).first(); a = AC.current(db, u)
    c = TestClient(app); t = re.search(r'name="csrf" value="([^"]+)"', c.get("/login").text)[1]
    c.post("/login", data=dict(csrf=t, email="q@ntu.edu.tw", password=PW))
    assert c.get("/admin/affiliations").status_code == 403
    t = re.search(r'name="csrf" value="([^"]+)"', c.get("/profile").text)[1]
    assert c.post(f"/admin/affiliations/{a.id}", data=dict(csrf=t, action="keep")).status_code == 403
    adm = User(email="adm@x.tw", handle="adm", name="Adm", is_admin=True); db.add(adm); db.commit()
    from app.security import hash_password
    adm.password_hash = hash_password(PW); db.add(adm); db.commit()
    c2 = TestClient(app); t2 = re.search(r'name="csrf" value="([^"]+)"', c2.get("/login").text)[1]
    c2.post("/login", data=dict(csrf=t2, email="adm@x.tw", password=PW))
    page = c2.get("/admin/affiliations").text; t2 = re.search(r'name="csrf" value="([^"]+)"', page)[1]
    assert "Lawz" in page
    law = db.exec(select(AcademicUnit).where(AcademicUnit.institution_id == a.institution_id, AcademicUnit.name_zh == "法律學系")).first()
    c2.post(f"/admin/affiliations/{a.id}", data=dict(csrf=t2, action="link", unit_key="moe:" + law.unit_code))
    db.refresh(a)
    assert a.unit_key == "moe:" + law.unit_code and "unit" not in a.review and a.student_id == "B10000008" and a.current
    assert db.exec(select(VerificationEvent).where(VerificationEvent.action == "affiliation_link")).first()


SIX = {   # team review of the six names flagged in the first pass: 4 corrected from the schools' own sites, 2 still under review
    "0050": ("National Taichung University Of Science And Technology", "needs_review", "udb.moe.edu.tw"),
    "1020": ("Nanhua University", "verified", "en.nhu.edu.tw"),
    "1052": ("CTBC University of Technology", "verified", "ctbctech.edu.tw"),
    "1196": ("Dharma Drum Institute of Liberal Arts", "verified", "dila.edu.tw"),
    "1285": ("TZU HUI Institute of Technology", "needs_review", "udb.moe.edu.tw"),
    "1286": ("Cardinal Tien Junior College of Healthcare and Management", "verified", "ctcn.edu.tw"),
}
MOE_TEXT = {"1020": "Nanhua university", "1052": "CTBC UNIVERSITY OF TECHNOLOGY", "1196": "Dharma Drum Institute of Liberal Art",
            "1286": "Cardinal Tien Junior College of Healthcare And Management"}


@pytest.mark.parametrize("moe", sorted(SIX))
def test_six_reviewed_names_in_db_and_dataset(db, moe):
    name, status, host = SIX[moe]
    i = code(db, moe)
    assert (i.name_en, i.en_status) == (name, status) and host in i.en_source
    row = {r["moe_code"]: r for r in AC._read_pipe(AC.DIR_CSV)}[moe]
    assert (row["name_en"], row["en_status"]) == (name, status) and host in row["en_source"]
    assert row["moe114_en"] == MOE_TEXT.get(moe, name)                           # the MOE-published text is kept for provenance
    assert row["aliases"] == i.aliases and i.aliases                             # abbreviations untouched


def test_review_counts_and_no_name_lost(db):
    rows = AC._read_pipe(AC.DIR_CSV)
    assert sum(r["en_status"] == "needs_review" for r in rows) == 2 and sum(r["en_status"] == "verified" for r in rows) == 137
    assert all(r["name_en"] for r in rows) and len({r["moe_code"] for r in rows}) == 139


def test_bootstrap_runs_once_and_only_fills(db):
    assert AC.bootstrap(db) is None                                               # departments already there: nothing happens
    for u in db.exec(select(AcademicUnit)).all(): db.delete(u)
    i = code(db, "0003"); i.name_en = "Kept as set"; db.add(i); db.commit()
    r = AC.bootstrap(db)
    assert r["units_added"] == len(db.exec(select(AcademicUnit)).all()) > 3000 and r["names_set"] == 0 and r["name_conflicts"] == 1
    assert code(db, "0003").name_en == "Kept as set" and AC.bootstrap(db) is None
