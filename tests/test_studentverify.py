"""Student verification through the real routes: upload checks, private access, decisions, retention, pending limits."""
import io, re, tempfile
from datetime import datetime, timedelta
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlmodel import Session, select
from app.main import app
from app.db import engine, init_db
from app.models import User, Project, Role, Application, StudentVerification as SV, VerificationEvent as VE, Invitation, Block, Report
from app.security import hash_password
from app import storage, studentverify as SVM

PW = "Tr0ub4dor&3xyz"


def png(w=40, h=30, exif=False):
    b = io.BytesIO(); Image.new("RGB", (w, h), (200, 30, 30)).save(b, "PNG"); return b.getvalue()


def jpg_with_gps():
    im = Image.new("RGB", (30, 20), (0, 90, 200)); ex = im.getexif(); ex[0x010F] = "PhoneMaker"; ex[0x0110] = "Model X"
    b = io.BytesIO(); im.save(b, "JPEG", exif=ex.tobytes()); return b.getvalue()


def pdf(js=False):
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject, NameObject, TextStringObject
    w = PdfWriter(); w.add_blank_page(200, 200)
    if js: w._root_object[NameObject("/OpenAction")] = DictionaryObject({NameObject("/S"): NameObject("/JavaScript"), NameObject("/JS"): TextStringObject("app.alert(1)")})
    b = io.BytesIO(); w.write(b); return b.getvalue()


_n = [0]
def mk(s, h, **kw):
    _n[0] += 1
    d = dict(email=f"{h}@x.tw", handle=h, name=h.title(), password_hash=hash_password(PW), email_verified=True, student_id=f"1159{_n[0]:05d}")
    d.update(kw); u = User(**d); s.add(u); s.commit(); s.refresh(u); return u


@pytest.fixture()
def env():
    init_db()
    from app.main import HITS; HITS.clear()   # rate limits are per account id, and ids restart in every test
    storage.set_verify_backend(storage.LocalStorage(tempfile.mkdtemp()))
    with Session(engine) as s:
        for t in (VE, SV, Invitation, Block, Report, Application, Role, Project, User):
            for row in s.exec(select(t)).all(): s.delete(row)
        s.commit()
        st = mk(s, "stu"); other = mk(s, "other")
        adm = mk(s, "adm", is_admin=True, student_id=""); lead = mk(s, "lead", verified=True)
        return dict(stu=st.id, other=other.id, adm=adm.id, lead=lead.id)


def login(email):
    c = TestClient(app)
    t = re.search(r'name="csrf" value="([^"]+)"', c.get("/login").text)[1]
    c.post("/login", data=dict(csrf=t, email=email, password=PW)); return c


def csrf(c, path="/verify-student"): return re.search(r'name="csrf" value="([^"]+)"', c.get(path).text)[1]


def send(c, data, name="card.png", mime="image/png", doc="student_card", consent="1"):
    return c.post("/verify-student/upload", data=dict(csrf=csrf(c), doc_type=doc, consent=consent), files={"file": (name, data, mime)})


def latest(uid):
    with Session(engine) as s: return s.exec(select(SV).where(SV.user_id == uid).order_by(SV.id.desc())).first()


def test_valid_upload_goes_to_review_and_key_never_appears_in_pages(env):
    c = login("stu@x.tw"); r = send(c, png())
    assert "Document received" in r.text
    req = latest(env["stu"]); assert req.state == "needs_review" and req.mime == "image/png" and req.storage_key
    with Session(engine) as s: assert s.get(User, env["stu"]).student_status == "needs_review"
    for path in ("/verify-student", "/profile", "/u/stu", "/activity"):
        html = c.get(path).text
        assert req.storage_key not in html and req.storage_key.split("/")[-1] not in html, path


@pytest.mark.parametrize("data,name,mime", [
    (b"MZ\x90\x00 not really a picture", "card.png", "image/png"),       # a program renamed to .png
    (b"<svg onload=alert(1)></svg>", "card.svg", "image/svg+xml"),
    (b"<html><script>x</script></html>", "card.pdf", "application/pdf"),
    (b"", "card.png", "image/png"),
])
def test_wrong_file_types_are_refused_by_content(env, data, name, mime):
    c = login("stu@x.tw"); send(c, data, name, mime)
    assert latest(env["stu"]) is None


