"""Student verification: a "Verified student" badge needs a human to approve an uploaded proof of enrollment.

Flow: the student uploads ONE document (student ID card, enrollment certificate, student status document or another
official university document) -> an admin reviews it -> approve / ask for a clearer document / reject (with a reason the
student sees) -> the original file is deleted 14 days after approval or 30 days after a rejection; only the decision,
dates and document type are kept. Format checks on a student ID never verify anyone.

Statuses of a person (User.student_status):
  ""/pending      no document yet                    needs_review     a document waits for an admin
  action_required the admin asked for a clearer one  verified         approved (User.verified = True)
  rejected        not accepted (may upload again)    expired          the yearly renewal date passed
  revoked         an admin withdrew the badge (fraud, mistake), with a reason
Accounts verified by an admin before document checks existed keep their badge and show as "verified (before document
checks)" to admins, who can ask them for a document; nothing about them is changed automatically.

Security: documents live in a separate PRIVATE bucket (storage.verify_backend), are fetched only through
/admin/verification/{id}/file by an admin, every view is logged (VerificationEvent), responses are not cached, and no
page, email or URL ever contains the storage key. Images are re-encoded (removes location and camera data); PDFs with
scripts, attachments or launch actions are refused.
"""
import io, os, secrets
from datetime import datetime, timedelta
from fastapi import Request, Depends, Form, HTTPException, UploadFile, File
from fastapi.responses import Response
from sqlmodel import Session, select
from .db import get_session, engine
from .models import User, StudentVerification as SV, VerificationEvent as VE
from .main import app, render, me, go, limited
from . import storage

MAX_BYTES = 5 * 1024 * 1024
KEEP_APPROVED = timedelta(days=int(os.getenv("VERIFY_KEEP_APPROVED_DAYS", "14")))
KEEP_REJECTED = timedelta(days=int(os.getenv("VERIFY_KEEP_REJECTED_DAYS", "30")))
DEFAULT_RENEWAL = os.getenv("VERIFY_RENEWAL_MMDD", "08-31")   # used when the student's institution has no rule of its own
MIN_VALID = timedelta(days=60)   # approved shortly before the renewal date: valid until the following year's date
DOC_TYPES = {"student_card": "Student ID card", "enrollment_certificate": "Enrollment certificate (在學證明)",
             "status_document": "Student status document", "other": "Other official university document"}
OPEN_STATES = ("", "pending", "action_required", "rejected", "expired")   # states in which a new upload is accepted


class DocError(Exception): pass


def state(u) -> str:
    """The person's verification state, reading old accounts honestly: an admin badge from before document checks
    counts as verified (legacy) without inventing any document."""
    if not u: return ""
    st = getattr(u, "student_status", "") or ""
    if not st and u.verified: return "verified"
    return st or "pending"


def legacy(u) -> bool:
    return bool(u) and u.verified and not (getattr(u, "student_status", "") or "")


def renewal_for(u):
    """MM-DD of the yearly renewal for this person: their institution's rule (when set) or the default."""
    try:
        from .academics import renewal_mmdd
        return renewal_mmdd(u) or DEFAULT_RENEWAL
    except Exception:
        return DEFAULT_RENEWAL


def expiry(now: datetime, mmdd: str) -> datetime:
    m, d = (int(x) for x in mmdd.split("-"))
    e = datetime(now.year, m, d, 23, 59)
    while e - now < MIN_VALID: e = datetime(e.year + 1, m, d, 23, 59)
    return e


def check_doc(data: bytes):
    """(ext, mime, clean bytes) for an acceptable proof document, else DocError. Checked by content, not by name."""
    if not data: raise DocError("The file is empty.")
    if len(data) > MAX_BYTES: raise DocError("The file is larger than 5 MB. Take a smaller photo or export a smaller PDF.")
    if data[:5] == b"%PDF-":
        low = data.lower()
        for bad in (b"/javascript", b"/js ", b"/js(", b"/js<", b"/launch", b"/embeddedfile", b"/richmedia", b"/xfa"):
            if bad in low: raise DocError("This PDF contains scripts or attachments. Print it to a new PDF or upload a photo instead.")
        try:
            from pypdf import PdfReader
            n = len(PdfReader(io.BytesIO(data)).pages)
        except Exception:
            raise DocError("This PDF could not be read. Upload another copy or a photo.")
        if n > 10: raise DocError("The PDF has more than 10 pages. Upload only the page that proves your enrollment.")
        return "pdf", "application/pdf", data
    if data[:3] == b"\xff\xd8\xff" or data[:8] == b"\x89PNG\r\n\x1a\n":
        from PIL import Image
        try:
            im = Image.open(io.BytesIO(data))
            if im.width * im.height > 40_000_000: raise DocError("The image is too large. Take a smaller photo.")
            im.load()
        except DocError: raise
        except Exception:
            raise DocError("The image could not be read. Upload a JPEG or PNG photo, or a PDF.")
        png = im.format == "PNG"
        im = im.convert("RGBA" if png and im.mode in ("RGBA", "LA", "P") else "RGB")
        out = io.BytesIO()
        im.save(out, "PNG" if png else "JPEG", **({} if png else {"quality": 90}))   # a fresh file: no EXIF, GPS or other metadata
        return ("png", "image/png", out.getvalue()) if png else ("jpg", "image/jpeg", out.getvalue())
    raise DocError("Upload a JPEG or PNG photo, or a PDF.")


