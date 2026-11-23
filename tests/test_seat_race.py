"""B5 regression: two accepts for a one-person seat at the same moment. Exactly one may win.

The old code read the seat ("not filled"), then later wrote filled = True. Two requests that both read before either
wrote both got in. take_seat() checks and fills in one statement, so the second always loses.
The interleaving below is the one that broke before: both requests have loaded the seat as empty."""
import os, tempfile
from sqlmodel import SQLModel, Session, create_engine, select
from app.main import take_seat
from app.models import Role, Project, User


def make_db():
    path = os.path.join(tempfile.mkdtemp(), "race.db")
    eng = create_engine(f"sqlite:///{path}")
    SQLModel.metadata.create_all(eng)
    with Session(eng) as s:
        u = User(email="lead@example.com", handle="lead"); s.add(u); s.commit(); s.refresh(u)
        p = Project(owner_id=u.id, title="T", description="d"); s.add(p); s.commit(); s.refresh(p)
        r = Role(project_id=p.id, name="UI designer"); s.add(r); s.commit(); s.refresh(r)
        return eng, r.id


def test_second_accept_loses_even_when_both_saw_an_empty_seat():
    eng, rid = make_db()
    a, b = Session(eng), Session(eng)
    assert a.get(Role, rid).filled is False and b.get(Role, rid).filled is False   # both requests saw the seat empty
    assert take_seat(a, rid) is True; a.commit()        # first accept wins
    assert take_seat(b, rid) is False; b.rollback()     # second accept is refused, nothing written
    with Session(eng) as s: assert s.get(Role, rid).filled is True
    a.close(); b.close()


def test_take_seat_on_an_open_seat_and_after_it_reopens():
    eng, rid = make_db()
    with Session(eng) as s:
        assert take_seat(s, rid) is True; s.commit()
        assert take_seat(s, rid) is False
        r = s.get(Role, rid); r.filled = False; s.add(r); s.commit()   # the lead removed the member: the seat is open again
        assert take_seat(s, rid) is True; s.commit()