def test_oversized_upload_is_refused(env):
    c = login("stu@x.tw"); send(c, b"\x89PNG\r\n\x1a\n" + b"0" * (5 * 1024 * 1024 + 10))
    assert latest(env["stu"]) is None


def test_pdf_with_javascript_is_refused_and_plain_pdf_accepted(env):
    c = login("stu@x.tw"); send(c, pdf(js=True), "e.pdf", "application/pdf", "enrollment_certificate")
    assert latest(env["stu"]) is None
    send(c, pdf(), "e.pdf", "application/pdf", "enrollment_certificate")
    assert latest(env["stu"]).mime == "application/pdf"


def test_image_metadata_is_stripped(env):
    c = login("stu@x.tw"); send(c, jpg_with_gps(), "c.jpg", "image/jpeg")
    req = latest(env["stu"]); data = storage.verify_backend().get(req.storage_key)
    assert b"PhoneMaker" not in data and b"Model X" not in data and dict(Image.open(io.BytesIO(data)).getexif()) == {}


def test_consent_and_type_are_required(env):
    c = login("stu@x.tw"); send(c, png(), consent=""); send(c, png(), doc="passport")
    assert latest(env["stu"]) is None


def test_only_admins_can_open_documents_and_every_view_is_logged(env):
    c = login("stu@x.tw"); send(c, png()); rid = latest(env["stu"]).id
    assert TestClient(app).get(f"/admin/verification/{rid}/file", follow_redirects=False).status_code == 403   # logged out
    assert c.get(f"/admin/verification/{rid}/file").status_code == 403                                          # the student themself
    assert login("other@x.tw").get(f"/admin/verification/{rid}/file").status_code == 403
    a = login("adm@x.tw"); r = a.get(f"/admin/verification/{rid}/file")
    assert r.status_code == 200 and r.headers["cache-control"].startswith("no-store") and r.content[:4] == b"\x89PNG"
    with Session(engine) as s:
        assert [e.action for e in s.exec(select(VE).where(VE.request_id == rid)).all()] == ["submitted", "viewed"]


def test_non_admin_cannot_decide(env):
    c = login("stu@x.tw"); send(c, png()); rid = latest(env["stu"]).id
    assert c.post(f"/admin/verification/{rid}/approve", data=dict(csrf=csrf(c))).status_code == 403
    assert latest(env["stu"]).state == "needs_review"


def test_approve_gives_badge_with_expiry_and_schedules_deletion(env):
    c = login("stu@x.tw"); send(c, png()); rid = latest(env["stu"]).id
    a = login("adm@x.tw"); a.post(f"/admin/verification/{rid}/approve", data=dict(csrf=csrf(a, "/admin/verification")))
    with Session(engine) as s:
        u = s.get(User, env["stu"]); r = s.get(SV, rid)
        assert u.verified and u.student_status == "verified" and u.verify_expires_at > datetime.utcnow() + timedelta(days=59)
        assert r.state == "verified" and timedelta(days=13) < r.delete_after - r.decided_at <= timedelta(days=14)


def test_reject_needs_reason_then_student_resubmits(env):
    c = login("stu@x.tw"); send(c, png()); rid = latest(env["stu"]).id
    a = login("adm@x.tw"); t = csrf(a, "/admin/verification")
    a.post(f"/admin/verification/{rid}/reject", data=dict(csrf=t, reason=""))
    assert latest(env["stu"]).state == "needs_review"                       # no reason: nothing happens
    a.post(f"/admin/verification/{rid}/reject", data=dict(csrf=t, reason="Not an official university document."))
    assert "Not an official university document." in c.get("/verify-student").text
    with Session(engine) as s: assert s.get(User, env["stu"]).student_status == "rejected"
    send(c, png(50, 50)); assert latest(env["stu"]).id != rid and latest(env["stu"]).state == "needs_review"