def log(s, uid, action, actor=None, request_id=None, note=""):
    s.add(VE(user_id=uid, request_id=request_id, actor_id=actor, action=action, note=note[:300]))


def is_student(u) -> bool:
    return bool(u) and getattr(u, "role", "student") != "faculty" and not u.is_admin

from .main import templates as _tpl
_tpl.env.globals["is_student"] = is_student
_tpl.env.globals["vstate"] = state


# ---------- student side ----------
@app.get("/verify-student")
def page(req: Request, user=Depends(me), s: Session = Depends(get_session)):
    if not user: return go("/login?next=/verify-student")
    reqs = s.exec(select(SV).where(SV.user_id == user.id).order_by(SV.submitted_at.desc()).limit(10)).all()
    return render(req, "verify_student.html", user, st=state(user), legacy=legacy(user), reqs=reqs, types=DOC_TYPES,
                  can_upload=is_student(user) and state(user) in OPEN_STATES and storage.verify_backend() is not None,
                  stored=storage.verify_backend() is not None, notice=req.query_params.get("n", ""), err=req.query_params.get("e", ""))


@app.post("/verify-student/upload", dependencies=[limited("verifyup", 6, 86400)])
async def upload(doc_type: str = Form(""), consent: str = Form(""), file: UploadFile = File(None),
                 user=Depends(me), s: Session = Depends(get_session)):
    if not user: return go("/login")
    if not is_student(user) or state(user) not in OPEN_STATES: return go("/verify-student")
    if doc_type not in DOC_TYPES: return go("/verify-student?e=type")
    if consent != "1": return go("/verify-student?e=consent")
    st = storage.verify_backend()
    if st is None: return go("/verify-student?e=off")
    data = await file.read(MAX_BYTES + 1) if file else b""
    try: ext, mime, clean = check_doc(data)
    except DocError as e:
        from urllib.parse import quote
        return go("/verify-student?e=file&m=" + quote(str(e)))
    if not submit_clean(s, user, doc_type, (ext, mime, clean)): return go("/verify-student?e=store")
    return go("/verify-student?n=sent")


def submit_clean(s, user, doc_type, checked, note="") -> bool:
    """Store one already-checked document (check_doc output) privately and put the person in the review queue.
    The one way in for both the verification page and sign-up: an upload only ever means "needs_review", never verified.
    False when storage is unavailable or refused the file (nothing is recorded then)."""
    ext, mime, clean = checked
    st = storage.verify_backend()
    if st is None or doc_type not in DOC_TYPES: return False
    u = s.get(User, user.id)
    if not is_student(u) or state(u) not in OPEN_STATES: return False
    key = f"verify/{u.id}/{secrets.token_hex(16)}.{ext}"
    try: st.put(key, clean, mime)
    except storage.StorageError: return False
    r = SV(user_id=u.id, doc_type=doc_type, storage_key=key, mime=mime, size=len(clean))
    s.add(r); again = state(u) in ("action_required", "rejected", "expired")
    u.student_status = "needs_review"; s.commit(); s.refresh(r)
    log(s, u.id, "submitted", u.id, r.id, "resubmitted" if again else note); s.commit()
    from .notify import notify
    admins = [a.id for a in s.exec(select(User).where(User.is_admin == True)).all()]
    notify(s, admins, "verify_queue", f"{u.name or u.handle} sent a student verification document", "/admin/verification", None, u.id)
    return True


# ---------- admin side ----------
def admin_only(user):
    if not user or not user.is_admin: raise HTTPException(403)


@app.get("/admin/verification")
def queue(req: Request, user=Depends(me), s: Session = Depends(get_session)):
    admin_only(user)
    waiting = s.exec(select(SV).where(SV.state == "needs_review").order_by(SV.submitted_at)).all()
    recent = s.exec(select(SV).where(SV.state != "needs_review").order_by(SV.decided_at.desc()).limit(30)).all()
    ids = {r.user_id for r in waiting + recent}
    people = {u.id: u for u in s.exec(select(User).where(User.id.in_(ids or [-1]))).all()}
    legacy_n = len([u for u in s.exec(select(User).where(User.verified == True, User.is_admin == False, User.is_faculty == False)).all() if legacy(u)])
    return render(req, "admin_verify.html", user, waiting=waiting, recent=recent, people=people, types=DOC_TYPES, legacy_n=legacy_n,
                  notice=req.query_params.get("n", ""))


@app.get("/admin/verification/{rid}/file")
def view_file(rid: int, user=Depends(me), s: Session = Depends(get_session)):
    admin_only(user)
    r = s.get(SV, rid)
    if not r or not r.storage_key: raise HTTPException(404)
    try: data = storage.verify_backend().get(r.storage_key)
    except (storage.StorageError, AttributeError): raise HTTPException(404)
    log(s, r.user_id, "viewed", user.id, r.id); s.commit()
    return Response(data, media_type=r.mime, headers={"Cache-Control": "no-store, private", "X-Content-Type-Options": "nosniff",
                                                       "Content-Disposition": f'inline; filename="verification-{r.id}.{r.storage_key.rsplit(".", 1)[-1]}"',
                                                       "Content-Security-Policy": "default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; sandbox"})


@app.post("/admin/verification/{rid}/{action}", dependencies=[limited("verifydecide", 300, 3600)])
def decide(rid: int, action: str, reason: str = Form(""), user=Depends(me), s: Session = Depends(get_session)):
    admin_only(user)
    r = s.get(SV, rid)
    if not r: raise HTTPException(404)
    u = s.get(User, r.user_id); now = datetime.utcnow(); reason = " ".join(reason.split())[:300]
    if action in ("reject", "action_required", "revoke") and len(reason) < 5: return go("/admin/verification?n=reason")
    from .notify import notify
    if action == "approve" and r.state in ("needs_review", "action_required"):
        r.state, r.reason, r.decided_at, r.reviewer_id, r.delete_after = "verified", "", now, user.id, now + KEEP_APPROVED
        u.student_status, u.verified, u.verify_expires_at, u.verified_at = "verified", True, expiry(now, renewal_for(u)), now
        log(s, u.id, "approved", user.id, r.id); s.commit()
        notify(s, [u.id], "verification", "Your student verification was approved. You now have the Verified student badge.", "/verify-student", None, user.id)
    elif action == "action_required" and r.state == "needs_review":
        r.state, r.reason, r.decided_at, r.reviewer_id, r.delete_after = "action_required", reason, now, user.id, now + KEEP_REJECTED
        u.student_status = "action_required"; log(s, u.id, "action_required", user.id, r.id, reason); s.commit()
        notify(s, [u.id], "verification", "Your verification document needs to be clearer. Open the page to see what to send.", "/verify-student", None, user.id)
    elif action == "reject" and r.state in ("needs_review", "action_required"):
        r.state, r.reason, r.decided_at, r.reviewer_id, r.delete_after = "rejected", reason, now, user.id, now + KEEP_REJECTED
        u.student_status, u.verified = "rejected", False
        log(s, u.id, "rejected", user.id, r.id, reason); s.commit()
        notify(s, [u.id], "verification", "Your student verification was not approved. Open the page to see why and what to do.", "/verify-student", None, user.id)
    elif action == "revoke" and state(u) == "verified":
        if r.state == "verified": r.state, r.reason = "revoked", reason
        u.student_status, u.verified, u.open_to_join = "revoked", False, False
        log(s, u.id, "revoked", user.id, r.id, reason); s.commit()
        notify(s, [u.id], "verification", "Your Verified student badge was withdrawn by an admin. Open the page to see why.", "/verify-student", None, user.id)
    return go("/admin/verification?n=done")


@app.post("/admin/users/{uid}/verification/revoke")
def revoke_user(uid: int, reason: str = Form(""), user=Depends(me), s: Session = Depends(get_session)):
    """Withdraw a badge from the users list (works for legacy badges too, which have no document)."""
    admin_only(user)
    u = s.get(User, uid); reason = " ".join(reason.split())[:300]
    if not u or len(reason) < 5 or state(u) != "verified" or u.is_admin: return go("/admin/verification?n=reason")
    u.student_status, u.verified, u.open_to_join = "revoked", False, False
    log(s, u.id, "revoked", user.id, None, reason); s.commit()
    from .notify import notify
    notify(s, [u.id], "verification", "Your Verified student badge was withdrawn by an admin. Open the page to see why.", "/verify-student", None, user.id)
    return go("/admin/verification?n=done")


# ---------- daily job: delete documents past their retention date, expire badges past their renewal date ----------
def daily(now=None, s=None):
    now = now or datetime.utcnow(); own = s is None
    s = s or Session(engine); st = storage.verify_backend(); deleted = expired = 0
    try:
        for r in s.exec(select(SV).where(SV.delete_after != None, SV.delete_after < now, SV.deleted_at == None)).all():
            if r.storage_key and st is not None:
                try: st.delete(r.storage_key)
                except storage.StorageError: continue   # try again tomorrow; never mark a file deleted that is still there
            r.storage_key, r.deleted_at = "", now; log(s, r.user_id, "deleted", None, r.id); deleted += 1
        gone = []
        for u in s.exec(select(User).where(User.student_status == "verified", User.verify_expires_at != None, User.verify_expires_at < now)).all():
            u.student_status, u.verified, u.open_to_join = "expired", False, False
            log(s, u.id, "expired"); gone.append(u.id); expired += 1
        s.commit()
        if gone:
            from .notify import notify
            for uid in gone:
                notify(s, [uid], "verification", "Your student verification expired for the new academic year. Upload a current document to renew it.", "/verify-student")
        return dict(deleted=deleted, expired=expired)
    finally:
        if own: s.close()