def test_action_required_then_resubmission(env):
    c = login("stu@x.tw"); send(c, png()); rid = latest(env["stu"]).id
    a = login("adm@x.tw"); a.post(f"/admin/verification/{rid}/action_required", data=dict(csrf=csrf(a, "/admin/verification"), reason="The ID number is cut off."))
    assert "The ID number is cut off." in c.get("/verify-student").text
    send(c, png(60, 40)); assert latest(env["stu"]).state == "needs_review"


def test_cannot_upload_again_while_waiting_or_verified(env):
    c = login("stu@x.tw"); send(c, png()); send(c, png(41, 31))
    with Session(engine) as s: assert len(s.exec(select(SV).where(SV.user_id == env["stu"])).all()) == 1


def test_revoke_removes_badge_and_listing(env):
    c = login("stu@x.tw"); send(c, png()); rid = latest(env["stu"]).id
    a = login("adm@x.tw"); t = csrf(a, "/admin/verification")
    a.post(f"/admin/verification/{rid}/approve", data=dict(csrf=t))
    with Session(engine) as s: u = s.get(User, env["stu"]); u.open_to_join = True; s.add(u); s.commit()
    a.post(f"/admin/verification/{rid}/revoke", data=dict(csrf=t, reason="Fake student card."))
    with Session(engine) as s:
        u = s.get(User, env["stu"]); assert not u.verified and u.student_status == "revoked" and not u.open_to_join


def test_daily_job_deletes_files_after_retention_and_expires_badges(env):
    c = login("stu@x.tw"); send(c, png()); rid = latest(env["stu"]).id
    a = login("adm@x.tw"); a.post(f"/admin/verification/{rid}/approve", data=dict(csrf=csrf(a, "/admin/verification")))
    key = latest(env["stu"]).storage_key
    with Session(engine) as s:
        assert SVM.daily(datetime.utcnow() + timedelta(days=1), s) == dict(deleted=0, expired=0)    # not yet
        out = SVM.daily(datetime.utcnow() + timedelta(days=15), s)
        assert out["deleted"] == 1
        r = s.get(SV, rid); assert r.storage_key == "" and r.deleted_at
        u = s.get(User, env["stu"]); u.verify_expires_at = datetime.utcnow() - timedelta(minutes=1); s.add(u); s.commit()
        assert SVM.daily(None, s)["expired"] == 1
        assert s.get(User, env["stu"]).student_status == "expired" and not s.get(User, env["stu"]).verified
    with pytest.raises(storage.StorageError): storage.verify_backend().get(key)


def test_pending_student_limits_three_applications_and_cannot_publish(env):
    with Session(engine) as s:
        pr = Project(owner_id=env["lead"], title="P", description="d"); s.add(pr); s.commit(); s.refresh(pr)
        rids = []
        for i in range(4):
            r = Role(project_id=pr.id, name=f"Seat {i}", skills="python"); s.add(r); s.commit(); s.refresh(r); rids.append(r.id)
        pid = pr.id
    c = login("stu@x.tw"); t = csrf(c, f"/projects/{pid}")
    for rid in rids: c.post(f"/roles/{rid}/apply", data=dict(csrf=t, message="I would like to help with this seat, I know python."))
    with Session(engine) as s:
        assert len(s.exec(select(Application).where(Application.user_id == env["stu"], Application.status == "pending")).all()) == 3
    r = c.post("/projects/new", data=dict(csrf=t, title="My project", description="A project description long enough", kind="Side project",
                                         roles_json='[{"name":"Dev","skills":"python"}]', hours_per_week="4"))
    assert "needs a verified account" in r.text
    with Session(engine) as s: assert s.exec(select(Project).where(Project.owner_id == env["stu"])).first() is None


def test_legacy_badge_is_read_as_verified_without_inventing_a_document(env):
    with Session(engine) as s:
        u = s.get(User, env["lead"]); assert SVM.state(u) == "verified" and SVM.legacy(u)
        assert s.exec(select(SV).where(SV.user_id == u.id)).first() is None


def test_old_one_click_verify_no_longer_gives_a_badge(env):
    a = login("adm@x.tw"); t = csrf(a, "/admin/verification")
    a.post(f"/admin/verify/{env['stu']}", data=dict(csrf=t)); a.post("/admin/verify_all/0", data=dict(csrf=t))
    with Session(engine) as s: assert not s.get(User, env["stu"]).verified
